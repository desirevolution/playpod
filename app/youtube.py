"""YouTube catalog subscriptions. Network scans never hold playback/database locks."""
import logging
import time
from urllib.parse import urlsplit, parse_qs

from . import ytdlp
from .activity import record
from .feeds import web_url
from .player import PlayerError

KINDS = ('yt_playlist', 'yt_channel')
log = logging.getLogger(__name__)


def collection_url(url, kind):
    web_url(url)
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
        raise ValueError('Sammlungen benötigen eine YouTube-Adresse')
    if kind == 'yt_playlist':
        key = parse_qs(parsed.query).get('list', [''])[0]
        if not key or not all(c.isalnum() or c in '-_' for c in key):
            raise ValueError('YouTube-Playlistadresse mit list= benötigt')
        return 'https://www.youtube.com/playlist?list=' + key
    parts = parsed.path.strip('/').split('/')
    if parts[0].startswith('@') and len(parts[0]) > 1:
        path = parts[0]
    elif len(parts) >= 2 and parts[0] in ('channel', 'c', 'user') and parts[1]:
        path = '/'.join(parts[:2])
    else:
        raise ValueError('YouTube-Kanaladresse benötigt')
    return 'https://www.youtube.com/' + path + '/videos'


def thumbnail(item):
    images = [item.get('thumbnail')] + [i.get('url') for i in reversed(item.get('thumbnails') or [])]
    for image in images:
        try:
            if image: return web_url(image)
        except ValueError:
            pass
    return ''


def allowed(item):
    url = item.get('webpage_url') or item.get('url') or ''
    return not (item.get('is_live') or
                item.get('live_status') in ('is_live', 'is_upcoming') or
                item.get('media_type') == 'short' or '/shorts/' in url)


class YouTubeCatalog:
    def __init__(self, db, downloads, player):
        self.db, self.downloads, self.player = db, downloads, player

    def add(self, url, kind, limit):
        if not self.downloads.ytdlp_enabled:
            raise PlayerError('yt-dlp ist deaktiviert oder FFmpeg/yt-dlp fehlt')
        url = collection_url(url, kind)
        return self.db.execute('INSERT INTO feeds(url,title,kind,import_limit) VALUES(?,?,?,?)',
                               (url, url, kind, limit))

    def has_copy(self, episode_id):
        row = self.db.one("SELECT id FROM downloads WHERE episode_id=? AND state='ready'", (episode_id,))
        if row:
            try:
                self.downloads.file(row['id'])
                return True
            except PlayerError:
                pass
        return False

    def delete(self, ids):
        """Caller holds player/download locks; cancellation is observed before worker commit."""
        if any(self.downloads.browser_in_use(id_) for id_ in ids):
            raise PlayerError('Ein Download wird im Browser verwendet. Zuerst die Browserwiedergabe freigeben.')
        files = {row['id'] for id_ in ids for row in self.db.rows('SELECT id FROM downloads WHERE episode_id=?', (id_,))}
        self.player.delete_episodes(ids)
        for path, _ in self.downloads.managed_files():
            if path.stem in files:
                path.unlink()

    def refresh(self, feed_id):
        feed = self.db.one('SELECT * FROM feeds WHERE id=?', (feed_id,))
        if not feed or feed['kind'] not in KINDS:
            return 0
        if not self.downloads.ytdlp_enabled:
            raise ValueError('yt-dlp ist deaktiviert')
        self.db.execute('UPDATE feeds SET last_attempt=? WHERE id=?', (time.time(), feed_id))
        snapshot = ytdlp.catalog(feed['url'], self.downloads.ytdlp_timeout, self.downloads.stop)
        entries = snapshot['entries']
        # A fetch must complete before any removals. Unavailable placeholders retain IDs.
        if any(not item.get('id') for item in entries):
            raise ValueError('Unvollständige YouTube-Liste: Eintrag ohne ID')
        seen = {str(item['id']) for item in entries}
        previous = self.db.get(f'yt_seen:{feed_id}')
        previous = set(previous or [])
        existing = {row['source_key']: row for row in self.db.rows('SELECT * FROM episodes WHERE feed_id=?', (feed_id,))}
        eligible = [item for item in entries if allowed(item)]
        def available(item):
            return item.get('availability') not in ('private', 'premium_only', 'subscriber_only', 'needs_auth', 'unavailable') and item.get('title') not in ('[Deleted video]', '[Private video]')
        importable = [item for item in eligible if available(item)]
        skipped = self.db.get(f'yt_skipped:{feed_id}')
        if skipped is None:
            if not existing:
                # Also repair an earlier empty import: "seen" is not proof of import.
                selected = importable if feed['import_limit'] is None else importable[:feed['import_limit']]
                selected_ids = {str(item['id']) for item in selected}
                skipped = {str(item['id']) for item in importable} - selected_ids
            else:
                # Preserve deliberate old initial limits when upgrading populated catalogs.
                skipped = previous - {key.removeprefix('youtube:') for key in existing} if feed['import_limit'] is not None else set()
        skipped = set(skipped) & seen
        added = 0
        with self.player.lock, self.downloads.lock:
            # Deleting a subscription while fetching must not recreate it.
            if not self.db.one('SELECT 1 FROM feeds WHERE id=? AND url=?', (feed_id, feed['url'])):
                return 0
            with self.db.connect() as conn:
                for item in eligible:
                    video_id = str(item['id'])
                    key = 'youtube:' + video_id
                    if key not in existing and video_id in skipped:
                        continue
                    raw_url = item.get('webpage_url') or item.get('url') or ''
                    url = raw_url if raw_url.startswith('https://') else 'https://www.youtube.com/watch?v=' + video_id
                    title = str(item.get('title') or video_id)
                    is_available = available(item)
                    if not is_available and key not in existing:
                        continue
                    if not is_available and key in existing:
                        title = existing[key]['title']
                    published = item.get('timestamp') or item.get('release_timestamp')
                    values = (title, url, thumbnail(item), item.get('duration') or 0, published, int(is_available), 'unchecked' if is_available else 'unreachable')
                    if key in existing:
                        conn.execute('UPDATE episodes SET title=?,url=?,cover=CASE WHEN length(?)>0 THEN ? ELSE cover END,duration=CASE WHEN ?>0 THEN ? ELSE duration END,published=COALESCE(?,published),source_present=?,availability=? WHERE id=?', (title, url, values[2], values[2], values[3], values[3], published, int(is_available), values[6], existing[key]['id']))
                    else:
                        id_ = conn.execute("INSERT INTO episodes(feed_id,source_key,title,url,cover,duration,published,source_present,availability,source_type) VALUES(?,?,?,?,?,?,?,?,?,'web')", (feed_id, key, *values)).lastrowid
                        record(conn, 'episode_added', episode_id=id_)
                        added += 1
                conn.execute("UPDATE feeds SET title=?,cover=?,last_success=?,error='' WHERE id=?", (str(snapshot.get('title') or feed['title']), thumbnail(snapshot), time.time(), feed_id))
            # Missing remote entries remain playable as long as a local copy exists.
            for key, ep in existing.items():
                missing = key.removeprefix('youtube:') not in seen or not self.db.one('SELECT source_present FROM episodes WHERE id=?', (ep['id'],))['source_present']
                if missing:
                    self.db.execute("UPDATE episodes SET source_present=0,availability='unreachable' WHERE id=?", (ep['id'],))
                if missing and not self.has_copy(ep['id']):
                    task = self.db.one('SELECT state FROM downloads WHERE episode_id=?', (ep['id'],))
                    if task and task['state'] in ('queued', 'running', 'cancel_requested'):
                        continue
                    self.player.delete_episodes([ep['id']])
            self.db.put(f'yt_seen:{feed_id}', sorted(seen))
            self.db.put(f'yt_skipped:{feed_id}', sorted(skipped))
            status = {'checked': time.time(), 'found': len(entries), 'eligible': len(importable),
                      'excluded': len(entries) - len(eligible), 'unavailable': len(eligible) - len(importable),
                      'initial_limit_skipped': len(skipped), 'added': added,
                      'stored': self.db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed_id,))['n']}
            self.db.put(f'yt_status:{feed_id}', status)
            log.info('YouTube-Sammlung %s: gefunden=%s geeignet=%s ausgeschlossen=%s nicht_verfügbar=%s Importgrenze=%s neu=%s gespeichert=%s',
                     feed_id, status['found'], status['eligible'], status['excluded'], status['unavailable'], len(skipped), added, status['stored'])
        return added
