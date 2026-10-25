"""Browser catalog/media helpers; never issue MPD commands or alter its queue/timer."""
import time
from typing import Literal
import requests
from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from pydantic import Field
from .contracts import Input
from .player import PlayerError
from .media import MediaError
from .activity import record


class BrowserProgress(Input):
    episode_id: int = Field(gt=0)
    position: float = Field(ge=0, allow_inf_nan=False)
    duration: float = Field(default=0, ge=0, allow_inf_nan=False)
    started: bool = False
    completed: bool = False
    playback_id: str | None = Field(default=None, min_length=1, max_length=100)
    in_use: bool = False


def add_browser_routes(app, db, player, media, downloads):
    @app.get('/api/v1/browser/candidates')
    def candidates(favorites_only: bool = False, selection: Literal['random','random_unheard'] = 'random'):
        return db.rows("""SELECT e.id FROM episodes e JOIN feeds f ON f.id=e.feed_id
            LEFT JOIN media_roots r ON r.id=e.media_root_id
            WHERE (?=0 OR f.favorite=1) AND (?='random' OR e.completed=0)
            AND (e.source_type<>'web' OR EXISTS(SELECT 1 FROM downloads d WHERE d.episode_id=e.id AND d.state='ready'))
            AND (e.url<>'' OR (e.local_source IS NOT NULL AND e.source_present=1 AND r.enabled=1))
            ORDER BY RANDOM()""",(favorites_only,selection))

    @app.get('/api/v1/browser/episodes/{episode_id}/source')
    def source(episode_id: int):
        ep=player.episode(episode_id)
        row=db.one("SELECT id FROM downloads WHERE episode_id=? AND state='ready'",(episode_id,))
        if row:
            try:
                downloads.file(row['id'])
                return {'episode':ep,'url':'/downloads/'+row['id'],'source_kind':'local'}
            except PlayerError:pass
        if ep.get('local_source'):
            try:
                _,stat=media.file(episode_id)
                return {'episode':ep,'url':f'/media/{episode_id}?v={stat.st_mtime_ns}-{stat.st_size}','source_kind':'local'}
            except MediaError:
                if not ep['url']:raise PlayerError('Lokale Datei nicht verfügbar')
        if ep['source_type']=='web':raise PlayerError('YT-Import zuerst herunterladen')
        if not ep['url']:raise PlayerError('Keine Wiedergabequelle verfügbar')
        return {'episode':ep,'url':f'/api/v1/browser/episodes/{episode_id}/stream','source_kind':'remote'}

    @app.put('/api/v1/browser/progress')
    def progress(data: BrowserProgress):
        player.episode(data.episode_id)
        downloads.browser_usage(data.playback_id, data.episode_id, data.in_use and not data.completed)
        # Shared listening metadata; no MPD playback/queue/timer mutation.
        with db.connect() as conn:
            previous = conn.execute('SELECT completed FROM episodes WHERE id=?', (data.episode_id,)).fetchone()
            conn.execute("""UPDATE episodes SET position=?,
            duration=CASE WHEN ?>0 THEN ? ELSE duration END,
            last_started=CASE WHEN ? THEN ? ELSE last_started END,
            completed=CASE WHEN ? THEN 1 WHEN ? THEN 0 ELSE completed END WHERE id=?""",
            (min(data.position,data.duration) if data.duration else data.position,data.duration,data.duration,
             data.started,time.time(),data.completed,data.started,data.episode_id))
            if data.completed and (data.playback_id or not previous[0]):
                key = f'browser:{data.episode_id}:{data.playback_id}' if data.playback_id else None
                record(conn, 'completed', episode_id=data.episode_id, target='browser', key=key)
        return {'ok':True}

    @app.get('/api/v1/browser/episodes/{episode_id}/stream')
    def stream(episode_id: int, request: Request):
        ep=player.episode(episode_id)
        if ep['source_type']=='web' or not ep['url']:
            raise HTTPException(409,'Keine direkte Audioquelle verfügbar')
        headers={'User-Agent':'PlayPod/2.0','Accept-Encoding':'identity'}
        for name in ('Range','If-Range'):
            if request.headers.get(name):headers[name]=request.headers[name]
        try:
            response=requests.get(ep['url'],headers=headers,stream=True,timeout=(5,20))
        except requests.RequestException as exc:
            raise HTTPException(502,'Audioquelle nicht erreichbar') from exc
        if response.status_code not in (200,206,416):
            response.close()
            raise HTTPException(502,'Audioquelle antwortet mit Fehler')
        if 'text/html' in response.headers.get('Content-Type','').lower():
            response.close();raise HTTPException(502,'HTML statt Audio erhalten')
        result_headers={k:v for k,v in response.headers.items() if k.lower() in
                        ('content-type','content-range','accept-ranges','etag','last-modified')}
        result_headers['Cache-Control']='no-cache'
        def chunks():
            try:yield from response.iter_content(64*1024)
            finally:response.close()
        return StreamingResponse(chunks(),status_code=response.status_code,headers=result_headers,
                                 background=BackgroundTask(response.close))
