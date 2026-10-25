import time
from uuid import uuid4
import pytest
from test_downloads import source, download_rig


def copies(rig):
    c,app,d,_,mpd=rig
    db=app.state.db
    for id_ in (2,3):
        db.execute('INSERT INTO episodes(id,feed_id,source_key,title,url,completed) VALUES(?,1,?,?,?,?)',(id_,str(id_),f'Episode {id_}',f'http://audio/{id_}',1 if id_==2 else 0))
    db.execute('UPDATE episodes SET completed=1 WHERE id=1')
    for id_ in (1,2,3):
        token=str(uuid4())
        (d.directory/(token+'.audio')).write_bytes(b'audio')
        db.execute("INSERT INTO downloads(episode_id,id,source_url,state,received,updated) VALUES(?,?,?,'ready',5,?)",(id_,token,f'http://audio/{id_}',time.time()))
    return c,app,d,mpd


def test_bulk_deletes_only_finished_copies_and_keeps_catalog(download_rig):
    c,app,d,mpd=copies(download_rig)
    before=app.state.db.rows('SELECT * FROM episodes ORDER BY id')
    assert c.get('/api/v1/feeds/1/downloads/completed').json()=={'count':2,'bytes':10}
    result=c.delete('/api/v1/feeds/1/downloads/completed')
    assert result.status_code==200 and result.json()=={'deleted':2,'skipped':0,'failed':0}
    assert app.state.db.rows('SELECT * FROM episodes ORDER BY id')==before
    assert app.state.db.one('SELECT state FROM downloads WHERE episode_id=3')['state']=='ready'
    assert c.delete('/api/v1/feeds/1/downloads/completed').json()['deleted']==0
    assert c.delete('/api/v1/feeds/999/downloads/completed').status_code==404


def test_bulk_skips_mpd_and_browser_copies(download_rig):
    c,app,d,mpd=copies(download_rig)
    mpd.start(d.playback_url(1))
    response=c.put('/api/v1/browser/progress',json={'episode_id':2,'position':2,'playback_id':'browser','in_use':True})
    assert response.status_code==200
    result=c.delete('/api/v1/feeds/1/downloads/completed').json()
    assert result=={'deleted':0,'skipped':2,'failed':0}
    assert c.delete('/api/v1/episodes/2/download/file').status_code==409
    mpd.call('clear')
    c.put('/api/v1/browser/progress',json={'episode_id':2,'position':2,'playback_id':'browser','in_use':False})
    assert c.delete('/api/v1/feeds/1/downloads/completed').json()['deleted']==2


def test_bulk_requires_mpd_usage_check_and_protects_announcement_resume(download_rig):
    c,app,d,mpd=copies(download_rig)
    mpd.unavailable=True
    assert c.delete('/api/v1/feeds/1/downloads/completed').status_code==503
    assert len(d.managed_files())==3
    mpd.unavailable=False
    app.state.player.saved['intro']={'kind':'custom','resume':{'song':{'file':d.playback_url(1)}}}
    assert c.delete('/api/v1/feeds/1/downloads/completed').json()=={'deleted':1,'skipped':1,'failed':0}
    app.state.player.saved.pop('intro')


def test_browser_usage_expires_and_other_sessions_stay_protected(download_rig,monkeypatch):
    c,app,d,mpd=copies(download_rig)
    now=[1000.]
    monkeypatch.setattr('app.downloads.time.monotonic',lambda:now[0])
    d.browser_usage('one',1,True)
    d.browser_usage('two',1,True)
    d.browser_usage('one',1,False)
    assert d.browser_in_use(1)
    now[0]+=91
    assert not d.browser_in_use(1)
    assert c.delete('/api/v1/feeds/1/downloads/completed').json()['deleted']==2
