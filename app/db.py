from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
CREATE TABLE IF NOT EXISTS feeds(
 id INTEGER PRIMARY KEY, url TEXT NOT NULL UNIQUE, title TEXT NOT NULL DEFAULT '',
 favorite INTEGER NOT NULL DEFAULT 0, cover TEXT NOT NULL DEFAULT '',
 last_attempt REAL, last_success REAL, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS episodes(
 id INTEGER PRIMARY KEY, feed_id INTEGER NOT NULL REFERENCES feeds(id) ON DELETE CASCADE,
 source_key TEXT NOT NULL, guid TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
 url TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', cover TEXT NOT NULL DEFAULT '',
 published REAL, duration REAL NOT NULL DEFAULT 0, position REAL NOT NULL DEFAULT 0,
 last_started REAL, completed INTEGER NOT NULL DEFAULT 0, bookmarked INTEGER NOT NULL DEFAULT 0,
 availability TEXT NOT NULL DEFAULT 'unchecked', checked_at REAL, check_error TEXT NOT NULL DEFAULT '',
 local_source TEXT, UNIQUE(feed_id,source_key));
CREATE INDEX IF NOT EXISTS episodes_feed ON episodes(feed_id);
CREATE INDEX IF NOT EXISTS episodes_url ON episodes(url);
CREATE INDEX IF NOT EXISTS episodes_played ON episodes(last_started);
CREATE TABLE IF NOT EXISTS queue(
 episode_id INTEGER PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
 rank INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
 total INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', created REAL NOT NULL,
 finished REAL, results TEXT NOT NULL DEFAULT '[]');
"""

MIGRATION_2 = [
    "CREATE TABLE media_roots(id INTEGER PRIMARY KEY,root_key TEXT NOT NULL UNIQUE,path TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,last_scan REAL,error TEXT NOT NULL DEFAULT '')",
    "ALTER TABLE feeds ADD COLUMN kind TEXT NOT NULL DEFAULT 'rss'",
    "ALTER TABLE feeds ADD COLUMN media_root_id INTEGER REFERENCES media_roots(id)",
    "ALTER TABLE episodes ADD COLUMN media_root_id INTEGER REFERENCES media_roots(id)",
    "ALTER TABLE episodes ADD COLUMN file_size INTEGER",
    "ALTER TABLE episodes ADD COLUMN file_mtime_ns INTEGER",
    "ALTER TABLE episodes ADD COLUMN source_present INTEGER NOT NULL DEFAULT 1",
    "CREATE INDEX episodes_media_root ON episodes(media_root_id)",
]


class Database:
    def __init__(self, path):
        path = str(path)
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 4:
                raise RuntimeError("Diese Datenbank benötigt eine neuere PlayPod-Version.")
            if version == 0:
                db.executescript(SCHEMA)
                db.execute("INSERT OR IGNORE INTO schema_migrations VALUES(1)")
                db.execute("PRAGMA user_version=1")
                db.commit()
            if version < 2:
                # Upgrade existing legacy databases in place, with a consistent backup first.
                if version == 1:
                    backup = Path(path + ".before-v2.sqlite3")
                    if not backup.exists():
                        dest = sqlite3.connect(backup)
                        try:
                            db.backup(dest)
                        finally:
                            dest.close()
                db.execute("BEGIN IMMEDIATE")
                for statement in MIGRATION_2:
                    db.execute(statement)
                db.execute("INSERT INTO schema_migrations VALUES(2)")
                db.execute("PRAGMA user_version=2")
                db.commit()
            if version < 3:
                if version in (1, 2):
                    backup = Path(path + ".before-v3.sqlite3")
                    if not backup.exists():
                        dest = sqlite3.connect(backup)
                        try:
                            db.backup(dest)
                        finally:
                            dest.close()
                db.execute("BEGIN IMMEDIATE")
                db.execute("""CREATE TABLE downloads(
                    episode_id INTEGER PRIMARY KEY REFERENCES episodes(id) ON DELETE CASCADE,
                    id TEXT NOT NULL UNIQUE, source_url TEXT NOT NULL, state TEXT NOT NULL, received INTEGER NOT NULL DEFAULT 0,
                    total INTEGER, error TEXT NOT NULL DEFAULT '', updated REAL NOT NULL)""")
                db.execute("INSERT INTO schema_migrations VALUES(3)")
                db.execute("PRAGMA user_version=3")
                db.commit()
            if version < 4:
                if version > 0:
                    backup = Path(path + ".before-v4.sqlite3")
                    if not backup.exists():
                        dest = sqlite3.connect(backup)
                        try:
                            db.backup(dest)
                        finally:
                            dest.close()
                db.execute("BEGIN IMMEDIATE")
                db.execute("ALTER TABLE episodes ADD COLUMN source_type TEXT NOT NULL DEFAULT 'audio'")
                db.execute("ALTER TABLE downloads ADD COLUMN phase TEXT NOT NULL DEFAULT 'download'")
                db.execute("INSERT INTO schema_migrations VALUES(4)")
                db.execute("PRAGMA user_version=4")
                db.commit()
            # A killed refresh/cleanup job cannot resume halfway; results remain inspectable.
            db.execute("UPDATE jobs SET state='interrupted',error='App wurde neu gestartet' WHERE state='running'")

    @contextmanager
    def connect(self):
        # Only local, short SQL transactions. Network operations never hold this lock.
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.create_function('casefold', 1, lambda s: (s or '').casefold(), deterministic=True)
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA busy_timeout=10000")
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def rows(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args).fetchall()]

    def one(self, sql, args=()):
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql, args=()):
        with self.connect() as db:
            return db.execute(sql, args).lastrowid

    def get(self, key, default=None):
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def put(self, key, value):
        self.execute("INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))

    def backup(self, target):
        with self.connect() as source:
            dest = sqlite3.connect(target)
            try:
                source.backup(dest)
            finally:
                dest.close()
