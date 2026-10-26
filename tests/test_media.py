import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import wave

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.db import Database, SCHEMA
from app.media import MediaLibrary, MediaError
from app.player import Player
from conftest import FakeMPD, FakeNotifications


def wav(path):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b'\0\0' * 8000)
    os.utime(path,(time.time()-30,time.time()-30))


@pytest.fixture
def media_rig(tmp_path):
    root=tmp_path/'downloads'
    root.mkdir()
    path=root/'Test Episode.wav'
    wav(path)
    config=Settings(database=str(tmp_path/'db.sqlite3'),media_roots=json.dumps({'Downloads':str(root)}),media_base_url='http://playpod.lan:9393',media_stable_seconds=5)
    mpd,notify=FakeMPD(),FakeNotifications()
    app=create_app(config,mpd=mpd,notifications=notify,background=False)
    app.state.media.scan(threading.Event(),lambda *a:None)
    # Existing playback regressions explicitly exercise the sleep setup.
    app.state.player.saved.update(timer_seconds=900, remaining=900, when_queue_empty='random_unheard')
    app.state.player.sync()
    with TestClient(app) as client:
        yield client,app,root,path,config,mpd


def local_episode(app):
    return app.state.db.one('SELECT * FROM episodes WHERE local_source IS NOT NULL')


def test_import_idempotent_keeps_progress_and_merker(media_rig):
    c,app,root,path,_,_=media_rig
    initial=c.get('/api/v1/activity').json()['items']
    assert len(initial)==1 and initial[0]['kind']=='feed_added' and initial[0]['count']==1
    ep=local_episode(app)
    assert ep['title']=='Test Episode'
    assert ep['duration']==pytest.approx(1)
    app.state.db.execute('UPDATE episodes SET bookmarked=1,position=0.5 WHERE id=?',(ep['id'],))
    app.state.media.scan(threading.Event(),lambda *a:None)
    rows=app.state.db.rows('SELECT * FROM episodes')
    assert len(rows)==1
    assert rows[0]['id']==ep['id']
    assert rows[0]['bookmarked']==1
    assert rows[0]['position']==0.5
    assert c.get('/api/v1/episodes?filter=local').json()['total']==1
    feed=c.get('/api/v1/feeds').json()[0]
    assert feed['kind']=='local'
    assert c.get('/api/v1/activity').json()['items']==initial


def test_real_http_range_head_suffix_and_invalid(media_rig):
    c,app,_,path,_,_=media_rig
    ep=local_episode(app)
    data=path.read_bytes()
    url=f"/media/{ep['id']}"
    assert c.get(url).content==data
    part=c.get(url,headers={'Range':'bytes=10-19'})
    assert part.status_code==206
    assert part.content==data[10:20]
    assert part.headers['content-range']==f'bytes 10-19/{len(data)}'
    assert part.headers['accept-ranges']=='bytes'
    assert c.get(url,headers={'Range':'bytes=-10'}).content==data[-10:]
    assert c.get(url,headers={'Range':f'bytes={len(data)+100}-'}).status_code==416
    head=c.head(url)
    assert head.status_code==200
    assert head.content==b''
    assert int(head.headers['content-length'])==len(data)
    assert head.headers['content-type']=='audio/wav'


def test_play_local_and_reconcile_after_restart(media_rig):
    c,app,_,_,config,mpd=media_rig
    ep=local_episode(app)
    response=c.post('/api/v1/episodes/play',json={'episode_id':ep['id']})
    assert response.status_code==200
    assert response.json()['source_kind']=='local'
    assert mpd.song['file'].startswith(f"http://playpod.lan:9393/media/{ep['id']}?v=")
    app.state.player.seek(0.5)
    restored=Player(app.state.db,mpd,FakeNotifications(),media=app.state.media)
    restored.sync()
    assert restored.saved['episode_id']==ep['id']
    assert restored.state()['source_kind']=='local'
    assert c.get('/api/v1/state').json()['current']['title']=='Test Episode'


def test_catalog_removal_never_deletes_file(media_rig):
    c,app,_,path,_,_=media_rig
    ep=local_episode(app)
    result=c.delete(f"/api/v1/episodes/{ep['id']}")
    assert result.json()['file_deleted'] is False
    assert path.exists()
    assert not app.state.db.rows('SELECT * FROM episodes')
    app.state.media.scan(threading.Event(),lambda *a:None)
    assert local_episode(app)


def test_missing_file_keeps_catalog_merker_and_progress(media_rig):
    c,app,_,path,_,_=media_rig
    ep=local_episode(app)
    app.state.db.execute('UPDATE episodes SET bookmarked=1,position=0.4 WHERE id=?',(ep['id'],))
    path.unlink()
    app.state.media.scan(threading.Event(),lambda *a:None)
    stored=local_episode(app)
    assert stored['source_present']==0
    assert stored['bookmarked']==1
    assert stored['position']==0.4
    assert c.get(f"/media/{ep['id']}").status_code==404


def test_sidecar_title_description_duration_and_sanitizing(media_rig):
    _,app,_,path,_,_=media_rig
    path.with_suffix('.info.json').write_text(json.dumps({'title':'Von yt-dlp','duration':42,'description':'Text\n<script>alert(1)</script>'}))
    app.state.media.scan(threading.Event(),lambda *a:None)
    ep=local_episode(app)
    assert ep['title']=='Von yt-dlp'
    assert ep['duration']==42
    assert '<script>' not in ep['description']
    assert '&lt;script&gt;' in ep['description']


def test_symlinks_partial_files_and_recent_files_ignored(media_rig):
    c,app,root,path,_,_=media_rig
    (root/'alias.wav').symlink_to(path)
    (root/'not-audio.txt').write_text('x')
    (root/'partial.wav.part').write_bytes(b'x')
    fresh=root/'fresh.wav'
    wav(fresh)
    os.utime(fresh,None)
    app.state.media.scan(threading.Event(),lambda *a:None)
    assert len(app.state.db.rows('SELECT * FROM episodes'))==1


def test_changed_file_requires_rescan(media_rig):
    c,app,_,path,_,_=media_rig
    ep=local_episode(app)
    with path.open('ab') as f:f.write(b'xx')
    assert c.get(f"/media/{ep['id']}").status_code==404
    os.utime(path,(time.time()-30,time.time()-30))
    app.state.media.scan(threading.Event(),lambda *a:None)
    assert c.get(f"/media/{ep['id']}").status_code==200


def test_path_traversal_and_outside_symlink_not_served(media_rig,tmp_path):
    c,app,root,path,_,_=media_rig
    ep=local_episode(app)
    outside=tmp_path/'outside.wav'
    wav(outside)
    app.state.db.execute("UPDATE episodes SET local_source='../outside.wav' WHERE id=?",(ep['id'],))
    assert c.get(f"/media/{ep['id']}").status_code==404
    app.state.db.execute("UPDATE episodes SET local_source='link.wav' WHERE id=?",(ep['id'],))
    (root/'link.wav').symlink_to(outside)
    assert c.get(f"/media/{ep['id']}").status_code==404


def test_local_preferred_remote_fallback_and_no_base_url(media_rig):
    c,app,_,path,config,_=media_rig
    ep=local_episode(app)
    app.state.db.execute("UPDATE episodes SET url='http://source.test/audio.wav' WHERE id=?",(ep['id'],))
    ep=local_episode(app)
    assert app.state.media.playback_url(ep)[1]=='local'
    path.unlink()
    assert app.state.media.playback_url(ep)==('http://source.test/audio.wav','remote')


def test_local_favorite_works_and_rss_refresh_skips_local(media_rig,monkeypatch):
    c,app,_,_,_,_=media_rig
    feed=c.get('/api/v1/feeds').json()[0]
    assert c.put(f"/api/v1/feeds/{feed['id']}",json={'url':feed['url'],'title':feed['title'],'favorite':True}).status_code==200
    assert c.get('/api/v1/feeds').json()[0]['favorite']==1
    def forbidden(*args,**kwargs):raise AssertionError('No HTTP requests for local files')
    monkeypatch.setattr('app.feeds.requests.get',forbidden)
    jobs=app.state.jobs
    id_=jobs.start_job('refresh')
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        row=c.get('/api/v1/jobs/'+id_).json()
        if row['state']!='running':break
        time.sleep(.01)
    assert row['state']=='done'
    assert row['total']==0


def test_invalid_media_config_rejected(media_rig):
    _,app,_,_,_,_=media_rig
    with pytest.raises(ValueError):
        MediaLibrary(app.state.db,Settings(media_roots='["/tmp"]'))
    with pytest.raises(ValueError):
        MediaLibrary(app.state.db,Settings(media_roots='{"x":"relative"}'))


def test_database_v1_migration_is_backed_up_and_non_destructive(tmp_path):
    path=tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute('PRAGMA user_version=1')
        db.execute("INSERT INTO schema_migrations VALUES(1)")
        db.execute("INSERT INTO feeds(id,url,title) VALUES(1,'http://example.test/feed','Alt')")
        db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url,position,bookmarked) VALUES(7,1,'key','Altfolge','http://example.test/a.mp3',123,1)")
        db.execute("INSERT INTO queue VALUES(7,0,'')")
    new=Database(path)
    ep=new.one('SELECT * FROM episodes WHERE id=7')
    assert ep['position']==123 and ep['bookmarked']==1
    assert new.one('SELECT * FROM queue')['episode_id']==7
    assert new.one('PRAGMA user_version')['user_version']==6
    backup=Path(str(path)+'.before-v2.sqlite3')
    assert backup.exists()
    with sqlite3.connect(backup) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==1
        assert db.execute('SELECT position FROM episodes WHERE id=7').fetchone()[0]==123
    Database(path)  # An already upgraded database must reopen cleanly.


def test_root_unavailable_marks_missing_without_deleting_state(media_rig):
    _,app,root,path,_,_=media_rig
    ep=local_episode(app)
    app.state.db.execute('UPDATE episodes SET bookmarked=1 WHERE id=?',(ep['id'],))
    root.rename(root.with_name('offline'))
    result=app.state.media.scan(threading.Event(),lambda *a:None)
    assert not result[0]['ok']
    stored=local_episode(app)
    assert stored['source_present']==0
    assert stored['bookmarked']==1


def test_missing_media_base_url_returns_clear_error(media_rig):
    c,app,_,_,_,_=media_rig
    ep=local_episode(app)
    app.state.media.base_url=''
    response=c.post('/api/v1/episodes/play',json={'episode_id':ep['id']})
    assert response.status_code==409
    assert 'MEDIA_BASE_URL' in response.json()['error']['message']


def test_media_scan_job_imports_new_files(media_rig):
    c,app,root,_,_,_=media_rig
    wav(root/'Second.wav')
    job_id=c.post('/api/v1/media/scan').json()['job_id']
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
        job=c.get('/api/v1/jobs/'+job_id).json()
        if job['state']!='running':break
        time.sleep(.01)
    assert job['state']=='done'
    assert job['results'][0]['count']==2
    assert c.get('/api/v1/episodes?filter=local').json()['total']==2


def test_recent_overwrite_is_pending_until_rescan(media_rig):
    c,app,_,path,_,_=media_rig
    ep=local_episode(app)
    os.utime(path,None)
    app.state.media.scan(threading.Event(),lambda *a:None)
    assert local_episode(app)['availability']=='local_pending'
    os.utime(path,(time.time()-30,time.time()-30))
    app.state.media.scan(threading.Event(),lambda *a:None)
    assert local_episode(app)['source_present']==1


def test_disabled_root_is_not_randomly_selected(media_rig):
    _,app,_,_,_,_=media_rig
    MediaLibrary(app.state.db,Settings())
    assert app.state.player.random_episode() is None
    assert local_episode(app)['availability']=='local_unconfigured'


def test_empty_mpd_does_not_match_local_episode_with_empty_url(media_rig):
    _,app,_,_,_,_=media_rig
    app.state.player.sync()
    assert app.state.player.saved['episode_id'] is None
