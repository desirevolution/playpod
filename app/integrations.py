from contextlib import contextmanager
import logging
import os
import socket
import threading
from urllib.parse import urlsplit
import requests
from mpd import MPDClient, ConnectionError as MPDConnectionError
import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


class MPD:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.client = None
        self.event_lock = threading.Lock()
        self.event_client = None
        self.event_stop = threading.Event()
        self.event_thread = None

    @staticmethod
    def _disconnect(client):
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass

    def _connect(self):
        client = MPDClient()
        client.timeout = 5
        try:
            client.connect(self.settings.mpd_host, self.settings.mpd_port)
            if self.settings.mpd_password:
                client.password(self.settings.mpd_password)
            # Detect a lost network even while idle has no application timeout.
            with socket.socket(fileno=os.dup(client.fileno())) as sock:
                if sock.family in (socket.AF_INET, socket.AF_INET6):
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                    for option, value in (('TCP_KEEPIDLE', 30), ('TCP_KEEPINTVL', 10), ('TCP_KEEPCNT', 3)):
                        if hasattr(socket, option):
                            sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
            return client
        except Exception:
            self._disconnect(client)
            raise

    @contextmanager
    def connection(self):
        # A single serialized command connection also prevents interleaved replies
        # from HTTP controls, health checks and the player monitor.
        with self.lock:
            if self.client is None:
                self.client = self._connect()
            try:
                yield self.client
            except BaseException:
                self._disconnect(self.client)
                self.client = None
                raise

    def snapshot(self):
        # Repeating reads is safe. Mutating commands are deliberately never replayed
        # after a lost response: MPD may already have executed them.
        for attempt in range(2):
            try:
                with self.connection() as c:
                    return c.status(), c.currentsong()
            except (OSError, EOFError, MPDConnectionError):
                if attempt:
                    raise

    def start_events(self, changed):
        if self.event_thread and self.event_thread.is_alive():
            return
        self.event_stop.clear()
        def loop():
            delay = 1
            while not self.event_stop.is_set():
                client = None
                try:
                    client = self._connect()
                    with self.event_lock:
                        self.event_client = client
                    if self.event_stop.is_set():
                        break
                    delay = 1
                    changed()  # Reconcile changes that happened during an outage.
                    while not self.event_stop.is_set():
                        client.idle('player', 'playlist', 'mixer', 'options', 'output')
                        if not self.event_stop.is_set():
                            changed()
                except Exception:
                    if not self.event_stop.is_set():
                        log.warning('MPD-idle-Verbindung unterbrochen; Wiederverbindung in %s s', delay)
                        changed()
                finally:
                    with self.event_lock:
                        self.event_client = None
                    self._disconnect(client)
                if self.event_stop.wait(delay):
                    break
                delay = min(30, delay * 2)
        self.event_thread = threading.Thread(target=loop, name='mpd-idle', daemon=True)
        self.event_thread.start()

    def close(self):
        self.event_stop.set()
        with self.event_lock:
            client = self.event_client
            if client is not None:
                try:
                    # Wake the blocking idle read without concurrently touching
                    # python-mpd2's parser or closing its buffered file objects.
                    with socket.socket(fileno=os.dup(client.fileno())) as sock:
                        sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass
        if self.event_thread:
            self.event_thread.join(timeout=6)
        with self.lock:
            self._disconnect(self.client)
            self.client = None

    def call(self, name, *args):
        with self.connection() as c:
            return getattr(c, name)(*args)

    def start(self, url, position=0, *, paused=False):
        # App owns the MPD queue; do not let MPD's repeat/random defeat its queue/timer.
        with self.connection() as c:
            c.clearerror()
            c.repeat(0)
            c.random(0)
            c.single(1)
            song_id = c.addid(url)
            if position > 0 or paused:
                # seekid selects the song at the target offset. Playing first would
                # send the beginning of the podcast to the audio output before the seek.
                # Keep selection and the requested pause state in one server batch.
                c.command_list_ok_begin()
                if paused:
                    c.pause(1)
                c.seekid(song_id, str(position))
                c.pause(1 if paused else 0)
                c.command_list_end()
            else:
                c.playid(song_id)
            # Keep only the active song after a confirmed add/play, not before add succeeds.
            for song in c.playlistinfo():
                if song.get("id") != str(song_id):
                    c.deleteid(song["id"])
            return str(song_id)


class DisabledMPD:
    """No sockets or background monitor when MPD_HOST is empty."""
    def snapshot(self):
        return {'state': 'stop', 'volume': '-1'}, {}

    def call(self, name, *args):
        if name not in ('stop', 'clear'):
            from .player import PlayerError
            raise PlayerError('MPD nicht konfiguriert', code='mpd_not_configured', status_code=503)



class Notifications:
    def __init__(self, settings):
        self.settings = settings
        self.state = "stop"
        self.last_sent = None
        self.lock = threading.Lock()
        self.client = None
        if settings.mqtt_host:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            if settings.mqtt_user:
                self.client.username_pw_set(settings.mqtt_user, settings.mqtt_password)
            self.client.on_connect = self._connected
            self.client.reconnect_delay_set(1, 30)

    def start(self):
        if self.client:
            self.client.connect_async(self.settings.mqtt_host, self.settings.mqtt_port, 60)
            self.client.loop_start()

    def _connected(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            with self.lock:
                self.last_sent = None
            self.publish(self.state)

    def publish(self, state):
        with self.lock:
            self.state = state
            if self.client and self.client.is_connected() and state != self.last_sent:
                result = self.client.publish(self.settings.mqtt_topic, state, qos=1, retain=True)
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.last_sent = state

    def title_audio(self, title):
        if not self.settings.tts_audio_url:
            return None
        try:
            response = requests.post(self.settings.tts_audio_url, data=title.encode('utf-8'),
                                     headers={'Content-Type': 'text/plain;charset=utf-8'},
                                     timeout=self.settings.tts_timeout_seconds)
            response.raise_for_status()
            url = response.json().get('url')
            if not isinstance(url, str) or urlsplit(url).scheme not in ('http', 'https') or not urlsplit(url).netloc:
                raise ValueError('Keine gültige Audio-URL erhalten')
            return url
        except (requests.RequestException, ValueError, AttributeError):
            log.warning('TTS-Audiodatei nicht verfügbar')
            return None

    def stop(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
