import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.integrations import DisabledMPD
from test_downloads import source,download_rig,complete_download
from test_media import media_rig,local_episode


def test_optional_mpd_has_no_connections_or_monitor_and_controls_are_explicit(tmp_path,monkeypatch):
    connect=Mock(side_effect=AssertionError('must not open sockets'))
    monkeypatch.setattr('app.integrations.MPD._connect',connect)
    app=create_app(Settings(database=str(tmp_path/'p.sqlite3')))
    with TestClient(app) as c:
        assert isinstance(app.state.player.mpd,DisabledMPD)
        assert app.state.player.thread is None
        config=c.get('/api/v1/config').json()
        assert config['mpd']=='disabled' and not config['mpd_configured']
        assert c.get('/api/health').status_code==200
        assert c.get('/api/v1/state').json()['error']==''
        for path,method,body in [('playback/play','POST',{}),('playback/toggle','POST',{}),('playback/next','POST',{}),('queue','POST',{'episode_id':1}),('mode/toggle','POST',{}),('timer','PUT',{'minutes':15})]:
            r=c.request(method,'/api/v1/'+path,json=body)
            assert r.status_code==503 and r.json()['error']['code']=='mpd_not_configured'
    connect.assert_not_called()


def test_browser_progress_and_candidates_never_change_mpd_queue_timer(rig):
    c,p,db,mpd,_=rig
    p.start_episode(2,announce=False);p.enqueue(3)
    before=(p.saved.copy(),p.queue(),list(mpd.calls))
    r=c.put('/api/v1/browser/progress',json={'episode_id':1,'position':30,'duration':100,'started':True})
    assert r.status_code==200
    r=c.put('/api/v1/browser/progress',json={'episode_id':1,'position':100,'duration':100,'completed':True})
    assert r.status_code==200 and p.episode(1)['completed']
    assert (p.saved,p.queue(),mpd.calls)==before
    ids=[e['id'] for e in c.get('/api/v1/browser/candidates?favorites_only=true').json()]
    assert set(ids)=={1,2,3}
    assert {e['id'] for e in c.get('/api/v1/browser/candidates?favorites_only=true&selection=random_unheard').json()}=={2,3}
    assert c.put('/api/v1/browser/progress',json={'episode_id':1,'position':-1}).status_code==422
    assert c.put('/api/v1/browser/progress',json={'episode_id':999,'position':0}).status_code==404


def test_browser_source_prefers_same_origin_download_without_mpd_url(download_rig):
    c,app,d,_,mpd=download_rig
    id_=complete_download(c,d)
    d.base_url=''
    mpd.unavailable=True
    r=c.get('/api/v1/browser/episodes/1/source')
    assert r.status_code==200 and r.json()['url']=='/downloads/'+id_
    assert c.get(r.json()['url'],headers={'Range':'bytes=0-9'}).status_code==206


def test_browser_local_source_needs_no_media_base_url(media_rig):
    c,app,_,path,mpd,_=media_rig
    ep=local_episode(app)
    app.state.media.base_url=''
    result=c.get(f"/api/v1/browser/episodes/{ep['id']}/source").json()
    assert result['url'].startswith('/media/')
    assert c.get(result['url']).status_code==200


def test_browser_proxy_stream_and_html_failure(rig,source):
    c,p,db,mpd,_=rig
    base,data,_=source
    db.execute('UPDATE episodes SET url=? WHERE id=1',(base+'/audio',))
    mpd.unavailable=True
    result=c.get('/api/v1/browser/episodes/1/source').json()
    assert result['url']=='/api/v1/browser/episodes/1/stream'
    r=c.get(result['url']);assert r.status_code==200 and r.content==data
    db.execute('UPDATE episodes SET url=? WHERE id=1',(base+'/html',))
    assert c.get(result['url']).status_code==502
    db.execute("UPDATE episodes SET source_type='web' WHERE id=1")
    assert c.get('/api/v1/browser/episodes/1/source').status_code==409


def test_browser_proxy_forwards_range_and_partial_response(rig):
    import threading
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    c,_,db,_,_=rig
    ranges=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            ranges.append(self.headers.get('Range'))
            self.send_response(206)
            self.send_header('Content-Type','audio/mpeg')
            self.send_header('Content-Range','bytes 4-12/100')
            self.send_header('Accept-Ranges','bytes')
            self.end_headers();self.wfile.write(b'123456789')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        db.execute('UPDATE episodes SET url=? WHERE id=1',(f'http://127.0.0.1:{server.server_port}/audio',))
        r=c.get('/api/v1/browser/episodes/1/stream',headers={'Range':'bytes=4-12'})
        assert r.status_code==206 and r.content==b'123456789'
        assert r.headers['content-range']=='bytes 4-12/100' and ranges==['bytes=4-12']
    finally:server.shutdown();server.server_close();thread.join()
