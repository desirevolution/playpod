"""Read-only import and HTTP-source resolution for externally managed audio files."""
import hashlib
import html
import json
import math
import mimetypes
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

import mutagen

from .feeds import safe_html, web_url

AUDIO_EXTENSIONS = {".mp3", ".m4a", ".m4b", ".aac", ".ogg", ".oga", ".opus", ".flac", ".wav", ".aiff", ".aif", ".webm"}
MIME_TYPES = {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".m4b": "audio/mp4", ".aac": "audio/aac", ".ogg": "audio/ogg", ".oga": "audio/ogg", ".opus": "audio/ogg", ".flac": "audio/flac", ".wav": "audio/wav", ".aiff": "audio/aiff", ".aif": "audio/aiff", ".webm": "audio/webm"}


class MediaError(ValueError):
    pass


class MediaLibrary:
    def __init__(self, db, settings):
        self.db, self.settings = db, settings
        self.downloads = None
        self.base_url = settings.media_base_url.rstrip("/")
        if self.base_url:
            web_url(self.base_url)
            parsed = urlsplit(self.base_url)
            if parsed.query or parsed.fragment:
                raise ValueError("MEDIA_BASE_URL darf keine Query oder Fragment enthalten")
        try:
            roots = json.loads(settings.media_roots)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("MEDIA_ROOTS muss ein JSON-Objekt aus Namen und absoluten Pfaden sein") from exc
        if not isinstance(roots, dict):
            raise ValueError("MEDIA_ROOTS muss ein JSON-Objekt sein")
        configured = []
        for key, value in roots.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", key) or not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError("MEDIA_ROOTS: Namen nur Buchstaben/Ziffern/_/-, Pfade müssen absolut sein")
            configured.append((key, str(Path(value))))
        with db.connect() as conn:
            conn.execute("UPDATE media_roots SET enabled=0")
            for key, path in configured:
                conn.execute("INSERT INTO media_roots(root_key,path) VALUES(?,?) ON CONFLICT(root_key) DO UPDATE SET path=excluded.path,enabled=1", (key, path))
                root = conn.execute("SELECT id FROM media_roots WHERE root_key=?", (key,)).fetchone()
                conn.execute("INSERT OR IGNORE INTO feeds(url,title,kind,media_root_id) VALUES(?,?,'local',?)", ("playpod-local://" + key, key, root[0]))
            conn.execute("UPDATE episodes SET source_present=0,availability='local_unconfigured' WHERE url='' AND media_root_id IN (SELECT id FROM media_roots WHERE enabled=0)")

    def roots(self):
        rows = self.db.rows("SELECT r.*,(SELECT COUNT(*) FROM episodes e WHERE e.media_root_id=r.id) AS episode_count FROM media_roots r ORDER BY r.root_key")
        for row in rows:
            row["online"] = bool(row["enabled"] and Path(row["path"]).is_dir())
            row["read_only"] = True
        return rows

    def _path(self, ep):
        root = self.db.one("SELECT * FROM media_roots WHERE id=? AND enabled=1", (ep.get("media_root_id"),))
        if not root or not ep.get("local_source"):
            raise MediaError("Lokales Verzeichnis ist nicht konfiguriert")
        relative = Path(ep["local_source"])
        if relative.is_absolute() or ".." in relative.parts:
            raise MediaError("Ungültiger Medienpfad")
        try:
            base = Path(root["path"]).resolve(strict=True)
            candidate = base / relative
            path = candidate.resolve(strict=True)
            if not path.is_relative_to(base) or candidate.is_symlink() or not path.is_file():
                raise MediaError("Lokale Datei ist nicht verfügbar")
            stat = path.stat()
            if stat.st_size <= 0:
                raise MediaError("Lokale Datei ist leer")
            # Never hand MPD a file currently being overwritten by another downloader.
            if ep.get("file_size") != stat.st_size or ep.get("file_mtime_ns") != stat.st_mtime_ns:
                raise MediaError("Datei wurde geändert. Bitte lokale Medien erneut einlesen.")
            with path.open("rb"):
                pass
            return path, stat
        except (OSError, RuntimeError) as exc:
            raise MediaError("Lokale Datei ist nicht erreichbar") from exc

    def file(self, episode_id):
        ep = self.db.one("SELECT * FROM episodes WHERE id=?", (episode_id,))
        if not ep:
            raise MediaError("Episode nicht gefunden")
        return self._path(ep)

    def playback_url(self, ep):
        if self.downloads and (url := self.downloads.playback_url(ep['id'])):
            return url, "local"
        if ep.get("source_type") == "web":
            raise MediaError("Seitenlink zuerst herunterladen, bevor er abgespielt werden kann")
        if ep.get("local_source"):
            try:
                _, stat = self._path(ep)
                if not self.base_url:
                    raise MediaError("MEDIA_BASE_URL fehlt: interne, für MPD erreichbare PlayPod-Adresse eintragen")
                return f"{self.base_url}/media/{ep['id']}?v={stat.st_mtime_ns}-{stat.st_size}", "local"
            except MediaError:
                if not ep.get("url"):
                    raise
        if ep.get("url"):
            return ep["url"], "remote"
        raise MediaError("Keine verfügbare Wiedergabequelle")

    def match_url(self, value):
        if self.downloads and (id_ := self.downloads.match_url(value)):
            return id_
        prefix = self.base_url + "/media/" if self.base_url else ""
        if prefix and value.startswith(prefix):
            suffix = value[len(prefix):].split("?", 1)[0]
            if suffix.isdigit():
                return int(suffix)
        return None

    @staticmethod
    def metadata(path):
        title, duration, description = path.stem, 0.0, ""
        try:
            audio = mutagen.File(path, easy=True)
            if audio is not None:
                duration = float(audio.info.length)
                if audio.tags:
                    names = audio.tags.get("title")
                    if names:
                        title = str(names[0])
        except (mutagen.MutagenError, ValueError, TypeError, AttributeError):
            pass
        # yt-dlp sidecars are optional and never required for playback. Do not execute
        # their URLs or infer a feed association from similar names.
        sidecar = path.with_suffix(".info.json")
        try:
            if not sidecar.is_symlink() and sidecar.is_file() and sidecar.stat().st_size <= 2 * 1024 * 1024:
                with sidecar.open("rb") as file:
                    raw = file.read(2 * 1024 * 1024 + 1)
                data = json.loads(raw) if len(raw) <= 2 * 1024 * 1024 else {}
                if isinstance(data, dict):
                    if isinstance(data.get("title"), str):
                        title = data["title"]
                    if isinstance(data.get("description"), str):
                        description = "<p>" + html.escape(data["description"]).replace("\n", "<br>") + "</p>"
                    value = data.get("duration")
                    if isinstance(value, (float, int)) and math.isfinite(value) and value > 0:
                        duration = value
        except (OSError, ValueError, TypeError):
            pass
        return title[:1000], duration if math.isfinite(duration) else 0, safe_html(description)

    def scan(self, stop_event, report):
        roots = self.db.rows("SELECT * FROM media_roots WHERE enabled=1 ORDER BY id")
        results = []
        report(0, len(roots), results)
        for root in roots:
            if stop_event.is_set():
                raise RuntimeError("Scan unterbrochen")
            base = Path(root["path"])
            self.db.execute("UPDATE feeds SET last_attempt=? WHERE media_root_id=? AND kind='local'", (time.time(), root["id"]))
            seen, pending, imported, skipped, errors = set(), set(), 0, 0, []
            try:
                if not base.is_dir():
                    raise OSError("Verzeichnis nicht erreichbar")
                base = base.resolve(strict=True)
                files = []
                def walk_error(exc):
                    errors.append(str(exc))
                for directory, directories, names in os.walk(base, followlinks=False, onerror=walk_error):
                    directories[:] = sorted(d for d in directories if not d.startswith(".") and not (Path(directory) / d).is_symlink())
                    for name in sorted(names):
                        if stop_event.is_set():
                            raise RuntimeError("Scan unterbrochen")
                        path = Path(directory) / name
                        if name.startswith(".") or path.suffix.lower() not in AUDIO_EXTENSIONS or path.is_symlink():
                            continue
                        relative = path.relative_to(base).as_posix()
                        seen.add(relative)
                        try:
                            resolved = path.resolve(strict=True)
                            if not resolved.is_relative_to(base) or not resolved.is_file():
                                continue
                            stat = resolved.stat()
                            if not stat.st_size or time.time() - stat.st_mtime < self.settings.media_stable_seconds:
                                pending.add(relative)
                                skipped += 1
                                continue
                            title, duration, description = self.metadata(resolved)
                            after = resolved.stat()
                            if (stat.st_size, stat.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                                pending.add(relative)
                                skipped += 1
                                continue
                            files.append((relative, stat, title, duration, description))
                        except OSError:
                            errors.append(relative)
                with self.db.connect() as conn:
                    feed = conn.execute("SELECT id FROM feeds WHERE kind='local' AND media_root_id=?", (root["id"],)).fetchone()
                    if not feed:
                        raise RuntimeError("Lokaler Katalog fehlt")
                    for relative, stat, title, duration, description in files:
                        key = "local:" + hashlib.sha256(relative.encode()).hexdigest()
                        conn.execute("""INSERT INTO episodes(feed_id,source_key,title,url,description,duration,local_source,media_root_id,file_size,file_mtime_ns,source_present,availability)
                          VALUES(?,?,?,'',?,?,?,?,?,?,1,'local_available')
                          ON CONFLICT(feed_id,source_key) DO UPDATE SET title=excluded.title,description=excluded.description,
                          duration=CASE WHEN excluded.duration>0 THEN excluded.duration ELSE episodes.duration END,
                          file_size=excluded.file_size,file_mtime_ns=excluded.file_mtime_ns,source_present=1,availability='local_available'""",
                          (feed[0], key, title, description, duration, relative, root["id"], stat.st_size, stat.st_mtime_ns))
                        imported += 1
                    for relative in pending:
                        conn.execute("UPDATE episodes SET source_present=0,availability='local_pending' WHERE media_root_id=? AND local_source=? AND url=''", (root["id"], relative))
                    missing = 0
                    # If traversal failed, absence is inconclusive. Preserve existing records.
                    if not errors:
                        for ep in conn.execute("SELECT id,local_source FROM episodes WHERE media_root_id=?", (root["id"],)).fetchall():
                            if ep["local_source"] not in seen:
                                conn.execute("UPDATE episodes SET source_present=0,availability='local_missing' WHERE id=? AND url=''", (ep["id"],))
                                missing += 1
                    message = "Einzelne Dateien/Ordner konnten nicht gelesen werden" if errors else ""
                    conn.execute("UPDATE media_roots SET last_scan=?,error=? WHERE id=?", (time.time(), message, root["id"]))
                    conn.execute("UPDATE feeds SET last_success=CASE WHEN ?='' THEN ? ELSE last_success END,error=? WHERE media_root_id=? AND kind='local'", (message, time.time(), message, root["id"]))
                results.append({"root": root["root_key"], "ok": not errors, "count": imported, "skipped": skipped, "missing": missing, "error": message})
            except OSError:
                message = "Verzeichnis nicht erreichbar oder nicht lesbar"
                self.db.execute("UPDATE media_roots SET error=? WHERE id=?", (message, root["id"]))
                self.db.execute("UPDATE feeds SET error=? WHERE media_root_id=? AND kind='local'", (message, root["id"]))
                self.db.execute("UPDATE episodes SET source_present=0,availability='local_missing' WHERE media_root_id=? AND url=''", (root["id"],))
                results.append({"root": root["root_key"], "ok": False, "count": 0, "error": message})
            report(len(results), len(roots), results)
        return results

    @staticmethod
    def content_type(path):
        return MIME_TYPES.get(path.suffix.lower(), mimetypes.guess_type(path.name)[0] or "application/octet-stream")
