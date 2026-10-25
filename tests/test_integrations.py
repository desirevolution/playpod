from types import SimpleNamespace
from unittest.mock import Mock
import socketserver
import threading

from app.config import Settings
from app.integrations import MPD, Notifications
from test_downloads import download_rig, source


class ProtocolHandler(socketserver.StreamRequestHandler):
    def handle(self):
        self.wfile.write(b'OK MPD 0.24.0\n')
        batch = False
        while raw := self.rfile.readline():
            command = raw.decode().strip()
            self.server.commands.append(command)
            if command == 'command_list_ok_begin':
                batch = True
                continue
            if command == 'command_list_end':
                batch = False
                self.wfile.write(b'OK\n')
                continue
            if command.startswith('addid'):
                self.wfile.write(b'Id: 1\n')
            elif command == 'playlistinfo':
                self.wfile.write(b'file: http://example.test/a.mp3\nId: 1\nPos: 0\n')
            elif command == 'status':
                self.wfile.write(b'state: play\nelapsed: 12.000\nduration: 1200.000\nvolume: 55\n')
            elif command == 'currentsong':
                self.wfile.write(b'file: http://example.test/a.mp3\nId: 1\nPos: 0\n')
            self.wfile.write(b'list_OK\n' if batch else b'OK\n')


def test_real_python_mpd_client_protocol():
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), ProtocolHandler)
    server.commands = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        mpd = MPD(Settings(mpd_host='127.0.0.1', mpd_port=server.server_address[1]))
        assert mpd.start('http://example.test/a.mp3', 12) == '1'
        status,song=mpd.snapshot()
        assert status['state']=='play'
        assert song['id']=='1'
        assert 'repeat "0"' in server.commands
        assert 'single "1"' in server.commands
        assert 'seekid "1" "12"' in server.commands
        assert not any(c.startswith('playid') for c in server.commands)
        assert 'pause "0"' in server.commands
        server.commands.clear()
        mpd.start('http://example.test/a.mp3', 123, paused=True)
        assert not any(c.startswith('playid') for c in server.commands)
        assert server.commands.index('pause "1"') < server.commands.index('seekid "1" "123"')
        assert server.commands[server.commands.index('seekid "1" "123"')+1] == 'pause "1"'
    finally:
        mpd.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_mqtt_payload_retained_and_republish_on_connect():
    n=Notifications(Settings())
    client=Mock()
    client.is_connected.return_value=True
    client.publish.return_value=SimpleNamespace(rc=0)
    n.client=client
    n.publish('play')
    n.publish('play')
    client.publish.assert_called_once_with('podplayer/status','play',qos=1,retain=True)
    n._connected(client,None,None,0,None)
    assert client.publish.call_count==2


def test_old_tts_environment_does_not_send_requests(monkeypatch):
    monkeypatch.setenv('TTS_URL', 'http://node-red.test/old-speak')
    monkeypatch.delenv('TTS_AUDIO_URL', raising=False)
    post = Mock()
    monkeypatch.setattr('app.integrations.requests.post', post)
    notifications = Notifications(Settings.from_env())
    assert notifications.title_audio('Episode') is None
    post.assert_not_called()


def test_episode_waits_for_tts_response_before_mpd_start(rig, monkeypatch):
    _, player, _, mpd, _ = rig
    entered, release, started = threading.Event(), threading.Event(), threading.Event()
    original = mpd.start
    def start(*args, **kwargs):
        started.set()
        return original(*args, **kwargs)
    mpd.start = start
    def post(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return Mock(json=lambda: {"url": "http://ha.test/title.wav"})
    monkeypatch.setattr('app.integrations.requests.post', post)
    player.notifications = Notifications(Settings(tts_audio_url='http://node-red.test/title-audio'))
    thread = threading.Thread(target=lambda: player.start_episode(1))
    thread.start()
    try:
        assert entered.wait(1)
        assert not started.is_set()
        assert player.saved['episode_id'] is None
    finally:
        release.set()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert started.is_set()
    assert player.saved['intro']['episode_id'] == 1


def test_tts_error_and_timeout_still_allow_playback(rig, monkeypatch):
    import requests
    _, player, _, mpd, _ = rig
    player.notifications = Notifications(Settings(tts_audio_url='http://node-red.test/title-audio', tts_timeout_seconds=.25))
    for exc in (requests.Timeout('timeout'), requests.HTTPError('HTTP 500')):
        post = Mock(side_effect=exc)
        monkeypatch.setattr('app.integrations.requests.post', post)
        player.start_episode(1)
        assert mpd.state == 'play'
        assert post.call_args.kwargs['timeout'] == .25


def test_automatic_transition_during_tts_respects_expired_timer(rig):
    _, player, _, mpd, notifications = rig
    now = [1000.0]
    player.clock = lambda: now[0]
    player.start_episode(1)
    player.enqueue(2)
    player.saved['deadline'] = 1001
    starts = sum(c[0] == 'start' for c in mpd.calls)
    def title_audio(title):
        now[0] = 1002
    notifications.title_audio = title_audio
    player._advance(natural=True)
    assert sum(c[0] == 'start' for c in mpd.calls) == starts
    assert player.saved['episode_id'] == 1
    assert [e['id'] for e in player.queue()] == [2]
    assert not player.saved['run_active']
    assert player.status['state'] == 'pause'


def test_local_fallback_announces_only_once(download_rig, monkeypatch):
    # Both source attempts belong to one announcement.
    client, app, downloads, _, mpd = download_rig
    from test_downloads import complete_download
    id_ = complete_download(client, downloads)
    mpd.bad_urls.add(f'http://playpod.lan:9393/downloads/{id_}')
    events = []
    original = mpd.start
    def start(*args, **kwargs):
        events.append('start')
        return original(*args, **kwargs)
    def title_audio(title):
        events.append('tts')
    mpd.start = start
    app.state.player.notifications.title_audio = title_audio
    app.state.player.start_episode(1)
    assert events == ['tts', 'start', 'start']

