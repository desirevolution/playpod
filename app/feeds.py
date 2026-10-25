from concurrent.futures import ThreadPoolExecutor
import calendar
import json
import logging
import threading
import time
from urllib.parse import urljoin, urlsplit
import uuid

import bleach
import feedparser
import requests

log = logging.getLogger(__name__)
AGENT = "PlayPod/2.0 (+self-hosted podcast player)"


def web_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Eine HTTP- oder HTTPS-Adresse ist erforderlich")
    return value


def duration_seconds(raw):
    try:
        pieces = str(raw).split(":")
        seconds = 0.0
        for part in pieces:
            seconds = seconds * 60 + float(part)
        return max(0, seconds)
    except (TypeError, ValueError):
        return 0


def safe_html(text):
    return bleach.clean(text or "", tags={"p", "br", "strong", "em", "ul", "ol", "li", "a", "h2", "h3", "blockquote"}, attributes={"a": ["href", "title"]}, protocols={"http", "https", "mailto"}, strip=True)


class FeedJobs:
    def __init__(self, db, interval=3600, media=None):
        self.db, self.interval = db, interval
        self.media = media
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="feeds")
        self.stop_event = threading.Event()
        self.scheduler = None
        self.refresh_again = False

    def start_job(self, kind, feed_id=None):
        with self.lock:
            # One feed job at a time, to avoid duplicate and conflicting imports.
            existing = self.db.one("SELECT id FROM jobs WHERE kind=? AND state='running'", (kind,))
            if existing:
                if kind == "refresh":
                    # New feeds can be added after the running job took its snapshot.
                    # One follow-up full pass prevents their initial fetch from being lost.
                    self.refresh_again = True
                return existing["id"]
            job_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO jobs(id,kind,state,created) VALUES(?,?,'running',?)", (job_id, kind, time.time()))
            self.executor.submit(self._run, job_id, kind, feed_id)
            return job_id

    def _run(self, job_id, kind, feed_id):
        try:
            if kind == "media":
                def report(progress, total, results):
                    self.db.execute("UPDATE jobs SET progress=?,total=?,results=? WHERE id=?", (progress, total, json.dumps(results), job_id))
                self.media.scan(self.stop_event, report)
                self.db.execute("UPDATE jobs SET state='done',finished=? WHERE id=?", (time.time(), job_id))
                return
            if kind == "refresh":
                rows = self.db.rows("SELECT * FROM feeds WHERE kind='rss'" + (" AND id=?" if feed_id else ""), (feed_id,) if feed_id else ())
            else:
                rows = self.db.rows("SELECT id,url FROM episodes WHERE source_type='audio' AND url<>'' AND NOT EXISTS(SELECT 1 FROM downloads d WHERE d.episode_id=episodes.id AND d.state='ready')")
            self.db.execute("UPDATE jobs SET total=? WHERE id=?", (len(rows), job_id))
            results = []
            for row in rows:
                if self.stop_event.is_set():
                    raise RuntimeError("App wird beendet")
                if kind == "refresh":
                    try:
                        count = self.refresh(row["id"], row["url"])
                        results.append({"id": row["id"], "ok": True, "count": count})
                    except Exception:
                        log.warning("Feed %s konnte nicht aktualisiert werden", row["id"], exc_info=True)
                        message = "Feed nicht erreichbar oder ungültig"
                        self.db.execute("UPDATE feeds SET error=? WHERE id=?", (message, row["id"]))
                        results.append({"id": row["id"], "ok": False, "error": message})
                else:
                    result = self.check(row["url"])
                    self.db.execute("UPDATE episodes SET availability=?,checked_at=?,check_error=? WHERE id=?", (result["status"], time.time(), result["error"], row["id"]))
                    results.append({"id": row["id"], **result})
                self.db.execute("UPDATE jobs SET progress=?,results=? WHERE id=?", (len(results), json.dumps(results), job_id))
            self.db.execute("UPDATE jobs SET state='done',finished=? WHERE id=?", (time.time(), job_id))
        except Exception:
            self.db.execute("UPDATE jobs SET state='failed',error='Auftrag wurde unterbrochen',finished=? WHERE id=?", (time.time(), job_id))
        finally:
            if kind == "refresh":
                with self.lock:
                    again = self.refresh_again
                    self.refresh_again = False
                if again and not self.stop_event.is_set():
                    self.start_job("refresh")

    def refresh(self, feed_id, url):
        self.db.execute("UPDATE feeds SET last_attempt=? WHERE id=?", (time.time(), feed_id))
        with requests.get(url, timeout=(5, 15), headers={"User-Agent": AGENT}, stream=True) as response:
            response.raise_for_status()
            content = bytearray()
            for chunk in response.iter_content(64 * 1024):
                content.extend(chunk)
                if len(content) > 20 * 1024 * 1024:
                    raise ValueError("Feed ist zu groß")
            parsed = feedparser.parse(bytes(content))
            base = response.url
        if not parsed.get("version"):
            raise ValueError("Kein RSS-/Atom-Feed")
        meta = parsed.feed
        image = meta.get("image", {}).get("href", "")
        title = meta.get("title", url)
        normalized = []
        for entry in parsed.entries:
            if entry.get("itunes_episodetype", "full") != "full":
                continue
            enclosure = next((e for e in entry.get("enclosures", []) if e.get("href") and (not e.get("type") or e["type"].startswith("audio/"))), None)
            if not enclosure:
                continue
            media_url = urljoin(base, enclosure["href"])
            try:
                web_url(media_url)
            except ValueError:
                continue
            guid = str(entry.get("id", ""))
            key = "guid:" + guid if guid else "url:" + media_url
            stamp = entry.get("published_parsed") or entry.get("updated_parsed")
            published = calendar.timegm(stamp) if stamp else None
            description = entry.get("content", [{}])[0].get("value") or entry.get("summary", "")
            cover = entry.get("image", {}).get("href", image)
            normalized.append((key, guid, entry.get("title", "Ohne Titel"), media_url, safe_html(description), urljoin(base, cover) if cover else "", published, duration_seconds(entry.get("itunes_duration", 0))))
        with self.db.connect() as db:
            if not db.execute("SELECT 1 FROM feeds WHERE id=? AND url=?", (feed_id, url)).fetchone():
                return 0
            for values in normalized:
                key, guid, title_e, url_e, description, cover_e, published, duration = values
                # A changed/introduced GUID can still refer to the same existing enclosure.
                row = db.execute("SELECT id FROM episodes WHERE feed_id=? AND (source_key=? OR url=?) ORDER BY id LIMIT 1", (feed_id, key, url_e)).fetchone()
                if row:
                    db.execute("UPDATE episodes SET source_key=?,guid=?,title=?,url=?,description=?,cover=?,published=?,duration=CASE WHEN ?>0 THEN ? ELSE duration END WHERE id=?", (*values[:-1], duration, duration, row[0]))
                else:
                    db.execute("INSERT INTO episodes(feed_id,source_key,guid,title,url,description,cover,published,duration) VALUES(?,?,?,?,?,?,?,?,?)", (feed_id, *values))
            db.execute("UPDATE feeds SET title=?,cover=?,last_success=?,error='' WHERE id=?", (title, urljoin(base, image) if image else "", time.time(), feed_id))
        return len(normalized)

    @staticmethod
    def check(url):
        try:
            web_url(url)
            # HEAD can lie or be unsupported; a bounded, streamed GET verifies a response body.
            with requests.get(url, headers={"Range": "bytes=0-1023", "User-Agent": AGENT}, timeout=(5, 10), stream=True) as response:
                code = response.status_code
                if code in (404, 410):
                    return {"status": "unreachable", "error": f"HTTP {code}", "final_url": response.url}
                if not 200 <= code < 300:
                    return {"status": "temporary_error", "error": f"HTTP {code}", "final_url": response.url}
                chunk = next(response.iter_content(1024), b"")
                if not chunk:
                    return {"status": "temporary_error", "error": "Leere Antwort", "final_url": response.url}
                media_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in media_type:
                    return {"status": "temporary_error", "error": "HTML statt Audiodatei erhalten", "final_url": response.url}
                return {"status": "reachable", "error": "", "final_url": response.url}
        except (requests.RequestException, ValueError):
            return {"status": "temporary_error", "error": "Verbindungsfehler oder Zeitüberschreitung", "final_url": url}

    def start_scheduler(self):
        def loop():
            while not self.stop_event.wait(self.interval):
                self.start_job("refresh")
        self.scheduler = threading.Thread(target=loop, daemon=True)
        self.scheduler.start()

    def close(self):
        self.stop_event.set()
        if self.scheduler:
            self.scheduler.join(timeout=1)
        self.executor.shutdown(wait=True, cancel_futures=True)
