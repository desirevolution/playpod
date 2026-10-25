from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
from pathlib import Path
import sqlite3
import threading
from uuid import uuid4
import wave

import pytest
import requests
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.db import Database
from app.downloads import Downloads
from app.player import PlayerError
from app.player import Player
from conftest import FakeMPD, FakeNotifications


@pytest.fixture
def source():
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as file:
        file.setnchannels(1)
        file.setsampwidth(2)
        file.setframerate(8000)
        file.writeframes(b'\0\0' * 8000)
    data = audio.getvalue()
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_GET(self):
            calls.append(self.path)
            if self.path == '/404':
                self.send_error(404)
                return
            body = b'<html>Login required</html>' if self.path == '/html' else b'' if self.path == '/empty' else data
            self.send_response(200)
            self.send_header('Content-Type', 'text/html' if self.path == '/html' else 'audio/wav')
            if self.path != '/unknown':
                self.send_header('Content-Length', len(body) + (10 if self.path == '/truncated' else 0))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{server.server_port}', data, calls
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.fixture
def download_rig(tmp_path, source):
    base, data, calls = source
    settings = Settings(database=str(tmp_path / 'playpod.sqlite3'), media_base_url='http://playpod.lan:9393')
    mpd = FakeMPD()
    app = create_app(settings, mpd=mpd, notifications=FakeNotifications(), background=False)
    db = app.state.db
    db.execute("INSERT INTO feeds(id,url,title) VALUES(1,'http://feed.test','Feed')")
    db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url,position,bookmarked) VALUES(1,1,'one','Episode',?,42,1)", (base + '/episode.wav',))
    # Existing playback regressions explicitly exercise the sleep setup.
    app.state.player.saved.update(timer_seconds=900, remaining=900, when_queue_empty='random_unheard')
    app.state.player.sync()
    with TestClient(app) as c:
        yield c, app, app.state.downloads, settings, mpd


def complete_download(c, downloads):
    response = c.post('/api/v1/episodes/1/download')
    assert response.status_code == 202
    downloads.run_one()
    return response.json()['id']


def test_integrated_download_and_range_serving(download_rig, source):
    c, app, d, settings, mpd = download_rig
    _, data, calls = source
    id_ = c.post('/api/v1/episodes/1/download').json()['id']
    assert c.post('/api/v1/episodes/1/download').json()['id'] == id_
    assert c.get('/downloads/' + id_).status_code == 404
    assert d.run_one()
    assert not d.run_one()
    row = c.get('/api/v1/downloads').json()['items'][0]
    assert row['state'] == 'ready'
    assert row['received'] == row['total'] == len(data)
    assert c.get('/downloads/' + id_).content == data
    part = c.get('/downloads/' + id_, headers={'Range':'bytes=10-19'})
    assert part.status_code == 206 and part.content == data[10:20]
    assert c.get('/downloads/' + id_, headers={'Range':'bytes=-10'}).content == data[-10:]
    assert c.head('/downloads/' + id_).content == b''
    assert c.head('/downloads/' + id_).headers['content-type'].startswith('audio/')
    assert c.delete('/api/v1/episodes/1/download').status_code == 409
    assert len(calls) == 1
    assert not list(d.directory.glob('*.part'))
    assert d.directory == Path(settings.database).parent / 'downloads'
    assert not (d.directory/'worker.sqlite3').exists()


@pytest.mark.parametrize('route', ['/404','/html','/empty','/truncated'])
def test_failed_sources_never_publish_partial_files(download_rig, source, route):
    c, app, d, _, _ = download_rig
    base, _, _ = source
    app.state.db.execute('UPDATE episodes SET url=? WHERE id=1', (base+route,))
    id_ = complete_download(c, d)
    row = d.task(id_)
    assert row['state'] == 'error' and row['error']
    assert not list(d.directory.glob('*.part'))
    assert not list(d.directory.glob('*.audio'))
    if route == '/404':
        assert '404' in row['error']


@pytest.mark.parametrize('route', ['/episode.wav','/unknown'])
def test_size_limit_with_and_without_content_length(download_rig, source, route):
    c, app, d, _, _ = download_rig
    base, _, _ = source
    d.max_bytes = 100
    app.state.db.execute('UPDATE episodes SET url=? WHERE id=1', (base+route,))
    id_ = complete_download(c, d)
    assert d.task(id_)['state'] == 'error'
    assert 'DOWNLOAD_MAX_BYTES' in d.task(id_)['error']
    assert not list(d.directory.glob('*.part'))


def test_durable_restart_and_single_queue(download_rig, source):
    c, app, d, settings, _ = download_rig
    base, _, calls = source
    first = c.post('/api/v1/episodes/1/download').json()['id']
    app.state.db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url) VALUES(2,1,'two','Two',?)",(base+'/two.wav',))
    second = c.post('/api/v1/episodes/2/download').json()['id']
    app.state.db.execute("UPDATE downloads SET state='running',received=100 WHERE id=?", (first,))
    (d.directory/(first+'.part')).write_bytes(b'partial')
    restored = Downloads(app.state.db, settings)
    assert restored.task(first)['state'] == 'queued'
    restored.run_one()
    assert restored.task(first)['state'] == 'ready'
    assert restored.task(second)['state'] == 'queued'
    restored.run_one()
    assert restored.task(second)['state'] == 'ready'
    assert calls == ['/episode.wav','/two.wav']


def test_cancel_before_and_during_download(download_rig):
    c, app, d, _, _ = download_rig
    first = c.post('/api/v1/episodes/1/download').json()['id']
    c.delete('/api/v1/episodes/1/download')
    assert not d.run_one()
    assert d.task(first)['state'] == 'cancelled'
    second = c.post('/api/v1/episodes/1/download').json()['id']
    assert first != second
    original = d.check_running
    def cancel_on_chunk(value):
        d.cancel(1)
        original(value)
    d.check_running = cancel_on_chunk
    d.run_one()
    assert d.task(second)['state'] == 'cancelled'
    assert not list(d.directory.glob('*.part'))
    assert not list(d.directory.glob('*.audio'))


def test_same_episode_progress_bookmark_queue_and_restart(download_rig):
    c, app, d, settings, mpd = download_rig
    c.post('/api/v1/queue',json={'episode_id':1})
    id_ = complete_download(c,d)
    assert c.get('/api/v1/episodes?filter=downloaded').json()['total'] == 1
    assert app.state.player.queue()[0]['id'] == 1
    r = c.post('/api/v1/episodes/play',json={'episode_id':1})
    assert r.json()['source_kind'] == 'local'
    assert mpd.calls[-1] == ('start',f'http://playpod.lan:9393/downloads/{id_}',42)
    assert r.json()['current']['id'] == 1 and r.json()['current']['bookmarked'] == 1
    assert app.state.db.one('SELECT count(*) AS n FROM episodes')['n'] == 1
    restored = Player(app.state.db,mpd,FakeNotifications(),media=app.state.media)
    restored.sync()
    assert restored.saved['episode_id'] == 1 and restored.saved['source_kind'] == 'local'
    assert Downloads(app.state.db,settings).playback_url(1).endswith(id_)


def test_running_playback_not_switched_when_download_finishes(download_rig):
    c, app, d, _, mpd = download_rig
    c.post('/api/v1/episodes/play',json={'episode_id':1})
    remote=mpd.song['file']
    complete_download(c,d)
    assert mpd.song['file'] == remote
    assert c.get('/api/v1/state').json()['source_kind'] == 'remote'


def test_missing_file_falls_back_and_can_retry(download_rig):
    c, app, d, _, mpd = download_rig
    id_=complete_download(c,d)
    d.file(id_).unlink()
    r=c.post('/api/v1/episodes/play',json={'episode_id':1})
    assert r.json()['source_kind'] == 'remote'
    assert c.get('/api/v1/downloads').json()['items'][0]['state']=='missing'
    assert c.post('/api/v1/episodes/1/download').json()['id']!=id_


def test_local_mpd_error_falls_back_to_original(download_rig):
    c, app, d, _, mpd = download_rig
    id_=complete_download(c,d)
    mpd.bad_urls.add(f'http://playpod.lan:9393/downloads/{id_}')
    r=c.post('/api/v1/episodes/play',json={'episode_id':1})
    assert r.status_code==200 and r.json()['source_kind']=='remote'
    assert r.json()['current']['position']==42


def test_missing_media_url_and_unknown_episode(rig):
    c,*_=rig
    assert c.get('/api/v1/downloads').json()['enabled']
    assert c.post('/api/v1/episodes/1/download').status_code==202
    assert c.post('/api/v1/episodes/999/download').status_code==404


def test_invalid_ids_and_protocols(download_rig):
    c, app, d, _, _=download_rig
    assert c.get('/downloads/not-an-id').status_code==404
    with pytest.raises(PlayerError):
        d.file('../../outside')
    app.state.db.execute("UPDATE episodes SET url='file:///etc/passwd' WHERE id=1")
    assert c.post('/api/v1/episodes/1/download').status_code==409
    assert not d.status()['items']


def test_downloaded_episode_excluded_from_unreachable_cleanup(download_rig):
    c, app, d, _, _=download_rig
    complete_download(c,d)
    app.state.db.execute("UPDATE episodes SET availability='unreachable' WHERE id=1")
    assert c.post('/api/v1/cleanup/delete',json={'ids':[1]}).status_code==409
    assert app.state.db.one('SELECT id FROM episodes WHERE id=1')


def test_legacy_copy_recognized_without_database_migration(download_rig):
    c, app, d, settings, _=download_rig
    id_=complete_download(c,d)
    d.file(id_).rename(d.directory/(id_+'.wav'))
    restored=Downloads(app.state.db,settings)
    assert restored.file(id_).suffix=='.wav'
    assert restored.playback_url(1).endswith(id_)
    assert app.state.db.one('PRAGMA user_version')['user_version']==5


def test_stop_requeues_inflight_transfer(download_rig):
    c, app, d, settings, _=download_rig
    id_=c.post('/api/v1/episodes/1/download').json()['id']
    original=d.check_running
    def stop_on_chunk(value):
        d.stop.set()
        original(value)
    d.check_running=stop_on_chunk
    d.run_one()
    assert d.task(id_)['state']=='queued'
    restored=Downloads(app.state.db,settings)
    restored.run_one()
    assert restored.task(id_)['state']=='ready'


def test_integrated_background_thread_processes_download(download_rig):
    c, app, d, _, _=download_rig
    completed=threading.Event()
    original=d.run_one
    def run_and_signal():
        result=original()
        if result:
            completed.set()
        return result
    d.run_one=run_and_signal
    d.start()
    assert c.post('/api/v1/episodes/1/download').status_code==202
    assert completed.wait(5)
    assert d.thread.is_alive()
    assert c.get('/api/v1/downloads').json()['items'][0]['state']=='ready'


def test_cancel_racing_network_error_does_not_stay_pending(download_rig):
    c, app, d, _, _=download_rig
    id_=c.post('/api/v1/episodes/1/download').json()['id']
    def failing_get(*args,**kwargs):
        d.cancel(1)
        raise requests.ConnectionError('connection lost after cancel')
    d.get=failing_get
    d.run_one()
    assert d.task(id_)['state']=='cancelled'
    assert not list(d.directory.glob('*.part'))


def test_network_error_during_shutdown_remains_resumable(download_rig):
    c, app, d, _, _=download_rig
    id_=c.post('/api/v1/episodes/1/download').json()['id']
    def stopping_get(*args,**kwargs):
        d.stop.set()
        raise requests.ConnectionError('connection closed during shutdown')
    d.get=stopping_get
    d.run_one()
    assert d.task(id_)['state']=='queued'


def test_accepted_download_has_stable_status_reference(download_rig):
    c,app,d,_,_=download_rig
    response=c.post('/api/v1/episodes/1/download')
    assert response.status_code==202
    task=response.json()
    assert task['status_url']=='/api/v1/downloads/'+task['id']
    status=c.get(task['status_url'])
    assert status.status_code==200
    assert status.json()['id']==task['id']
    assert status.json()['state']=='queued'
    assert c.get('/api/v1/downloads/not-an-id').status_code==422


def test_mode_speech_protects_download_needed_for_resume(download_rig):
    from unittest.mock import Mock
    c,app,d,_,mpd=download_rig
    complete_download(c,d)
    p=app.state.player
    p.start_episode(1,announce=False)
    p.notifications.title_audio=Mock(return_value='http://ha.test/mode.wav')
    p.set_mode(True)
    assert p.state()['announcement_kind']=='mode'
    assert c.delete('/api/v1/episodes/1/download/file').status_code==409
    assert c.get('/api/v1/downloads').json()['items'][0]['in_use']
