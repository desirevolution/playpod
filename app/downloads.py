"""Integrated single-download queue. Files and state live with PlayPod."""
import os
import hashlib
import html
import importlib.util
import shutil
import re
from pathlib import Path
import threading
import time
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import mutagen
import requests

from .feeds import web_url
from .media import AUDIO_EXTENSIONS
from .player import PlayerError
from .ytdlp import extract


class Cancelled(Exception):
    pass


class Downloads:
    def __init__(self, db, settings, *, get=requests.get):
        self.db = db
        self.ytdlp_enabled = settings.ytdlp_enabled and importlib.util.find_spec("yt_dlp") is not None and bool(shutil.which("ffmpeg"))
        self.ytdlp_timeout = settings.ytdlp_timeout
        self.base_url = settings.media_base_url.rstrip('/')
        if self.base_url:
            web_url(self.base_url)
            if urlsplit(self.base_url).query or urlsplit(self.base_url).fragment:
                raise ValueError('MEDIA_BASE_URL darf keine Query oder Fragment enthalten')
        self.directory = Path(settings.download_directory or Path(db.path).parent / 'downloads')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.max_bytes, self.get = settings.download_max_bytes, get
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        db.execute("UPDATE feeds SET title='YT-Importe' WHERE url='playpod-links://manual' AND title IN ('Einzelne Links','Linkimporte')")
        db.execute("UPDATE downloads SET state='queued',received=0,total=NULL WHERE state='running'")
        db.execute("UPDATE downloads SET state='cancelled' WHERE state='cancel_requested'")

    def status(self):
        for row in self.db.rows("SELECT id FROM downloads WHERE state='ready'"):
            try:
                self.file(row['id'])
            except PlayerError:
                pass
        items = self.db.rows('SELECT d.*,e.title,e.source_type,f.title AS podcast FROM downloads d JOIN episodes e ON e.id=d.episode_id JOIN feeds f ON f.id=e.feed_id ORDER BY d.updated DESC')
        files = self.managed_files()
        known = {r['id'] for r in self.db.rows('SELECT id FROM downloads')}
        ready = [row for row in items if row['state'] == 'ready']
        return {'enabled': True, 'online': True, 'error': '', 'ytdlp_enabled': self.ytdlp_enabled,
                'storage': {'count': len(ready), 'bytes': sum(r['received'] for r in ready),
                            'free_bytes': shutil.disk_usage(self.directory).free,
                            'orphan_bytes': sum(size for path, size in files if path.stem not in known)},
                'items': items}

    def task(self, id_):
        try:
            if str(UUID(id_)) != id_:
                raise ValueError()
        except (ValueError, TypeError, AttributeError) as exc:
            raise PlayerError('Ungültige Download-ID', code='validation_error', status_code=422) from exc
        row = self.db.one('SELECT * FROM downloads WHERE id=?', (id_,))
        if not row:
            raise PlayerError('Download nicht gefunden', code='not_found', status_code=404)
        return row

    def start_download(self, episode):
        if episode.get('source_type') == 'web' and not self.ytdlp_enabled:
            raise PlayerError('yt-dlp ist deaktiviert oder FFmpeg/yt-dlp fehlt')
        if not episode['url'] or episode.get('local_source'):
            raise PlayerError('Diese Episode ist bereits eine lokale Datei')
        try:
            web_url(episode['url'])
        except ValueError as exc:
            raise PlayerError(str(exc)) from exc
        with self.lock:
            row = self.db.one('SELECT * FROM downloads WHERE episode_id=?', (episode['id'],))
            if row and row['state'] == 'ready':
                try:
                    self.file(row['id'])
                    return row
                except PlayerError:
                    pass
            elif row and row['state'] in ('queued', 'running', 'cancel_requested'):
                return row
            id_ = str(uuid4())
            self.db.execute("""INSERT INTO downloads(episode_id,id,source_url,state,updated)
                VALUES(?,?,?,'queued',?) ON CONFLICT(episode_id) DO UPDATE SET
                id=excluded.id,source_url=excluded.source_url,state='queued',phase='download',received=0,total=NULL,error='',updated=excluded.updated""",
                (episode['id'], id_, episode['url'], time.time()))
            return self.task(id_)

    def add_link(self, url):
        if not self.ytdlp_enabled:
            raise PlayerError('Seitenlinks benötigen aktiviertes yt-dlp mit FFmpeg')
        url = web_url(url).split('#', 1)[0]
        key = 'link:' + hashlib.sha256(url.encode()).hexdigest()
        with self.lock, self.db.connect() as conn:
            conn.execute("INSERT OR IGNORE INTO feeds(url,title,kind) VALUES('playpod-links://manual','YT-Importe','links')")
            feed_id = conn.execute("SELECT id FROM feeds WHERE url='playpod-links://manual'").fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO episodes(feed_id,source_key,title,url,source_type) VALUES(?,?,?,?, 'web')", (feed_id, key, url, url))
            id_ = conn.execute('SELECT id FROM episodes WHERE feed_id=? AND source_key=?', (feed_id, key)).fetchone()[0]
        episode = self.db.one('SELECT * FROM episodes WHERE id=?', (id_,))
        return self.start_download(episode)

    def feed_candidates(self, feed_id):
        feed = self.db.one('SELECT kind FROM feeds WHERE id=?', (feed_id,))
        if not feed or feed['kind'] != 'rss':
            raise PlayerError('Sammeldownload ist nur für RSS-Feeds verfügbar')
        return self.db.rows("""SELECT e.* FROM episodes e LEFT JOIN downloads d ON d.episode_id=e.id
            WHERE e.feed_id=? AND e.last_started IS NULL AND e.completed=0
            AND (d.state IS NULL OR d.state NOT IN ('queued','running','ready','cancel_requested'))
            ORDER BY e.published DESC,e.id DESC""", (feed_id,))

    def managed_files(self):
        result = []
        for path in self.directory.iterdir():
            if path.suffix not in {'.audio', *AUDIO_EXTENSIONS} or path.is_symlink():
                continue
            try:
                if str(UUID(path.stem)) == path.stem and path.is_file():
                    result.append((path, path.stat().st_size))
            except (ValueError, OSError):
                pass
        return result

    def remove_copy(self, episode_id):
        with self.lock:
            row = self.db.one('SELECT * FROM downloads WHERE episode_id=?', (episode_id,))
            if not row or row['state'] not in ('ready', 'missing'):
                raise PlayerError('Keine fertige lokale Kopie vorhanden')
            for path, _ in self.managed_files():
                if path.stem == row['id']:
                    path.unlink()
            self.db.execute("UPDATE downloads SET state='deleted',received=0,total=NULL,error='',updated=? WHERE episode_id=?", (time.time(), episode_id))

    def remove_orphans(self, protected=()):
        with self.lock:
            known = {r['id'] for r in self.db.rows('SELECT id FROM downloads')}
            count = 0
            for path, _ in self.managed_files():
                if path.stem not in known and path.stem not in protected:
                    path.unlink()
                    count += 1
            return count

    def run_web(self, row):
        id_ = row['id']
        folder = self.directory / ('.job-' + id_)
        def report(received, total, phase):
            if received is None:
                self.db.execute('UPDATE downloads SET phase=? WHERE id=?', (phase, id_))
            else:
                self.db.execute('UPDATE downloads SET received=?,total=?,phase=? WHERE id=?', (received, total, phase, id_))
        committed = False
        final = self.directory / (id_ + ".audio")
        try:
            path, metadata = extract(row['source_url'], folder, self.max_bytes, self.ytdlp_timeout,
                                     lambda: self.check_running(id_), report)
            audio = mutagen.File(path)
            if audio is None or not getattr(audio.info, 'length', 0) > 0:
                raise ValueError('yt-dlp hat keine erkennbare Audiodatei erzeugt')
            with self.lock:
                self.check_running(id_)
                size = path.stat().st_size
                path.replace(final)
                title = metadata.get('title') or row['source_url']
                description = '<p>' + html.escape(metadata.get('description') or '').replace('\n','<br>') + '</p>'
                with self.db.connect() as conn:
                    conn.execute('UPDATE episodes SET title=?,description=?,duration=? WHERE id=?',
                                 (title, description, audio.info.length, row['episode_id']))
                    conn.execute("UPDATE downloads SET state='ready',phase='download',received=?,total=?,error='' WHERE id=?", (size, size, id_))
                committed = True
        finally:
            if not committed:
                final.unlink(missing_ok=True)
            shutil.rmtree(folder, ignore_errors=True)

    def cancel(self, episode_id):
        with self.lock:
            row = self.db.one('SELECT * FROM downloads WHERE episode_id=?', (episode_id,))
            if not row or row['state'] not in ('queued', 'running', 'cancel_requested'):
                raise PlayerError('Kein abbrechbarer Download vorhanden')
            state = 'cancelled' if row['state'] == 'queued' else 'cancel_requested'
            self.db.execute('UPDATE downloads SET state=?,updated=? WHERE episode_id=?', (state, time.time(), episode_id))

    def file(self, id_):
        row = self.task(id_)
        if row['state'] != 'ready':
            raise PlayerError('Download ist noch nicht bereit')
        # Also recognize legacy files if copied into this directory.
        for suffix in ('.audio', *sorted(AUDIO_EXTENSIONS)):
            path = self.directory / (id_ + suffix)
            try:
                if path.is_file() and not path.is_symlink() and path.stat().st_size == row['received'] and row['received'] > 0:
                    return path
            except OSError:
                pass
        self.db.execute("UPDATE downloads SET state='missing',error='Lokale Datei fehlt oder wurde geändert' WHERE id=?", (id_,))
        raise PlayerError('Lokale Datei fehlt oder wurde geändert')

    def playback_url(self, episode_id):
        if not self.base_url:
            return None
        row = self.db.one("SELECT id FROM downloads WHERE episode_id=? AND state='ready'", (episode_id,))
        if row:
            try:
                self.file(row['id'])
                return f"{self.base_url}/downloads/{row['id']}"
            except PlayerError:
                pass
        return None

    def match_url(self, url):
        prefix = self.base_url + '/downloads/' if self.base_url else ''
        if prefix and url.startswith(prefix):
            row = self.db.one('SELECT episode_id FROM downloads WHERE id=?', (url[len(prefix):].split('?', 1)[0].split('#', 1)[0],))
            return row['episode_id'] if row else None
        return None

    def check_running(self, id_):
        if self.stop.is_set() or self.task(id_)['state'] != 'running':
            raise Cancelled()

    def run_one(self):
        with self.lock:
            rows = self.db.rows("SELECT d.*,e.source_type FROM downloads d JOIN episodes e ON e.id=d.episode_id WHERE d.state='queued' ORDER BY d.updated LIMIT 1")
            if not rows:
                return False
            row = rows[0]
            id_ = row['id']
            self.db.execute("UPDATE downloads SET state='running',phase='download',received=0,total=NULL,error='' WHERE id=?", (id_,))
        part = self.directory / (id_ + '.part')
        final = None
        try:
            if row['source_type'] == 'web':
                self.run_web(row)
                return True
            with self.get(row['source_url'], stream=True, timeout=(10, 30), headers={'User-Agent': 'PlayPod-Downloader/2', 'Accept-Encoding': 'identity'}) as response:
                response.raise_for_status()
                content_type = response.headers.get('Content-Type', '').split(';')[0].lower().strip()
                if content_type.startswith(('text/', 'application/json', 'application/xhtml')):
                    raise ValueError('Die Quelle liefert keine Audiodatei')
                total = int(response.headers['Content-Length']) if response.headers.get('Content-Length', '').isdigit() else None
                if total is not None and total > self.max_bytes:
                    raise ValueError('Datei überschreitet DOWNLOAD_MAX_BYTES')
                self.db.execute('UPDATE downloads SET total=? WHERE id=?', (total, id_))
                received, last_report = 0, 0
                with part.open('wb') as target:
                    for chunk in response.iter_content(128 * 1024):
                        self.check_running(id_)
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > self.max_bytes:
                            raise ValueError('Datei überschreitet DOWNLOAD_MAX_BYTES')
                        target.write(chunk)
                        if time.monotonic() - last_report >= .5:
                            self.db.execute('UPDATE downloads SET received=? WHERE id=?', (received, id_))
                            last_report = time.monotonic()
                    target.flush()
                    os.fsync(target.fileno())
                if not received or (total is not None and received != total):
                    raise ValueError('Download ist leer oder unvollständig')
                audio = mutagen.File(part)
                if audio is None or not getattr(audio.info, 'length', 0) > 0:
                    raise ValueError('Download enthält keine erkennbare Audiodatei')
                with self.lock:
                    self.check_running(id_)
                    final = self.directory / (id_ + '.audio')
                    part.replace(final)
                    self.db.execute("UPDATE downloads SET state='ready',received=?,error='' WHERE id=?", (received, id_))
        except Cancelled:
            self.db.execute("UPDATE downloads SET state=CASE WHEN state='cancel_requested' THEN 'cancelled' ELSE 'queued' END,received=0,total=NULL WHERE id=? AND state IN ('running','cancel_requested')", (id_,))
        except Exception as exc:
            # Free an incomplete file before persisting a disk-full error.
            part.unlink(missing_ok=True)
            if isinstance(exc, requests.HTTPError):
                message = f'Quelle antwortet mit HTTP {exc.response.status_code}'
            elif isinstance(exc, requests.RequestException):
                message = 'Quelle nicht erreichbar oder Übertragung abgebrochen'
            elif isinstance(exc, OSError):
                message = 'Datei konnte nicht gespeichert werden (Speicherplatz und Rechte prüfen)'
            else:
                message = str(exc)[:300] or 'Audiodatei konnte nicht gelesen werden'
            state = 'queued' if self.stop.is_set() else 'error'
            self.db.execute("UPDATE downloads SET state=?,error=? WHERE id=? AND state='running'", (state, '' if state == 'queued' else message, id_))
            if final is not None:
                final.unlink(missing_ok=True)
        finally:
            part.unlink(missing_ok=True)
            self.db.execute("UPDATE downloads SET state='cancelled' WHERE id=? AND state='cancel_requested'", (id_,))
        return True

    def start(self):
        def loop():
            while not self.stop.is_set():
                if not self.run_one():
                    self.stop.wait(.5)
        self.thread = threading.Thread(target=loop, daemon=True, name='downloads')
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=35)
