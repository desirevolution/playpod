from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import sqlite3
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from .contracts import (LinkInput, FeedDownloadInput, FeedInput, ValueBool, ModeInput,
    PlaybackInput, SleepDefaultsInput, SeekInput, VolumeInput, VolumeAdjustInput, TimerInput, ExtendInput,
    EpisodeInput, PlayEpisodeInput, OrderInput, DeleteInput, PlayerResult, QueueAddedResult,
    JobAccepted, ErrorResult, FeedResult, EpisodeResult, EpisodeListResult,
    JobResult, DownloadResult, DownloadAccepted, DownloadStatusResult,
    ActivityPageResult, ActivityStatusResult, EpisodeLocationResult, AnnouncementInput, AnnouncementResult,
    DownloadCleanupPreview, DownloadCleanupResult)

from . import __version__
from .config import Settings
from .db import Database
from .feeds import FeedJobs, web_url
from .integrations import MPD, DisabledMPD, Notifications
from .player import Player, PlayerError, MPDUnavailable
from .media import MediaLibrary, MediaError
from .downloads import Downloads
from .youtube import YouTubeCatalog, KINDS as YOUTUBE_KINDS
from .contracts import YouTubeInput
from .activity import listing, prune



def create_app(settings=None, *, mpd=None, notifications=None, background=True):
    settings = settings or Settings.from_env()
    db = Database(settings.database)
    mpd_configured = mpd is not None or bool(settings.mpd_host)
    mpd = mpd or (MPD(settings) if mpd_configured else DisabledMPD())
    notifications = notifications or Notifications(settings)
    media = MediaLibrary(db, settings)
    downloads = Downloads(db, settings)
    media.downloads = downloads
    player = Player(db, mpd, notifications, media=media)
    downloads.on_change = player.monitor_wake.set
    youtube = YouTubeCatalog(db, downloads, player)
    jobs = FeedJobs(db, settings.refresh_seconds, media=media, youtube=youtube)
    if not mpd_configured:
        player.status = {"state": "stop", "elapsed": 0, "duration": 0, "volume": -1}
        player.error = ""

    @asynccontextmanager
    async def lifespan(app):
        if background:
            notifications.start()
            if mpd_configured:
                player.start_monitor()
                player.start_announcement_worker()
            jobs.start_scheduler()
            downloads.start()
        try:
            yield
        finally:
            downloads.stop.set()
            player.stop_event.set()
            jobs.close()
            downloads.close()
            player.close()
            notifications.stop()

    app = FastAPI(title="PlayPod", version=__version__, lifespan=lifespan,
                  responses={code: {'model': ErrorResult} for code in (404, 405, 409, 422, 500, 503)})
    app.state.db, app.state.player, app.state.jobs = db, player, jobs
    app.state.media = media
    app.state.downloads = downloads
    app.state.youtube = youtube

    def error_response(status, code, message, details=None, headers=None):
        return JSONResponse({'error': {'code': code, 'message': message, 'details': details or []}},
                            status_code=status, headers=headers)

    @app.exception_handler(PlayerError)
    async def player_error(request, exc):
        return error_response(exc.status_code, exc.code, str(exc))

    @app.exception_handler(sqlite3.IntegrityError)
    async def integrity_error(request, exc):
        return error_response(409, 'integrity_conflict', 'Eintrag existiert bereits oder wurde inzwischen gelöscht')

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Do not echo request values or Python exception objects in validation responses.
        details = [{'location': list(e['loc']), 'type': e['type'], 'message': e['msg']} for e in exc.errors()]
        return error_response(422, 'validation_error', 'Ungültige Anfrage', jsonable_encoder(details))

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        code = {404: 'not_found', 405: 'method_not_allowed', 409: 'state_conflict',
                422: 'validation_error', 503: 'service_unavailable'}.get(exc.status_code, 'http_error')
        return error_response(exc.status_code, code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logging.getLogger(__name__).error('API-Anfrage fehlgeschlagen', exc_info=exc)
        return error_response(500, 'internal_error', 'Interner Fehler bei der Verarbeitung')

    def require_mpd():
        if not mpd_configured:
            raise PlayerError("MPD nicht konfiguriert", code="mpd_not_configured", status_code=503)

    def player_command(fn):
        require_mpd()
        with player.lock:
            try:
                fn()
            except PlayerError:
                raise
            except Exception as exc:
                player.sync()
                raise MPDUnavailable('MPD-Befehl fehlgeschlagen') from exc
            return player.state()

    def accepted_job(kind, feed_id=None):
        id_ = jobs.start_job(kind, feed_id) if feed_id is not None else jobs.start_job(kind)
        return {'job_id': id_, 'status_url': '/api/v1/jobs/' + id_}

    @app.get("/api/health")
    def health():
        checks = {"database": "ok", "mpd": "ok" if mpd_configured else "disabled"}
        try:
            db.one("SELECT 1")
        except sqlite3.Error:
            checks["database"] = "failed: database unavailable"
        try:
            mpd.snapshot()
        except Exception:
            checks["mpd"] = "failed: MPD unavailable"
        healthy = all(v in ("ok", "disabled") for v in checks.values())
        return JSONResponse({"status": "healthy" if healthy else "unhealthy", "timestamp": datetime.now(timezone.utc).isoformat(), "checks": checks}, status_code=200 if healthy else 500)

    @app.get("/api/live")
    def live():
        return {"status": "ok", "version": __version__}

    @app.get('/api/v1/state', response_model=PlayerResult)
    def state():
        return player.state()

    @app.post('/api/v1/playback/{action}', response_model=PlayerResult)
    def playback(action: Literal['play', 'pause', 'toggle', 'next', 'undo', 'sleep', 'normal'], data: PlaybackInput | None = None):
        timer = data.timer if data else 'keep'
        if timer != 'keep' and action not in ('play', 'toggle', 'next'):
            raise HTTPException(422, 'timer ist nur bei play, toggle und next erlaubt')
        if timer == 'preserve' and action not in ('play', 'toggle'):
            raise HTTPException(422, 'timer=preserve ist nur bei play und toggle erlaubt')
        policy = data.when_queue_empty if data else 'keep'
        if policy != 'keep' and action not in ('play','toggle','next'):
            raise HTTPException(422, 'when_queue_empty ist nur bei play, toggle und next erlaubt')
        return player_command(lambda: player.command(action, timer=timer, when_queue_empty=policy))

    @app.post('/api/v1/seek', response_model=PlayerResult)
    def seek(data: SeekInput):
        return player_command(lambda: player.seek_to(data.position_seconds, data.offset_seconds))

    @app.post('/api/v1/announcements', status_code=202, response_model=AnnouncementResult,
              responses={429: {'model': ErrorResult}})
    def announce(data: AnnouncementInput):
        """Accept text into the persistent FIFO queue; playback runs in the background."""
        require_mpd()
        return player.announce(data.text)

    @app.get('/api/v1/announcements', response_model=list[AnnouncementResult])
    def announcements():
        return player.announcement_status()

    @app.get('/api/v1/announcements/{announcement_id}', response_model=AnnouncementResult)
    def announcement(announcement_id: str):
        return player.announcement_status(announcement_id)

    @app.put('/api/v1/volume', response_model=PlayerResult)
    def volume(data: VolumeInput):
        return player_command(lambda: player.set_volume(data.value))

    @app.post('/api/v1/volume/adjust', response_model=PlayerResult)
    def adjust_volume(data: VolumeAdjustInput):
        return player_command(lambda: player.set_volume(data.delta, relative=True))

    @app.put('/api/v1/mode', response_model=PlayerResult)
    def mode(data: ModeInput):
        return player_command(lambda: player.set_mode(data.favorites_only))

    @app.post('/api/v1/mode/toggle', response_model=PlayerResult)
    def toggle_mode():
        return player_command(lambda: player.set_mode(not player.mode))

    @app.put('/api/v1/timer', response_model=PlayerResult)
    def timer(data: TimerInput):
        return player_command(lambda: player.timer(data.minutes * 60))

    @app.post('/api/v1/timer/extend', response_model=PlayerResult)
    def extend(data: ExtendInput | None = None):
        return player_command(lambda: player.timer(extend=(data.minutes if data else 5) * 60))

    @app.get("/api/v1/feeds", response_model=list[FeedResult])
    def feeds(q: str = ''):
        where = " WHERE instr(casefold(f.title),casefold(?))>0 OR EXISTS(SELECT 1 FROM episodes e WHERE e.feed_id=f.id AND instr(casefold(e.title),casefold(?))>0)" if q else ''
        return db.rows("SELECT f.*,(SELECT COUNT(*) FROM episodes e WHERE e.feed_id=f.id) AS episode_count FROM feeds f" + where + " ORDER BY f.title,f.id", (q,q) if q else ())

    @app.post("/api/v1/feeds", status_code=201)
    def add_feed(data: FeedInput):
        try:
            url = web_url(data.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        id_ = db.execute("INSERT INTO feeds(url,title,favorite) VALUES(?,?,?)", (url, data.title or url, data.favorite))
        return {"id": id_, **accepted_job("refresh", id_)}

    @app.post('/api/v1/youtube/collections', status_code=202)
    def add_youtube_collection(data: YouTubeInput):
        try:
            id_ = youtube.add(data.url, data.kind, data.limit)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {'id': id_, **accepted_job('refresh', id_)}

    @app.put("/api/v1/feeds/{feed_id}")
    def edit_feed(feed_id: int, data: FeedInput):
        existing = db.one("SELECT * FROM feeds WHERE id=?", (feed_id,))
        if not existing:
            raise HTTPException(404, "Podcast nicht gefunden")
        if existing["kind"] == "links" or existing["kind"] in YOUTUBE_KINDS:
            if data.url != existing['url']:
                raise PlayerError("Die Linksammlung hat keine veränderbare Feedadresse")
            db.execute('UPDATE feeds SET favorite=? WHERE id=?', (data.favorite, feed_id))
            return {'ok': True}
        if existing["kind"] == "local":
            if data.url != existing["url"]:
                raise HTTPException(422, "Lokale Verzeichnisse werden über MEDIA_ROOTS konfiguriert")
            db.execute("UPDATE feeds SET favorite=? WHERE id=?", (data.favorite, feed_id))
            return {"ok": True}
        try:
            web_url(data.url)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not db.one("SELECT 1 FROM feeds WHERE id=?", (feed_id,)):
            raise HTTPException(404, "Podcast nicht gefunden")
        db.execute("UPDATE feeds SET url=?,title=?,favorite=? WHERE id=?", (data.url, data.title, data.favorite, feed_id))
        return {"ok": True}

    @app.delete("/api/v1/feeds/{feed_id}")
    def delete_feed(feed_id: int):
        with player.lock, downloads.lock:
            feed = db.one("SELECT kind FROM feeds WHERE id=?", (feed_id,))
            if feed and feed["kind"] == "local":
                raise PlayerError("Lokale Sammlung über MEDIA_ROOTS deaktivieren. Einzelne Einträge können aus dem Katalog entfernt werden.")
            ids = [e["id"] for e in db.rows("SELECT id FROM episodes WHERE feed_id=?", (feed_id,))]
            if feed and feed['kind'] in (*YOUTUBE_KINDS, 'links'):
                youtube.delete(ids)
                db.execute('DELETE FROM settings WHERE key=?', (f'yt_seen:{feed_id}',))
            else:
                player.delete_episodes(ids)
            db.execute("DELETE FROM feeds WHERE id=?", (feed_id,))
        return {"ok": True}

    @app.delete('/api/v1/feeds/{feed_id}/episodes')
    def clear_link_imports(feed_id: int):
        with player.lock, downloads.lock:
            feed = db.one('SELECT kind FROM feeds WHERE id=?', (feed_id,))
            if not feed:
                raise HTTPException(404, 'Sammlung nicht gefunden')
            if feed['kind'] != 'links':
                raise PlayerError('Nur die Linkimportliste kann geleert werden')
            ids = [r['id'] for r in db.rows('SELECT id FROM episodes WHERE feed_id=?', (feed_id,))]
            player.delete_episodes(ids)
        return {'deleted': len(ids), 'files_deleted': False}

    @app.post("/api/v1/feeds/refresh", status_code=202, response_model=JobAccepted)
    def refresh_all():
        return accepted_job("refresh")

    @app.post("/api/v1/feeds/{feed_id}/refresh", status_code=202, response_model=JobAccepted)
    def refresh_one(feed_id: int):
        feed = db.one("SELECT kind FROM feeds WHERE id=?", (feed_id,))
        if not feed:
            raise HTTPException(404, "Podcast nicht gefunden")
        if feed["kind"] == "links":
            raise PlayerError("Einzelne Seitenlinks haben keinen Feedabruf")
        if feed["kind"] == "local":
            return accepted_job("media")
        return accepted_job("refresh", feed_id)

    @app.get('/api/v1/activity', response_model=ActivityPageResult)
    def activity(kind: Literal['all','new','completed'] = 'all', before: int | None = Query(None, ge=1), limit: int = Query(50, ge=1, le=200)):
        return listing(db, kind, before, limit)

    @app.get('/api/v1/activity/status', response_model=ActivityStatusResult)
    def activity_status(after: int = Query(0, ge=0)):
        with db.connect() as conn:
            prune(conn)
            row = conn.execute('SELECT COALESCE(MAX(id),0) AS latest,COUNT(CASE WHEN id>? THEN 1 END) AS unseen FROM activity', (after,)).fetchone()
            return dict(row)

    @app.get('/api/v1/episodes/{episode_id}/location', response_model=EpisodeLocationResult)
    def episode_location(episode_id: int):
        with db.connect() as conn:
            ep = conn.execute('SELECT feed_id,published,id,hidden FROM episodes WHERE id=?', (episode_id,)).fetchone()
            if not ep:
                raise HTTPException(404, 'Episode nicht gefunden')
            rank = conn.execute('''SELECT COUNT(*) FROM episodes WHERE feed_id=? AND hidden=? AND
                (published>? OR (published IS ? AND id>?) OR (? IS NULL AND published IS NOT NULL))''',
                (ep['feed_id'],ep['hidden'],ep['published'],ep['published'],episode_id,ep['published'])).fetchone()[0]
            return {'feed_id': ep['feed_id'], 'offset': (rank // 50) * 50, 'hidden': bool(ep['hidden'])}

    @app.get("/api/v1/episodes", response_model=EpisodeListResult)
    def episodes(q: str = "", filter: Literal["all", "marked", "new", "started", "completed", "local", "downloaded", "hidden"] = "all", feed_id: int | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        where, args = ["e.hidden=1" if filter == "hidden" else "e.hidden=0"], []
        if q:
            where.append("(instr(casefold(e.title),casefold(?))>0 OR instr(casefold(f.title),casefold(?))>0)")
            args += [q, q]
        if feed_id is not None:
            where.append("e.feed_id=?")
            args.append(feed_id)
        clause = {"hidden": "1=1", "all": "1=1", "marked": "e.bookmarked=1", "new": "e.last_started IS NULL AND e.completed=0", "started": "e.last_started IS NOT NULL AND e.completed=0", "completed": "e.completed=1", "local": "e.local_source IS NOT NULL", "downloaded": "EXISTS(SELECT 1 FROM downloads d WHERE d.episode_id=e.id AND d.state='ready')"}[filter]
        where.append(clause)
        base = " FROM episodes e JOIN feeds f ON f.id=e.feed_id WHERE " + " AND ".join(where)
        total = db.one("SELECT COUNT(*) AS n" + base, args)["n"]
        items = db.rows("SELECT e.*, f.title AS podcast, f.cover AS feed_cover, f.kind AS feed_kind" + base + " ORDER BY e.published DESC,e.id DESC LIMIT ? OFFSET ?", (*args, limit, offset))
        return {"items": items, "total": total}

    @app.get("/api/v1/episodes/{episode_id}", response_model=EpisodeResult)
    def episode(episode_id: int):
        return player.episode(episode_id)

    @app.delete("/api/v1/episodes/{episode_id}")
    def remove_local_episode(episode_id: int):
        with player.lock:
            ep = player.episode(episode_id)
            if ep.get('source_type') == 'web' and ep.get('feed_kind') == 'links':
                with downloads.lock:
                    youtube.delete([episode_id])
                return {'ok': True, 'file_deleted': True}
            if not ep["media_root_id"] or ep["url"]:
                raise PlayerError("Nur Einzelimporte oder lokale Katalogeinträge können entfernt werden")
            player.delete_episodes([episode_id])
        return {"ok": True, "file_deleted": False}

    @app.get("/api/v1/media/roots")
    def media_roots():
        return media.roots()

    @app.get("/api/v1/downloads", response_model=DownloadStatusResult)
    def download_status():
        result = downloads.status()
        for item in result['items']:
            item['in_use'] = downloads.browser_in_use(item['episode_id']) or (player.saved['episode_id'] == item['episode_id'] and player.saved.get('source_kind') == 'local' and bool(player.last_song))
        return result

    def accepted_download(task):
        return {**task, 'status_url': '/api/v1/downloads/' + task['id']}

    @app.get('/api/v1/downloads/{download_id}', response_model=DownloadResult)
    def download_task(download_id: str):
        return downloads.task(download_id)

    @app.post("/api/v1/links", status_code=202, response_model=DownloadAccepted)
    def add_link(data: LinkInput):
        try:
            return accepted_download(downloads.add_link(data.url))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/feeds/{feed_id}/downloads/preview")
    def feed_download_preview(feed_id: int):
        downloads.status()  # Revalidate files before excluding completed copies.
        candidates = downloads.feed_candidates(feed_id)
        return {'count': len(candidates), 'ids': [e['id'] for e in candidates[:1000]]}

    @app.post("/api/v1/feeds/{feed_id}/downloads", status_code=202)
    def feed_download(feed_id: int, data: FeedDownloadInput):
        candidates = {e['id']: e for e in downloads.feed_candidates(feed_id)}
        ids = set(data.ids)
        valid = {e['id'] for e in db.rows('SELECT id FROM episodes WHERE feed_id=?', (feed_id,))}
        if not ids.issubset(valid):
            raise PlayerError('Auswahl gehört nicht vollständig zu diesem Feed')
        added = 0
        tasks = []
        with downloads.lock:
            for id_ in dict.fromkeys(data.ids):
                if id_ in candidates:
                    task = downloads.start_download(candidates[id_])
                    tasks.append({'id': task['id'], 'status_url': '/api/v1/downloads/' + task['id']})
                    added += 1
        return {'added': added, 'skipped': len(ids) - added, 'tasks': tasks}

    def protected_downloads():
        try:
            _, song = mpd.snapshot()
        except Exception as exc:
            raise MPDUnavailable('Dateinutzung kann nicht geprüft werden: MPD ist nicht erreichbar') from exc
        sources = [song.get('file', '')]
        intro = player.saved.get('intro', {})
        if intro.get('kind') in ('mode', 'custom'):
            sources.append(intro.get('resume', {}).get('song', {}).get('file', ''))
        return {id_ for source in sources if (id_ := downloads.match_url(source))}

    @app.get('/api/v1/feeds/{feed_id}/downloads/completed', response_model=DownloadCleanupPreview)
    def completed_download_preview(feed_id: int):
        if not db.one('SELECT id FROM feeds WHERE id=?', (feed_id,)):
            raise HTTPException(404, 'Podcast nicht gefunden')
        rows = db.rows("SELECT e.id,d.received FROM episodes e JOIN downloads d ON d.episode_id=e.id WHERE e.feed_id=? AND e.completed=1 AND d.state IN ('ready','missing')", (feed_id,))
        return {'count': len(rows), 'bytes': sum(row['received'] for row in rows)}

    @app.delete('/api/v1/feeds/{feed_id}/downloads/completed', response_model=DownloadCleanupResult)
    def delete_completed_downloads(feed_id: int):
        completed_download_preview(feed_id)
        with player.lock, downloads.lock:
            protected = protected_downloads()
            rows = db.rows("SELECT e.id FROM episodes e JOIN downloads d ON d.episode_id=e.id WHERE e.feed_id=? AND e.completed=1 AND d.state IN ('ready','missing')", (feed_id,))
            deleted = skipped = failed = 0
            for row in rows:
                if row['id'] in protected or downloads.browser_in_use(row['id']):
                    skipped += 1
                    continue
                try:
                    downloads.remove_copy(row['id'])
                    deleted += 1
                except (OSError, PlayerError):
                    failed += 1
            return {'deleted': deleted, 'skipped': skipped, 'failed': failed}

    @app.delete("/api/v1/episodes/{episode_id}/download/file")
    def delete_download_file(episode_id: int):
        with player.lock:
            try:
                _, song = mpd.snapshot()
            except Exception as exc:
                raise PlayerError('MPD ist nicht erreichbar; Dateinutzung kann nicht geprüft werden') from exc
            intro = player.saved.get('intro', {})
            resume_url = intro.get('resume', {}).get('song', {}).get('file', '') if intro.get('kind') in ('mode', 'custom') else ''
            if downloads.match_url(song.get('file', '')) == episode_id or downloads.match_url(resume_url) == episode_id:
                raise PlayerError('Diese lokale Datei wird noch von MPD verwendet. Erst die Wiedergabequelle wechseln.')
            downloads.remove_copy(episode_id)
        return {'ok': True}

    @app.post("/api/v1/downloads/cleanup")
    def delete_orphan_downloads():
        with player.lock:
            try:
                _, song = mpd.snapshot()
            except Exception as exc:
                raise PlayerError('MPD ist nicht erreichbar; Dateinutzung kann nicht geprüft werden') from exc
            prefix = downloads.base_url + '/downloads/'
            source = song.get('file', '')
            protected = {source[len(prefix):].split('?', 1)[0].split('#', 1)[0]} if source.startswith(prefix) else set()
            return {'deleted': downloads.remove_orphans(protected)}

    @app.post("/api/v1/episodes/{episode_id}/download", status_code=202, response_model=DownloadAccepted)
    def download_episode(episode_id: int):
        return accepted_download(downloads.start_download(player.episode(episode_id)))

    @app.delete("/api/v1/episodes/{episode_id}/download")
    def cancel_download(episode_id: int):
        downloads.cancel(episode_id)
        return {"ok": True}

    @app.post("/api/v1/media/scan", status_code=202, response_model=JobAccepted)
    def media_scan():
        return accepted_job("media")

    @app.get('/downloads/{id_}')
    @app.head('/downloads/{id_}')
    def download_file(id_: str):
        try:
            path = downloads.file(id_)
        except PlayerError as exc:
            raise HTTPException(404, str(exc)) from exc
        import mutagen
        try:
            audio = mutagen.File(path)
            content_type = audio.mime[0] if audio is not None and audio.mime else "application/octet-stream"
        except (OSError, mutagen.MutagenError):
            raise HTTPException(404, "Audiodatei ist nicht verfügbar")
        return FileResponse(path, media_type=content_type, content_disposition_type="inline",
                            headers={"Cache-Control": "no-cache"})

    @app.get('/media/{episode_id}')
    @app.head('/media/{episode_id}')
    def media_file(episode_id: int):
        try:
            path, stat = media.file(episode_id)
        except MediaError as exc:
            raise HTTPException(404, str(exc)) from exc
        return FileResponse(path, stat_result=stat, media_type=media.content_type(path),
                            filename=path.name, content_disposition_type="inline",
                            headers={"Cache-Control": "no-cache"})

    @app.put('/api/v1/episodes/{episode_id}/hidden')
    def hide_episode(episode_id: int, data: ValueBool):
        ep = player.episode(episode_id)
        if ep.get('feed_kind') not in YOUTUBE_KINDS:
            raise PlayerError('Ausblenden ist nur für YouTube-Sammlungen verfügbar')
        db.execute('UPDATE episodes SET hidden=? WHERE id=?', (data.value, episode_id))
        return {'ok': True}

    @app.put("/api/v1/episodes/{episode_id}/bookmark")
    def bookmark(episode_id: int, data: ValueBool):
        player.episode(episode_id)
        if data.value:
            ep = player.episode(episode_id)
            if ep['source_type'] == 'web': downloads.start_download(ep)
        db.execute("UPDATE episodes SET bookmarked=? WHERE id=?", (data.value, episode_id))
        return {"ok": True}

    @app.put("/api/v1/episodes/{episode_id}/completed")
    def completed(episode_id: int, data: ValueBool):
        with player.lock:
            player.episode(episode_id)
            # A currently playing episode remains controlled by MPD. Set its label only;
            # do not seek it or overwrite an in-flight progress snapshot.
            db.execute("UPDATE episodes SET completed=? WHERE id=?", (data.value, episode_id))
            if not data.value and episode_id != player.saved["episode_id"]:
                db.execute("UPDATE episodes SET position=0,last_started=NULL WHERE id=?", (episode_id,))
        return {"ok": True}

    @app.post('/api/v1/episodes/play', response_model=PlayerResult)
    def play_episode(data: PlayEpisodeInput):
        return player_command(lambda: player.command('episode', timer=data.timer,
                              episode_id=data.episode_id, from_start=data.from_start, when_queue_empty=data.when_queue_empty))

    @app.post("/api/v1/queue", response_model=QueueAddedResult)
    def enqueue(data: EpisodeInput):
        require_mpd()
        added = player.enqueue(data.episode_id)
        return {"added": added, "state": player.state()}

    @app.put("/api/v1/queue/order", response_model=PlayerResult)
    def reorder(data: OrderInput):
        require_mpd()
        player.reorder(data.ids, data.revision)
        return player.state()

    @app.delete("/api/v1/queue", response_model=PlayerResult)
    def clear_queue():
        require_mpd()
        player.remove()
        return player.state()

    @app.delete("/api/v1/queue/{episode_id}", response_model=PlayerResult)
    def remove_queue(episode_id: int):
        require_mpd()
        player.remove(episode_id)
        return player.state()

    @app.post("/api/v1/queue/{episode_id}/retry", response_model=PlayerResult)
    def retry_queue(episode_id: int):
        require_mpd()
        player.retry(episode_id)
        return player.state()

    @app.post("/api/v1/cleanup/checks", status_code=202, response_model=JobAccepted)
    def cleanup():
        return accepted_job("cleanup")

    @app.post("/api/v1/cleanup/delete")
    def cleanup_delete(data: DeleteInput):
        with player.lock:
            # Timeouts are not proof of a permanently missing file. They require explicit
            # additional opt-in from the selection/confirmation dialog, never automatic cleanup.
            availability = "('unreachable','temporary_error')" if data.include_temporary else "('unreachable')"
            valid = {e["id"] for e in db.rows("SELECT id FROM episodes WHERE availability IN " + availability + " AND source_type='audio' AND local_source IS NULL AND NOT EXISTS(SELECT 1 FROM downloads d WHERE d.episode_id=episodes.id AND d.state='ready')")}
            if not set(data.ids).issubset(valid):
                raise PlayerError("Auswahl enthält nicht bestätigte oder lokal verfügbare Episoden")
            player.delete_episodes(data.ids)
        return {"deleted": len(set(data.ids))}

    @app.get("/api/v1/jobs", response_model=list[JobResult])
    def list_jobs():
        return db.rows("SELECT id,kind,state,progress,total,error FROM jobs ORDER BY created DESC LIMIT 20")

    @app.get("/api/v1/jobs/{job_id}", response_model=JobResult)
    def job(job_id: str):
        row = db.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not row:
            raise HTTPException(404, "Auftrag nicht gefunden")
        row["results"] = json.loads(row["results"])
        return row

    @app.put('/api/v1/config/sleep')
    def sleep_defaults(data: SleepDefaultsInput):
        db.put('sleep_defaults', data.model_dump())
        return data.model_dump()

    @app.get("/api/v1/config")
    def config():
        refresh = db.one("SELECT created,finished,state,results FROM jobs WHERE kind='refresh' ORDER BY created DESC,rowid DESC LIMIT 1")
        if refresh:
            refresh['errors'] = sum(r.get('ok') is False for r in json.loads(refresh.pop('results')))
        return {"version": __version__, "sleep_defaults": player.sleep_defaults(),
                "mpd_configured": mpd_configured,
                "mpd": ("connected" if player.status["state"] != "error" else "error") if mpd_configured else "disabled",
                "mqtt": "connected" if notifications.client and notifications.client.is_connected() else "disconnected" if settings.mqtt_host else "disabled",
                "tts": "configured" if settings.tts_audio_url else "disabled",
                "tts_mode": "audio" if settings.tts_audio_url else "disabled", "database": "SQLite",
                "rss_interval": settings.refresh_seconds, "rss_last_refresh": refresh,
                "rss_next_refresh": jobs.next_refresh_at(),
                "rss_scheduler_running": bool(jobs.scheduler and jobs.scheduler.is_alive()), "media_roots": media.roots(),
                "media_base_url": settings.media_base_url, "media_enabled": True}

    from .browser import add_browser_routes
    add_browser_routes(app, db, player, media, downloads)

    static = Path(settings.static_dir)
    if static.is_dir():
        assets = static / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get('/manifest.webmanifest')
    def manifest():
        return FileResponse(static/'manifest.webmanifest',media_type='application/manifest+json',headers={'Cache-Control':'no-cache'})

    @app.get('/manifest-en.webmanifest')
    def english_manifest():
        return FileResponse(static/'manifest-en.webmanifest',media_type='application/manifest+json',headers={'Cache-Control':'no-cache'})

    @app.get('/sw.js')
    def service_worker():
        return FileResponse(static/'sw.js',media_type='application/javascript',headers={'Cache-Control':'no-cache','Service-Worker-Allowed':'/'})

    @app.get('/offline.html')
    def offline():
        return FileResponse(static/'offline.html',media_type='text/html',headers={'Cache-Control':'no-cache'})

    if (static/'icons').is_dir():
        app.mount('/icons',StaticFiles(directory=static/'icons'),name='icons')

    @app.get("/")
    def index():
        file = static / "index.html"
        if not file.exists():
            raise HTTPException(503, "Frontend fehlt: im Verzeichnis frontend npm ci und npm run build ausführen")
        return FileResponse(file, headers={"Cache-Control": "no-cache"})

    return app
