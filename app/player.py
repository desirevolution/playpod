"""Serialized, server-side playback control. MPD I/O never runs in SQL transactions."""
import logging
import threading
import time
import uuid
from .activity import record
from copy import deepcopy

log = logging.getLogger(__name__)
DEFAULT_TIMER_SECONDS = 15 * 60
MPD_RECONCILE_SECONDS = 30


class PlayerError(Exception):
    def __init__(self, message, *, code='state_conflict', status_code=409):
        super().__init__(message)
        self.code, self.status_code = code, status_code


class MPDUnavailable(PlayerError):
    def __init__(self, message):
        super().__init__(message, code='mpd_unavailable', status_code=503)


class Player:
    def __init__(self, db, mpd, notifications, clock=time.time, media=None):
        self.db, self.mpd, self.notifications, self.clock = db, mpd, notifications, clock
        self.media = media
        self.lock = threading.RLock()
        self.saved = db.get("playback", {"episode_id": None, "song_id": None, "run_active": False,
            "timer_seconds": 0, "remaining": 0, "deadline": None, "when_queue_empty": "stop"})
        if 'when_queue_empty' not in self.saved:
            active = self.saved.get('run_active') or self.saved.get('intro')
            self.saved['when_queue_empty'] = 'random_unheard' if active else 'stop'
            if not active:
                self.saved.update(timer_seconds=0, remaining=0, deadline=None)
        self.mode = db.get("favorites_only", False)
        self.revision = db.get("queue_revision", 0)
        self.status = {"state": "error", "elapsed": 0, "duration": 0, "volume": -1}
        self.error = "Verbindung zu MPD wird aufgebaut"
        self.last_song = {}
        self.previous_state = None
        self.previous_elapsed = 0
        self.previous_duration = 0
        self.last_checkpoint = 0
        self.undo = None
        self.stop_event = threading.Event()
        self.thread = None
        self.monitor_wake = threading.Event()
        self.announcement_lock = threading.Lock()
        self.announcement_wake = threading.Event()
        self.announcement_thread = None
        self.announcements = db.get('announcement_jobs', [])
        active_job = self.saved.get('intro', {}).get('announcement_id')
        for job in self.announcements:
            if job['state'] == 'generating':
                job['state'] = 'queued'
            elif job['state'] == 'playing' and job['id'] != active_job:
                # Startup interrupted the handoff before a return context was saved.
                job['state'] = 'queued'
        if self.announcements:
            self._save_announcements()

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self.status_at = self.clock()

    def _elapsed(self):
        elapsed = self.status.get('elapsed', 0)
        if self.status['state'] == 'play':
            elapsed += max(0, self.clock() - self.status_at)
        duration = self.status.get('duration', 0)
        return min(duration, elapsed) if duration else elapsed

    def episode(self, episode_id):
        row = self.db.one("SELECT e.*,f.title AS podcast,f.favorite,f.cover AS feed_cover FROM episodes e JOIN feeds f ON f.id=e.feed_id WHERE e.id=?", (episode_id,))
        if not row:
            raise PlayerError("Episode nicht gefunden", code='not_found', status_code=404)
        return row

    def queue(self):
        return self.db.rows("SELECT e.*,f.title AS podcast,f.cover AS feed_cover,q.rank,q.error AS queue_error FROM queue q JOIN episodes e ON e.id=q.episode_id JOIN feeds f ON f.id=e.feed_id ORDER BY q.rank,e.id")

    def persist(self):
        self.db.put("playback", self.saved)

    def remaining(self):
        if self.saved["deadline"] is not None:
            return max(0, self.saved["deadline"] - self.clock())
        return self.saved["remaining"]

    def _timer_suspended(self):
        intro = self.saved.get('intro')
        return bool(intro and (intro.get('kind') in ('mode', 'custom') or intro.get('restart_timer')))

    def state(self):
        with self.lock:
            ep = None
            intro = self.saved.get("intro")
            current_id = intro["episode_id"] if intro else self.saved["episode_id"]
            if current_id:
                try:
                    ep = self.episode(current_id)
                except PlayerError:
                    pass
            restorable_announcement = bool(intro and intro.get('kind') in ('mode', 'custom'))
            return {**self.status, "phase": "announcement" if intro else "episode",
                    "announcement_kind": intro.get('kind', 'title') if intro else None,
                    "announcement_text": intro.get('text', ep['title'] if ep else '') if intro else '',
                    "elapsed": intro["position"] if intro else self._elapsed(),
                    "duration": ep["duration"] if intro and ep else intro.get('display_duration', 0) if restorable_announcement else self.status["duration"],
                    "current": ep, "queue": self.queue(), "revision": self.revision,
                    "source_kind": intro["source_kind"] if intro else self.saved.get("source_kind", "remote"),
                    "favorites_only": self.mode, "error": self.error,
                    "undo_available": self.undo is not None,
                    "when_queue_empty": self.saved['when_queue_empty'],
                    "sleep_mode": self.saved['timer_seconds'] > 0 and self.saved['when_queue_empty'] != 'stop',
                    "timer": {"enabled": self.saved["timer_seconds"] > 0,
                              "minutes": self.saved["timer_seconds"] / 60,
                              "remaining": self.remaining(), "run_active": self.saved["run_active"],
                              "suspended": self._timer_suspended()}}

    def _queue_changed(self):
        self.revision += 1
        self.db.put("queue_revision", self.revision)
        self.undo = None

    def enqueue(self, episode_id):
        with self.lock:
            self.episode(episode_id)
            if self.db.one("SELECT 1 FROM queue WHERE episode_id=?", (episode_id,)):
                return False
            self.db.execute("INSERT INTO queue(episode_id,rank) VALUES(?,(SELECT COALESCE(MAX(rank),0)+1 FROM queue))", (episode_id,))
            self._queue_changed()
            return True

    def reorder(self, ids, revision):
        with self.lock:
            if revision != self.revision:
                raise PlayerError("Warteschlange wurde inzwischen geändert. Bitte erneut versuchen.")
            existing = [e["id"] for e in self.queue()]
            if len(ids) != len(set(ids)) or set(ids) != set(existing):
                raise PlayerError("Ungültige Warteschlangenreihenfolge")
            with self.db.connect() as db:
                db.executemany("UPDATE queue SET rank=? WHERE episode_id=?", enumerate(ids))
            self._queue_changed()

    def remove(self, episode_id=None):
        with self.lock:
            if episode_id is None:
                self.db.execute("DELETE FROM queue")
            else:
                self.db.execute("DELETE FROM queue WHERE episode_id=?", (episode_id,))
            self._queue_changed()

    def retry(self, episode_id):
        with self.lock:
            self.db.execute("UPDATE queue SET error='' WHERE episode_id=?", (episode_id,))
            self._queue_changed()

    def sleep_defaults(self):
        return self.db.get('sleep_defaults', {'minutes': 15, 'when_queue_empty': 'random_unheard'})

    def _begin_run(self, *, preserve_timer=False):
        self.saved['run_active'] = True
        self.saved.pop('preset_pending', None)

    def _restart_sleep_timer(self):
        """A manual start/resume restarts the selected period, including timer-off."""
        self.saved.update(remaining=self.saved['timer_seconds'], deadline=None)
        intro = self.saved.get('intro')
        if intro:
            target = intro['resume']['playback'].get('intro') if intro.get('kind') in ('mode', 'custom') else intro
            if target:
                target['restart_timer'] = True

    def _freeze(self):
        self.saved["remaining"] = self.remaining()
        self.saved["deadline"] = None

    def _checkpoint(self, *, estimate=False):
        if self.saved.get("intro"):
            return
        episode_id = self.saved["episode_id"]
        if episode_id and self.last_song and self.status["state"] != "error":
            elapsed = self._elapsed() if estimate else self.status.get('elapsed', 0)
            duration = self.status.get("duration", 0)
            self.db.execute("UPDATE episodes SET position=?,duration=CASE WHEN ?>0 THEN ? ELSE duration END WHERE id=?", (elapsed, duration, duration, episode_id))

    def _read(self):
        status, song = self.mpd.snapshot()
        return {"state": status.get("state", "stop"), "elapsed": float(status.get("elapsed", 0)),
                "duration": float(status.get("duration", 0)), "volume": int(status.get("volume", -1)),
                "mpd_error": status.get("error", "")}, song

    def _adopt(self, status, song):
        # External MPD clients may change the song. Never save their position onto the old episode.
        file = song.get("file", "")
        matched = self.db.one("SELECT id FROM episodes WHERE url=? ORDER BY id LIMIT 1", (file,)) if file else None
        if file and file == self.saved.get("source_url") and self.saved["episode_id"]:
            matched = self.db.one("SELECT id FROM episodes WHERE id=?", (self.saved["episode_id"],))
        elif file and self.media and (local_id := self.media.match_url(file)):
            matched = self.db.one("SELECT id FROM episodes WHERE id=?", (local_id,))
        episode_id = matched["id"] if matched else None
        if episode_id != self.saved["episode_id"]:
            # A cancelled announcement restores metadata only; its interrupted
            # source was paused and must not gain any estimated playback time.
            self._checkpoint(estimate=self.previous_state is not None)
            self.saved["episode_id"] = episode_id
            self.saved['activity_run'] = uuid.uuid4().hex
            self.saved["song_id"] = song.get("id")
            self.saved["source_url"] = file
            self.saved["source_kind"] = "local" if self.media and self.media.match_url(file) else "remote"
            self.undo = None
            if episode_id and status["state"] == "play":
                self.db.execute("UPDATE episodes SET last_started=?,completed=0 WHERE id=?", (self.clock(), episode_id))
            self.persist()

    def sync(self):
        with self.lock:
            try:
                status, song = self._read()
                if self.saved.get("intro") and self._sync_intro(status, song):
                    self.notifications.publish(self.status["state"])
                    return
                ended = (status["state"] == "stop" and self.previous_state == "play"
                         and self.previous_duration > 0 and self._elapsed() >= self.previous_duration - 2
                         and not status["mpd_error"] and self.saved["episode_id"] is not None
                         and (not song or song.get("file") == self.last_song.get("file")))
                if not ended:
                    self._adopt(status, song)
                else:
                    # MPD may reset elapsed or clear currentsong on EOF. Preserve the final
                    # position before start_episode checkpoints the outgoing episode.
                    status["elapsed"] = self.previous_duration
                    song = self.last_song
                self.status, self.last_song, self.error = status, song, ""
                # Retain an elapsed deadline through outages. The pause is retried until successful.
                expired = self.saved["deadline"] is not None and self.remaining() <= 0
                if expired:
                    if status["state"] == "play":
                        self.mpd.call("pause", 1)
                    self.status["state"] = "pause" if song else "stop"
                    self.saved.update(run_active=False, remaining=0, deadline=None)
                    self._checkpoint()
                    self.persist()
                elif status["state"] == "pause" and self.saved["deadline"] is not None:
                    self._freeze()
                    self.persist()
                elif status["state"] == "play" and self.saved["deadline"] is None:
                    resumed = self.previous_state in ('pause', 'stop')
                    self._begin_run(preserve_timer=resumed)
                    if resumed:
                        self._restart_sleep_timer()
                    if self.saved["timer_seconds"] > 0:
                        self.saved["deadline"] = self.clock() + self.saved["remaining"]
                    self.persist()
                # A natural end must be observed at the end of the SAME episode, without an MPD error.
                if ended and not expired:
                    ep = self.saved["episode_id"]
                    with self.db.connect() as conn:
                        conn.execute("UPDATE episodes SET completed=1,position=duration WHERE id=?", (ep,))
                        run = self.saved.setdefault('activity_run', uuid.uuid4().hex)
                        record(conn, 'completed', episode_id=ep, target='mpd', key=f'mpd:{ep}:{run}')
                    self._advance(natural=True)
                elif status["mpd_error"] and self.previous_state == "play" and not expired:
                    ep = self.saved["episode_id"]
                    if ep and not self.db.one("SELECT 1 FROM queue WHERE episode_id=?", (ep,)):
                        self.db.execute("INSERT INTO queue VALUES(?, -1, ?)", (ep, status["mpd_error"]))
                        self._queue_changed()
                    self.error = "MPD konnte die aktuelle Episode nicht abspielen."
                    self._advance(natural=True)
                elif status["state"] == "stop" and self.saved["run_active"]:
                    self._freeze()
                    self.saved["run_active"] = False
                    self.persist()
                if self.clock() - self.last_checkpoint >= 5 and self.status["state"] in ("play", "pause"):
                    self._checkpoint()
                    self.last_checkpoint = self.clock()
                self.previous_state = self.status["state"]
                self.previous_elapsed = self.status["elapsed"]
                self.previous_duration = self.status["duration"]
            except Exception as exc:
                self.status["state"] = "error"
                self.error = str(exc) if isinstance(exc, PlayerError) else "MPD nicht erreichbar oder Befehl fehlgeschlagen"
                log.warning("MPD-Abgleich oder Wiedergabeübergang fehlgeschlagen", exc_info=True)
            self.notifications.publish(self.status["state"])

    def start_episode(self, episode_id, from_start=False, *, announce=True, position_override=None, restart_timer=False):
        with self.lock:
            if self.saved.get('intro', {}).get('kind') in ('mode', 'custom'):
                self._interrupt_announcement()
            self._checkpoint()
            ep = self.episode(episode_id)
            position = position_override if position_override is not None else (0 if from_start or ep["completed"] else ep["position"])
            source_url, source_kind = ep["url"], "remote"
            if self.media:
                try:
                    source_url, source_kind = self.media.playback_url(ep)
                except ValueError as exc:
                    raise PlayerError(str(exc)) from exc
            # Await the HTTP response before starting either the local or remote source.
            audio_url = self.notifications.title_audio(ep["title"]) if announce else None
            # Automatic transitions retain their deadline, including TTS generation.
            # A manual wake action instead starts a new period at confirmed playback.
            if not restart_timer and self.saved["deadline"] is not None and self.remaining() <= 0:
                if self.status["state"] == "play":
                    self.mpd.call("pause", 1)
                self._freeze()
                self.saved.update(run_active=False, remaining=0)
                self.status["state"] = "pause" if self.last_song else "stop"
                self.persist()
                return
            def start_source(url, at=None):
                song_id = self.mpd.start(url, position if at is None else at)
                status, song = self._read()
                # MPD may still be buffering. Do not mark started before observing play.
                end = time.monotonic() + 2
                while status["state"] != "play" and not status["mpd_error"] and time.monotonic() < end:
                    time.sleep(.1)
                    status, song = self._read()
                if status["state"] != "play" or status["mpd_error"]:
                    raise PlayerError("MPD konnte die Episode nicht starten")
                return song_id, status, song

            if audio_url:
                try:
                    song_id, status, song = start_source(audio_url, 0)
                except Exception:
                    log.warning('MPD konnte die Titelansage nicht starten; Episode wird direkt versucht')
                else:
                    timeout = getattr(getattr(self.notifications, 'settings', None), 'tts_playback_timeout_seconds', 120)
                    self.saved.update(episode_id=None, song_id=song_id, source_url=audio_url, source_kind='announcement',
                        intro={'episode_id': episode_id, 'position': position, 'source_kind': source_kind,
                               'restart_timer': restart_timer,
                               'url': audio_url, 'timeout_remaining': timeout, 'timeout_at': self.clock() + timeout})
                    if restart_timer:
                        self._restart_sleep_timer()
                    self.undo = None
                    self.status, self.last_song, self.error = status, song, ''
                    self.previous_state, self.previous_elapsed, self.previous_duration = status['state'], status['elapsed'], status['duration']
                    self.persist()
                    self.notifications.publish('play')
                    return
            try:
                try:
                    song_id, status, song = start_source(source_url)
                except Exception:
                    if source_kind != "local" or not ep["url"] or ep.get("source_type") == "web":
                        raise
                    # A missing file or an unreachable local source must not prevent
                    # streaming a feed episode. Keep its identity and saved position.
                    self.mpd.snapshot()
                    source_url, source_kind = ep["url"], "remote"
                    song_id, status, song = start_source(source_url)
            except Exception as exc:
                try:
                    self.mpd.snapshot()
                except Exception as connection_error:
                    raise MPDUnavailable("MPD ist nicht erreichbar. Warteschlange bleibt unverändert.") from connection_error
                raise PlayerError("Episode konnte nicht gestartet werden") from exc
            self.saved.pop("intro", None)
            self._begin_run(preserve_timer=restart_timer)
            if restart_timer:
                self._restart_sleep_timer()
            if self.saved["deadline"] is None and self.saved["timer_seconds"]:
                self.saved["deadline"] = self.clock() + self.saved["remaining"]
            self.saved.update(episode_id=episode_id, song_id=song_id, source_url=source_url, source_kind=source_kind)
            self.saved['activity_run'] = uuid.uuid4().hex
            self.db.execute("UPDATE episodes SET last_started=?,completed=0,position=? WHERE id=?", (self.clock(), position, episode_id))
            if self.db.one("SELECT 1 FROM queue WHERE episode_id=?", (episode_id,)):
                self.db.execute("DELETE FROM queue WHERE episode_id=?", (episode_id,))
                self._queue_changed()
            self.undo = None
            self.status, self.last_song, self.error = status, song, ""
            self.previous_state = "play"
            self.previous_elapsed, self.previous_duration = status["elapsed"], status["duration"]
            self.persist()
            self.notifications.publish("play")

    def _sync_intro(self, status, song):
        intro = self.saved['intro']
        file = song.get('file', '')
        if (intro.get('kind') in ('mode', 'custom') and intro.get('restoring')
                and (not file or file in (intro['url'], intro['resume']['song'].get('file')))):
            # A restore may have selected the original source before a connection failed.
            # Complete it instead of mistaking our own selection for an external change.
            self._finish_announcement()
            return True
        if file and file != intro['url']:
            # Another MPD client selected a source. Cancel the pending transition.
            if intro.get('kind') in ('mode', 'custom'):
                if intro.get('kind') == 'custom':
                    self._cancel_announcements()
                self._restore_announcement_metadata(intro)
                # The external source also supersedes any interrupted title announcement.
            self.saved.pop('intro', None)
            self.previous_state = None
            self.persist()
            return False
        if intro.get('kind') == 'custom' and intro.get('waiting_next'):
            self.status, self.last_song, self.error = status, song, ''
            self.announcement_wake.set()
            return True
        self.status, self.last_song, self.error = status, song, ''
        if status['state'] == 'play' and self.previous_state == 'pause' and intro.get('kind') != 'custom':
            self._restart_sleep_timer()
        expired = self.saved['deadline'] is not None and self.remaining() <= 0
        if expired:
            if status['state'] == 'play':
                self.mpd.call('pause', 1)
            self.status['state'] = 'pause' if song else 'stop'
            self.saved.update(run_active=False, remaining=0, deadline=None)
        if self.status['state'] != 'play' and intro['timeout_at'] is not None:
            intro['timeout_remaining'] = max(0, intro['timeout_at'] - self.clock())
            intro['timeout_at'] = None
        if self.status['state'] == 'pause' and self.saved['deadline'] is not None:
            self._freeze()
        if status['mpd_error'] and not expired:
            if intro.get('kind') == 'custom':
                self._end_announcement_job(intro.get('announcement_id'), 'failed', 'MPD konnte die Ansage nicht abspielen')
            log.warning('Ansage mit MPD-Fehler beendet; Wiedergabeübergang wird ausgeführt')
            self._finish_intro()
            return True
        # An accepted custom queue can finish its interrupted handoff after restart.
        ended = status['state'] == 'stop' and (self.previous_state == 'play' or (intro.get('kind') == 'custom' and self.previous_state is None))
        if status['state'] == 'play' and not expired:
            if intro['timeout_at'] is None:
                intro['timeout_at'] = self.clock() + intro['timeout_remaining']
            if intro.get('kind') not in ('mode', 'custom') and not intro.get('restart_timer') and self.saved['run_active'] and self.saved['timer_seconds'] and self.saved['deadline'] is None:
                self.saved['deadline'] = self.clock() + self.saved['remaining']
            if self.clock() >= intro['timeout_at']:
                if intro.get('kind') == 'custom':
                    self._end_announcement_job(intro.get('announcement_id'), 'failed', 'Zeitlimit der Ansage erreicht')
                log.warning('Zeitlimit der Ansage erreicht; Wiedergabeübergang wird ausgeführt')
                self._finish_intro()
                return True
        if ended and not expired:
            self._finish_intro()
            return True
        self.previous_state = self.status['state']
        self.previous_elapsed, self.previous_duration = status['elapsed'], status['duration']
        self.persist()
        return True

    def _finish_intro(self):
        intro = self.saved['intro']
        if intro.get('kind') in ('mode', 'custom'):
            self._finish_announcement()
            return
        if self.status['state'] in ('play', 'pause'):
            self.mpd.call('stop')
        self.saved.pop('intro')
        self.saved.update(episode_id=None, song_id=None, source_url=None)
        self.status.update(state='stop', elapsed=0, duration=0)
        self.last_song = {}
        self.previous_state = 'stop'
        self.persist()
        try:
            self.start_episode(intro['episode_id'], announce=False, position_override=intro['position'],
                               restart_timer=intro.get('restart_timer', False))
        except MPDUnavailable:
            raise
        except PlayerError:
            if self.db.one('SELECT 1 FROM episodes WHERE id=?', (intro['episode_id'],)):
                self.db.execute("INSERT INTO queue(episode_id,rank,error) VALUES(?,-1,'Episode konnte nicht gestartet werden') ON CONFLICT(episode_id) DO UPDATE SET error=excluded.error", (intro['episode_id'],))
                self._queue_changed()
            self._advance(natural=True, restart_timer=intro.get('restart_timer', False))

    def random_episode(self, exclude=()):
        scope = " AND f.favorite=1" if self.mode else ""
        if self.saved['when_queue_empty'] == 'random_unheard':
            scope += ' AND e.completed=0'
        args = ()
        # Avoid the current episode if there are alternatives; a single-episode library can repeat.
        base = """SELECT e.* FROM episodes e JOIN feeds f ON f.id=e.feed_id
                  LEFT JOIN media_roots r ON r.id=e.media_root_id
                  WHERE (e.source_type<>'web' OR EXISTS(SELECT 1 FROM downloads d WHERE d.episode_id=e.id AND d.state='ready'))
                  AND (e.url<>'' OR (e.local_source IS NOT NULL AND e.source_present=1 AND r.enabled=1))""" + scope
        rows = [r for r in self.db.rows(base + " ORDER BY RANDOM()", args) if r["id"] not in exclude]
        return next((e for e in rows if e["id"] != self.saved["episode_id"]), rows[0] if rows else None)

    def _advance(self, natural=False, *, restart_timer=False):
        failures = []
        def timer_expired():
            if restart_timer or self.saved["deadline"] is None or self.remaining() > 0:
                return False
            if self.status["state"] == "play":
                self.mpd.call("pause", 1)
            self._freeze()
            self.saved.update(run_active=False, remaining=0)
            self.status["state"] = "pause"
            self.persist()
            return True
        if timer_expired():
            return
        for ep in self.queue():
            if timer_expired():
                return
            if ep["queue_error"]:
                failures.append(ep["id"])
                continue
            try:
                self.start_episode(ep["id"], restart_timer=restart_timer)
                return
            except MPDUnavailable:
                raise
            except PlayerError:
                self.db.execute("UPDATE queue SET error='Episode konnte nicht gestartet werden' WHERE episode_id=?", (ep["id"],))
                self._queue_changed()
                failures.append(ep["id"])
        # Natural EOF and explicit Next share the same queue-then-random policy.
        for _ in range(5 if self.saved['when_queue_empty'] != 'stop' else 0):
            if timer_expired():
                return
            ep = self.random_episode(failures)
            if not ep:
                break
            try:
                self.start_episode(ep["id"], from_start=True, restart_timer=restart_timer)
                return
            except MPDUnavailable:
                raise
            except PlayerError:
                failures.append(ep["id"])
        if not natural:
            raise PlayerError("Keine abspielbare Episode vorhanden")
        self.saved["run_active"] = False
        self._freeze()
        self.persist()
        self.status["state"] = "stop"
        self.error = ""

    def next(self):
        with self.lock:
            if self.saved.get('intro', {}).get('kind') in ('mode', 'custom'):
                self._interrupt_announcement()
            if self.saved.get("intro"):
                self.saved['intro']['restart_timer'] = True
                self._finish_intro()
                return
            snapshot = {"episode_id": self.saved["episode_id"], "position": self.status["elapsed"],
                        "queue": self.queue(), "playing": self.status["state"] == "play"}
            self._advance(restart_timer=True)
            snapshot["revision"] = self.revision
            self.undo = snapshot if snapshot["episode_id"] else None

    def undo_next(self):
        with self.lock:
            if not self.undo or self.undo["revision"] != self.revision:
                raise PlayerError("Keine unveränderte Überspringaktion zum Rückgängigmachen")
            old = self.undo
            displaced = self.saved["episode_id"]
            self.start_episode(old["episode_id"], restart_timer=True)
            self.seek(old["position"])
            wanted = [r for r in old["queue"] if r["id"] != old["episode_id"]]
            if displaced and displaced != old["episode_id"] and displaced not in [r["id"] for r in wanted]:
                wanted.insert(0, {"id": displaced, "queue_error": ""})
            with self.db.connect() as db:
                db.execute("DELETE FROM queue")
                db.executemany("INSERT INTO queue VALUES(?,?,?)", [(e["id"], i, e["queue_error"]) for i, e in enumerate(wanted)])
            self._queue_changed()
            if not old["playing"]:
                self.pause()

    def command(self, action, *, timer='keep', when_queue_empty='keep', episode_id=None, from_start=False):
        """Execute a remote/UI command and optional run timer under the same lock.

        Manual API start/resume/Next restarts the selected period. UI resume uses
        timer=preserve; timer=default selects the configured sleep duration. Repeated Play while already playing remains a no-op.
        """
        with self.lock:
            self.sync()
            self._require_mpd()
            if action == 'normal':
                if self.status['state'] == 'play':
                    self.pause()
                self.timer(0)
                self.saved['when_queue_empty'] = 'stop'
                self.persist()
                return
            sleep = action == 'sleep'
            starts = sleep or action in ('episode', 'next') or (action in ('play', 'toggle') and self.status['state'] != 'play')
            timer_keys = ('timer_seconds', 'remaining', 'deadline', 'preset_pending', 'when_queue_empty')
            before = {k: self.saved[k] for k in timer_keys if k in self.saved}
            if starts and (timer == 'default' or sleep):
                self.timer(self.sleep_defaults()['minutes'] * 60)
            if starts and (when_queue_empty != 'keep' or sleep):
                self.saved['when_queue_empty'] = self.sleep_defaults()['when_queue_empty'] if sleep or when_queue_empty == 'default' else when_queue_empty
                self.persist()
            try:
                if sleep:
                    self.play()
                elif action == 'episode':
                    self.start_episode(episode_id, from_start, restart_timer=True)
                elif action in ('play', 'toggle'):
                    if action == 'toggle' and self.status['state'] == 'play':
                        self.pause()
                    else:
                        self.play(restart_timer=timer != 'preserve' or (self.saved['timer_seconds'] > 0 and self.remaining() <= 0))
                else:
                    {'pause': self.pause, 'next': self.next, 'undo': self.undo_next}[action]()
            except Exception:
                if starts and (timer == 'default' or when_queue_empty != 'keep' or sleep):
                    for key in timer_keys:
                        self.saved.pop(key, None)
                    self.saved.update(before)
                    self.persist()
                raise

    def _require_mpd(self):
        if self.status['state'] == 'error':
            raise MPDUnavailable(self.error or 'MPD ist nicht erreichbar')

    def seek_to(self, position=None, offset=None):
        with self.lock:
            self.sync()
            self._require_mpd()
            # The command uses the freshly read MPD sample, not the display estimate.
            intro = self.saved.get('intro')
            elapsed = intro['position'] if intro else self.status['elapsed']
            target = position if position is not None else elapsed + offset
            self.seek(target)

    def set_volume(self, value, *, relative=False):
        with self.lock:
            self.sync()
            self._require_mpd()
            if self.status['volume'] < 0:
                raise PlayerError('MPD stellt keine regelbare Lautstärke bereit', code='mixer_unavailable')
            self.volume(self.status['volume'] + value if relative else value)

    def play(self, *, restart_timer=True):
        with self.lock:
            self.sync()
            if self.status["state"] == "error":
                raise PlayerError(self.error)
            if self.status["state"] == "play":
                return
            if self.saved.get('intro'):
                if self.status['state'] == 'pause' and self.last_song:
                    self.mpd.call('pause', 0)
                    if restart_timer:
                        self._restart_sleep_timer()
                    self.sync()
                elif self.status['state'] == 'stop':
                    if restart_timer:
                        self._restart_sleep_timer()
                    self._finish_intro()
                return
            if self.status["state"] == "pause" and self.last_song:
                self.mpd.call("pause", 0)
                self._begin_run(preserve_timer=True)
                if restart_timer:
                    self._restart_sleep_timer()
                if self.saved["timer_seconds"]:
                    self.saved["deadline"] = self.clock() + self.saved["remaining"]
                self.persist()
                self.sync()
            elif self.saved.get('episode_id') and (self.saved['when_queue_empty']=='stop' or not self.episode(self.saved['episode_id'])['completed']):
                self.start_episode(self.saved['episode_id'], restart_timer=restart_timer)
            else:
                self._advance(restart_timer=restart_timer)

    def pause(self):
        with self.lock:
            self.mpd.call("pause", 1)
            self.sync()
            self._checkpoint()

    def toggle(self):
        with self.lock:
            self.sync()
            self.pause() if self.status["state"] == "play" else self.play()

    def seek(self, position):
        with self.lock:
            if self.saved.get('intro'):
                intro = self.saved['intro']
                if intro.get('kind') in ('mode', 'custom') and not intro['resume']['song']:
                    raise PlayerError('Keine aktive Episode')
                duration = self.episode(intro['episode_id'])['duration'] if intro['episode_id'] else intro.get('display_duration', 0)
                intro['position'] = max(0, min(position, duration)) if duration else max(0, position)
                if intro.get('kind') in ('mode', 'custom'):
                    original_intro = intro['resume']['playback'].get('intro')
                    if original_intro:
                        original_intro['position'] = intro['position']
                    else:
                        intro['resume']['status']['elapsed'] = intro['position']
                self.persist()
                return
            if not self.last_song:
                raise PlayerError("Keine aktive Episode")
            duration = self.status["duration"]
            position = max(0, min(position, duration)) if duration else max(0, position)
            self.mpd.call("seekcur", str(position))
            self.status["elapsed"] = position
            self.status_at = self.clock()
            self._checkpoint()
            self.previous_elapsed = position

    def volume(self, value):
        with self.lock:
            self.mpd.call("setvol", max(0, min(100, value)))
            self.status["volume"] = max(0, min(100, value))

    def set_mode(self, favorite):
        with self.lock:
            changed = self.mode != favorite
            self.mode = favorite
            self.db.put("favorites_only", favorite)
            if changed:
                try:
                    self._announce_mode('Favoriten' if favorite else 'Normal')
                except Exception:
                    # A failed announcement must not undo the successfully changed mode.
                    self.sync()
                    log.warning('Modusansage nicht verfügbar; Modus wurde trotzdem geändert', exc_info=True)

    def _restore_announcement_metadata(self, intro):
        """Restore identities without checkpointing announcement seconds onto an episode."""
        resume = intro['resume']
        self.saved.pop('intro', None)
        self.saved.update(deepcopy(resume['playback']))
        self.status, self.last_song = dict(resume['status']), dict(resume['song'])

    def _interrupt_announcement(self):
        # A manual episode change must not briefly resume the old podcast first.
        intro = self.saved['intro']
        self.mpd.call('stop')
        if intro.get('kind') == 'custom':
            self._cancel_announcements()
        self._restore_announcement_metadata(intro)
        self.previous_state = self.status['state']
        self.persist()

    def _save_announcements(self):
        terminal = [job for job in self.announcements if job['state'] in ('done', 'failed', 'cancelled')]
        keep = {job['id'] for job in terminal[-100:]}
        self.announcements = [job for job in self.announcements
                              if job['state'] not in ('done', 'failed', 'cancelled') or job['id'] in keep]
        self.db.put('announcement_jobs', self.announcements)

    def _announcement_result(self, job):
        pending = [item['id'] for item in self.announcements if item['state'] in ('queued', 'generating')]
        return {**job, 'queue_position': pending.index(job['id']) + 1 if job['id'] in pending else 0}

    def announcement_status(self, id_=None):
        with self.lock:
            if id_ is None:
                return [self._announcement_result(job) for job in self.announcements]
            job = next((item for item in self.announcements if item['id'] == id_), None)
            if job is None:
                raise PlayerError('Ansage nicht gefunden', code='not_found', status_code=404)
            return self._announcement_result(job)

    def announce(self, text):
        with self.lock:
            settings = getattr(self.notifications, 'settings', None)
            if settings is not None and hasattr(settings, 'tts_audio_url') and not settings.tts_audio_url:
                raise PlayerError('TTS_AUDIO_URL ist nicht konfiguriert', code='tts_not_configured', status_code=503)
            if sum(job['state'] in ('queued', 'generating', 'playing') for job in self.announcements) >= 50:
                raise PlayerError('Die Ansagewarteschlange ist voll', code='announcement_queue_full', status_code=429)
            job = {'id': uuid.uuid4().hex, 'text': text, 'state': 'queued', 'error': '',
                   'created': time.time(), 'finished': None}
            self.announcements.append(job)
            self._save_announcements()
            self.announcement_wake.set()
            return self._announcement_result(job)

    def _end_announcement_job(self, id_, state='done', error=''):
        job = next((item for item in self.announcements if item['id'] == id_), None)
        if job and job['state'] not in ('done', 'failed', 'cancelled'):
            job.update(state=state, error=error, finished=time.time())
            self._save_announcements()

    def _cancel_announcements(self):
        for job in self.announcements:
            if job['state'] in ('queued', 'generating', 'playing'):
                job.update(state='cancelled', finished=time.time())
        self._save_announcements()

    def process_announcements(self):
        # One worker generates speech; the MPD monitor and API controls keep running.
        if not self.announcement_lock.acquire(blocking=False):
            return False
        job = None
        try:
            with self.lock:
                intro = self.saved.get('intro')
                if intro and not (intro.get('kind') == 'custom' and intro.get('waiting_next')):
                    return False
                job = next((item for item in self.announcements if item['state'] == 'queued'), None)
                if job is None:
                    return False
                job['state'] = 'generating'
                self._save_announcements()
            try:
                audio = self.notifications.title_audio(job['text'])
                if not audio:
                    raise PlayerError('Keine TTS-Audiodatei erhalten. TTS_AUDIO_URL prüfen.', code='tts_unavailable', status_code=502)
                with self.lock:
                    if self.stop_event.is_set():
                        if job['state'] == 'generating':
                            job['state'] = 'queued'
                            self._save_announcements()
                        return False
                    if job['state'] == 'cancelled':
                        return True
                    self.sync()
                    self._require_mpd()
                    intro = self.saved.get('intro')
                    if intro and not (intro.get('kind') == 'custom' and intro.get('waiting_next')):
                        job['state'] = 'queued'
                        self._save_announcements()
                        return False
                    job['state'] = 'playing'
                    self._save_announcements()
                    self._start_announcement(job['text'], audio, kind='custom', strict=True, job_id=job['id'])
            except Exception as exc:
                with self.lock:
                    # A concurrent manual source change wins over generated audio.
                    if job['state'] != 'cancelled':
                        job.update(state='failed', error=str(exc) if isinstance(exc, PlayerError) else 'Ansage konnte nicht erzeugt oder abgespielt werden', finished=time.time())
                        self._save_announcements()
                    intro = self.saved.get('intro', {})
                    if intro.get('waiting_next') and not any(item['state'] in ('queued', 'generating') for item in self.announcements):
                        self._finish_announcement()
                log.warning('Ansage fehlgeschlagen', exc_info=True)
            return True
        finally:
            self.announcement_lock.release()

    def start_announcement_worker(self):
        def loop():
            while not self.stop_event.is_set():
                try:
                    worked = self.process_announcements()
                except Exception:
                    log.warning('Ansagewarteschlange konnte nicht verarbeitet werden', exc_info=True)
                    worked = False
                if not worked:
                    self.announcement_wake.wait(.5)
                    self.announcement_wake.clear()
        self.announcement_thread = threading.Thread(target=loop, name='announcements', daemon=True)
        self.announcement_thread.start()

    def _announce_mode(self, text):
        if (self.announcement_lock.locked() or self.saved.get('intro', {}).get('kind') == 'custom'
                or any(job['state'] in ('queued', 'generating') for job in self.announcements)):
            # Mode changes still speak, but join an existing announcement batch.
            self.announce(text)
            return
        audio = self.notifications.title_audio(text)
        if not audio:
            return
        self._start_announcement(text, audio, kind='mode')

    def _start_announcement(self, text, audio, *, kind, strict=False, job_id=None):
        self.sync()
        self._require_mpd()
        current = self.saved.get('intro')
        display = self.state()
        if current and current.get('kind') in ('mode', 'custom'):
            # Repeated mode changes replace the speech, never stack return contexts.
            resume = deepcopy(current['resume'])
        else:
            self._checkpoint()
            resume = {'playback': {k: deepcopy(self.saved[k]) for k in
                      ('episode_id', 'song_id', 'source_url', 'source_kind', 'activity_run', 'intro') if k in self.saved},
                      'status': dict(self.status), 'song': dict(self.last_song)}
        was_playing = self.status['state'] == 'play'
        self._freeze()
        original_intro = resume['playback'].get('intro')
        if original_intro and original_intro['timeout_at'] is not None:
            original_intro['timeout_remaining'] = max(0, original_intro['timeout_at'] - self.clock())
            original_intro['timeout_at'] = None
        timeout = getattr(getattr(self.notifications, 'settings', None), 'tts_playback_timeout_seconds', 120)
        intro = {'kind': kind, 'text': text, 'announcement_id': job_id, 'episode_id': display['current']['id'] if display['current'] else None,
                 'position': display['elapsed'], 'display_duration': display['duration'],
                 'source_kind': display['source_kind'], 'url': audio, 'resume': resume,
                 'timeout_remaining': timeout, 'timeout_at': self.clock() + timeout}
        self.saved['intro'] = intro
        # Persist the return context before touching the MPD playlist.
        self.persist()
        try:
            # The return context is already durable if pausing or the next read fails.
            if was_playing:
                self.mpd.call('pause', 1)
                paused, paused_song = self._read()
                if (not current or current.get('kind') not in ('mode', 'custom')) and paused_song:
                    resume['status']['elapsed'] = paused['elapsed']
                    resume['song'] = paused_song
                    if not current:
                        intro['position'] = paused['elapsed']
                    self.persist()
            self.mpd.start(audio, 0)
            status, song = self._read()
            end = time.monotonic() + 2
            while status['state'] != 'play' and not status['mpd_error'] and time.monotonic() < end:
                time.sleep(.1)
                status, song = self._read()
            if status['state'] != 'play' or status['mpd_error']:
                raise PlayerError('MPD konnte die Ansage nicht starten')
        except Exception as exc:
            try:
                self._finish_announcement()
            except Exception as restore_error:
                if strict:
                    raise MPDUnavailable('Ansage fehlgeschlagen; Wiederherstellung der Wiedergabe steht noch aus') from restore_error
                raise
            if strict:
                raise PlayerError('MPD konnte die Ansage nicht starten', code='announcement_failed', status_code=502) from exc
            log.warning('Ansage konnte nicht gestartet werden; vorherige Wiedergabe wiederhergestellt')
            return
        self.status, self.last_song, self.error = status, song, ''
        self.previous_state, self.previous_elapsed, self.previous_duration = status['state'], status['elapsed'], status['duration']
        self.persist()
        self.notifications.publish('play')

    def _finish_announcement(self):
        intro = self.saved['intro']
        if intro.get('kind') == 'custom' and not intro.get('restoring'):
            self._end_announcement_job(intro.get('announcement_id'))
            if any(job['state'] in ('queued', 'generating') for job in self.announcements):
                if self.status['state'] in ('play', 'pause'):
                    self.mpd.call('stop')
                intro.update(waiting_next=True, timeout_at=None)
                self.status, self.last_song = self._read()
                self.previous_state = self.status['state']
                self.persist()
                self.announcement_wake.set()
                return
        resume = intro['resume']
        wanted = resume['status']['state']
        source = resume['song'].get('file')
        # Keep the context persisted until MPD restoration succeeds, for outage retries.
        intro['restoring'] = True
        self.persist()
        if source and wanted in ('play', 'pause'):
            if 'restore_song_id' not in intro:
                # Do not reload/reseek on each monitor tick while MPD buffers.
                intro['restore_song_id'] = self.mpd.start(source, resume['status']['elapsed'], paused=wanted == 'pause')
                intro['restore_timeout_at'] = self.clock() + 120
                self.persist()
            song_id = intro['restore_song_id']
            status, song = self._read()
            if status['mpd_error']:
                intro.pop('restore_song_id', None)
                self.persist()
                raise PlayerError('MPD konnte die Episode nach der Ansage nicht fortsetzen: ' + status['mpd_error'])
            if status['state'] != wanted or song.get('file') != source or song.get('id') != song_id:
                if self.clock() >= intro['restore_timeout_at']:
                    intro.pop('restore_song_id', None)
                    self.persist()
                    raise PlayerError('Zeitlimit beim Fortsetzen nach der Ansage erreicht')
                # Buffering is a transition, not a disconnected MPD. Keep the
                # return context and frozen timer until the source is confirmed.
                self.status, self.last_song, self.error = status, song, ''
                self.persist()
                return
        else:
            self.mpd.call('clear')
            song_id = None
            status, song = self._read()
        self._restore_announcement_metadata(intro)
        self.saved['song_id'] = song_id
        if not song and not self.saved.get('intro'):
            self.saved.update(episode_id=None, source_url=None)
        original_intro = self.saved.get('intro')
        if original_intro:
            original_intro['timeout_at'] = self.clock() + original_intro['timeout_remaining'] if wanted == 'play' else None
        self.saved['deadline'] = (self.clock() + self.saved['remaining']
                                  if wanted == 'play' and self.saved['timer_seconds'] and self.saved['run_active'] and not self._timer_suspended() else None)
        self.status, self.last_song, self.error = status, song, ''
        self.previous_state, self.previous_elapsed, self.previous_duration = status['state'], status['elapsed'], status['duration']
        self.persist()
        self.notifications.publish(status['state'])

    def timer(self, seconds=None, extend=0):
        with self.lock:
            if extend:
                if not self.saved["timer_seconds"]:
                    raise PlayerError("Sleep-Timer ist ausgeschaltet")
                remaining = self.remaining() + extend
            else:
                self.saved["timer_seconds"] = seconds
                remaining = seconds
            self.saved["remaining"] = remaining
            if not self.saved["run_active"]:
                self.saved["preset_pending"] = True
            self.saved["deadline"] = self.clock() + remaining if self.status["state"] == "play" and self.saved["timer_seconds"] and not self._timer_suspended() and (not self.saved.get("intro") or self.saved["run_active"]) else None
            self.persist()

    def delete_episodes(self, ids):
        with self.lock:
            if self.saved["episode_id"] in ids or self.saved.get("intro", {}).get("episode_id") in ids:
                if self.saved.get('intro', {}).get('kind') == 'custom':
                    self._cancel_announcements()
                self.mpd.call("stop")
                self._freeze()
                self.saved.pop("intro", None)
                self.saved.update(episode_id=None, song_id=None, run_active=False)
                self.status.update(state="stop", elapsed=0, duration=0)
                self.last_song = {}
                self.previous_state = "stop"
                self.persist()
                self.notifications.publish("stop")
            with self.db.connect() as db:
                db.executemany("DELETE FROM episodes WHERE id=?", [(i,) for i in ids])
            self._queue_changed()

    def start_monitor(self):
        events = getattr(self.mpd, 'start_events', None)
        if events:
            events(self.monitor_wake.set)
        def loop():
            next_sync = 0
            while not self.stop_event.is_set():
                changed = self.monitor_wake.is_set()
                if changed:
                    self.monitor_wake.clear()
                with self.lock:
                    intro = self.saved.get('intro', {})
                    deadline = self.saved.get('deadline')
                    timeout = intro.get('timeout_at')
                    due = ((deadline is not None and self.clock() >= deadline)
                           or (timeout is not None and self.clock() >= timeout))
                    if changed or due or intro.get('restoring') or time.monotonic() >= next_sync:
                        self.sync()
                        next_sync = time.monotonic() + (MPD_RECONCILE_SECONDS if events else 1)
                    elif self.clock() - self.last_checkpoint >= 5:
                        self._checkpoint(estimate=True)
                        self.last_checkpoint = self.clock()
                # Local clock tick only; no MPD request without event/deadline.
                self.monitor_wake.wait(max(0, min(1, next_sync - time.monotonic())))
        self.thread = threading.Thread(target=loop, daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        self.monitor_wake.set()
        self.announcement_wake.set()
        if self.announcement_thread:
            self.announcement_thread.join(timeout=7)
        if self.thread:
            self.thread.join(timeout=7)
        close = getattr(self.mpd, 'close', None)
        if close:
            close()
        with self.lock:
            self._checkpoint(estimate=True)
            self.persist()
