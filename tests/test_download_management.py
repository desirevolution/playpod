import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from app.config import Settings
from app.db import Database
from app.downloads import Downloads
from app.player import PlayerError
from app import ytdlp
from test_downloads import source, download_rig, complete_download
from test_media import media_rig, local_episode


def test_delete_copy_preserves_episode_and_reverts_to_stream(download_rig):
    c, app, d, _, mpd = download_rig
    id_=complete_download(c,d)
    before=app.state.db.one('SELECT * FROM episodes WHERE id=1')
    assert c.get('/api/v1/downloads').json()['storage']['count']==1
    assert c.delete('/api/v1/episodes/1/download/file').status_code==200
    assert c.get('/downloads/'+id_).status_code==404
    after=app.state.db.one('SELECT * FROM episodes WHERE id=1')
    assert before==after
    assert c.get('/api/v1/downloads').json()['storage']['count']==0
    assert c.post('/api/v1/episodes/play',json={'episode_id':1}).json()['source_kind']=='remote'
    assert c.post('/api/v1/episodes/1/download').json()['id']!=id_


def test_copy_in_use_and_paused_protected_on_server(download_rig):
    c, app, d, _, mpd=download_rig
    complete_download(c,d)
    c.post('/api/v1/episodes/play',json={'episode_id':1})
    assert c.get('/api/v1/downloads').json()['items'][0]['in_use']
    assert c.delete('/api/v1/episodes/1/download/file').status_code==409
    c.post('/api/v1/playback/pause')
    mpd.song['file'] += '?cache=1'
    assert c.delete('/api/v1/episodes/1/download/file').status_code==409
    mpd.start('http://other.test/audio.mp3')
    assert c.delete('/api/v1/episodes/1/download/file').status_code==200


def test_delete_external_file_not_allowed(media_rig):
    c,app,_,path,_,_=media_rig
    id_=local_episode(app)['id']
    assert c.delete(f'/api/v1/episodes/{id_}/download/file').status_code==409
    assert path.exists()


def test_orphan_cleanup_ignores_external_names(download_rig):
    c,app,d,_,_=download_rig
    id_=complete_download(c,d)
    app.state.player.delete_episodes([1])
    extra=d.directory/'external.wav'
    extra.write_bytes(b'keep')
    status=c.get('/api/v1/downloads').json()
    assert status['storage']['orphan_bytes']>0
    assert c.post('/api/v1/downloads/cleanup').json()['deleted']==1
    assert extra.read_bytes()==b'keep'
    assert c.get('/api/v1/downloads').json()['storage']['orphan_bytes']==0


def test_feed_preview_and_bulk_are_explicit_idempotent(rig):
    c,player,db,_,_=rig
    c.app.state.downloads.base_url='http://playpod.test'
    db.execute('UPDATE episodes SET completed=1 WHERE id=2')
    db.execute('UPDATE episodes SET last_started=1 WHERE id=3')
    preview=c.get('/api/v1/feeds/1/downloads/preview').json()
    assert preview=={'count':1,'ids':[1]}
    assert not db.rows('SELECT * FROM downloads')
    assert c.post('/api/v1/feeds/1/downloads',json={'ids':[1]}).json()['added']==1
    assert c.post('/api/v1/feeds/1/downloads',json={'ids':[1]}).json()['added']==0
    assert c.get('/api/v1/feeds/1/downloads/preview').json()['count']==0
    assert c.post('/api/v1/feeds/1/downloads',json={'ids':[4]}).status_code==409


def test_page_link_real_ytdlp_ffmpeg_and_playback(download_rig, source):
    c,app,d,settings,mpd=download_rig
    base,_,_=source
    response=c.post('/api/v1/links',json={'url':base+'/episode.wav'})
    assert response.status_code==202
    id_=response.json()['episode_id']
    task_id=response.json()['id']
    assert c.post('/api/v1/links',json={'url':base+'/episode.wav'}).json()['id']==task_id
    assert c.post('/api/v1/episodes/play',json={'episode_id':id_}).status_code==409
    d.run_one()
    row=d.task(task_id)
    assert row['state']=='ready', row['error']
    ep=app.state.player.episode(id_)
    assert ep['source_type']=='web'
    assert ep['duration']>0
    assert ep['title']!=base+'/episode.wav'
    assert c.post('/api/v1/episodes/play',json={'episode_id':id_}).json()['source_kind']=='local'
    assert '/downloads/' in mpd.song['file']
    mpd.start('http://other.test/audio.mp3')
    assert c.delete(f'/api/v1/episodes/{id_}/download/file').status_code==200
    assert c.post('/api/v1/episodes/play',json={'episode_id':id_}).status_code==409
    assert app.state.player.random_episode()['id']==1


def test_ytdlp_can_be_disabled(download_rig, source):
    c,app,d,_,_=download_rig
    d.ytdlp_enabled=False
    assert c.post('/api/v1/links',json={'url':source[0]+'/episode.wav'}).status_code==409
    assert c.get('/api/v1/downloads').json()['ytdlp_enabled'] is False


def test_ytdlp_error_keeps_retryable_episode(download_rig, source):
    c,app,d,_,_=download_rig
    result=c.post('/api/v1/links',json={'url':source[0]+'/404'}).json()
    d.run_one()
    assert d.task(result['id'])['state']=='error'
    assert app.state.player.episode(result['episode_id'])['source_type']=='web'
    assert not list(d.directory.glob('.job-*'))
    assert c.post(f"/api/v1/episodes/{result['episode_id']}/download").json()['id']!=result['id']


def test_ytdlp_cancel_terminates_real_child(tmp_path, monkeypatch):
    original=subprocess.Popen
    processes=[]
    def spawn(*args,**kwargs):
        p=original([sys.executable,'-c','import time; time.sleep(120)'],**kwargs)
        processes.append(p)
        return p
    monkeypatch.setattr(ytdlp.subprocess,'Popen',spawn)
    def cancel():
        raise PlayerError('cancelled')
    with pytest.raises(PlayerError):
        ytdlp.extract('http://example.test',tmp_path/'job',1000000,10,cancel,lambda *a:None)
    assert processes[0].poll() is not None


def test_schema3_upgrade_keeps_downloads_and_backup(tmp_path):
    path=tmp_path/'old.sqlite3'
    db=Database(path)
    db.execute("INSERT INTO feeds(id,url,title) VALUES(1,'http://feed.test','One')")
    db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url,bookmarked,position) VALUES(1,1,'a','One','http://audio.test',1,12)")
    db.execute("INSERT INTO downloads(episode_id,id,source_url,state,updated) VALUES(1,'old','http://audio.test','ready',1)")
    db.execute('ALTER TABLE episodes DROP COLUMN source_type')
    db.execute('ALTER TABLE downloads DROP COLUMN phase')
    db.execute('DELETE FROM schema_migrations WHERE version=4')
    db.execute('PRAGMA user_version=3')
    new=Database(path)
    assert new.one('SELECT * FROM episodes')['source_type']=='audio'
    assert new.one('SELECT * FROM episodes')['bookmarked']==1
    assert new.one('SELECT * FROM episodes')['position']==12
    assert new.one('SELECT * FROM downloads')['id']=='old'
    with sqlite3.connect(str(path)+'.before-v4.sqlite3') as old:
        assert old.execute('PRAGMA user_version').fetchone()[0]==3


@pytest.mark.parametrize('info',[{'_type':'playlist','entries':[]},{'is_live':True}])
def test_runner_rejects_playlists_and_livestreams(tmp_path,monkeypatch,info):
    import yt_dlp
    from app.ytdlp_runner import run
    class Extractor:
        def __init__(self,options):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def extract_info(self,*args,**kwargs):return info
    monkeypatch.setattr(yt_dlp,'YoutubeDL',Extractor)
    with pytest.raises(ValueError):
        run('http://example.test/page',tmp_path,1000000)


def test_ytdlp_timeout_kills_child(tmp_path,monkeypatch):
    original=subprocess.Popen
    processes=[]
    def spawn(*args,**kwargs):
        p=original([sys.executable,'-c','import time; time.sleep(120)'],**kwargs)
        processes.append(p)
        return p
    monkeypatch.setattr(ytdlp.subprocess,'Popen',spawn)
    with pytest.raises(ValueError,match='Zeitlimit'):
        ytdlp.extract('http://example.test',tmp_path/'job',1000000,.1,lambda:None,lambda *a:None)
    assert processes[0].poll() is not None


def test_link_collection_can_be_favorited(download_rig,source):
    c,app,d,_,_=download_rig
    r=c.post('/api/v1/links',json={'url':source[0]+'/episode.wav'}).json()
    feed=app.state.db.one("SELECT * FROM feeds WHERE kind='links'")
    assert c.put('/api/v1/feeds/'+str(feed['id']),json={'url':feed['url'],'favorite':True}).status_code==200
    assert app.state.db.one('SELECT favorite FROM feeds WHERE id=?',(feed['id'],))['favorite']==1
