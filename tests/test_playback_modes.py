from pathlib import Path
import json

import pytest
from fastapi.testclient import TestClient
from app.api import create_app
from app.config import Settings
from app.db import Database
from app.player import PlayerError,Player
from conftest import FakeMPD,FakeNotifications


def test_fresh_defaults_are_normal_and_empty_play_does_not_random(tmp_path):
    app=create_app(Settings(database=str(tmp_path/'p.sqlite3')),mpd=FakeMPD(),background=False,notifications=FakeNotifications())
    with TestClient(app) as c:
        state=c.get('/api/v1/state').json()
        assert state['timer']['minutes']==0 and state['when_queue_empty']=='stop' and not state['sleep_mode']
        assert c.post('/api/v1/playback/play').status_code==409
        assert c.get('/api/v1/config').json()['sleep_defaults']=={'minutes':15,'when_queue_empty':'random_unheard'}


def test_normal_eof_stops_and_next_without_queue_keeps_current_playing(rig):
    c,p,db,mpd,_=rig
    c.post('/api/v1/playback/normal')
    c.post('/api/v1/episodes/play',json={'episode_id':1})
    assert c.post('/api/v1/playback/next').status_code==409 and mpd.state=='play'
    mpd.elapsed=1199;p.sync();mpd.state='stop';mpd.elapsed=0;p.sync()
    assert p.status['state']=='stop' and p.saved['episode_id']==1 and not p.error
    assert p.episode(1)['completed'] and not p.saved['timer_seconds']


def test_sleep_activation_and_end_never_restart_running_episode(rig):
    c,p,_,mpd,_=rig
    c.post('/api/v1/playback/normal');p.start_episode(1,announce=False);mpd.elapsed=82;p.sync()
    before=len([call for call in mpd.calls if call[0]=='start'])
    r=c.post('/api/v1/playback/sleep')
    assert r.status_code==200 and r.json()['sleep_mode']
    assert r.json()['timer']['minutes']==15 and r.json()['when_queue_empty']=='random_unheard'
    assert mpd.elapsed==82 and len([call for call in mpd.calls if call[0]=='start'])==before
    c.post('/api/v1/playback/toggle');assert mpd.state=='pause'
    r=c.post('/api/v1/playback/toggle');assert r.json()['sleep_mode'] and mpd.state=='play'
    r=c.post('/api/v1/playback/normal');assert not r.json()['sleep_mode'] and r.json()['when_queue_empty']=='stop'
    assert mpd.state=='pause' and mpd.elapsed==82


def test_sleep_config_persists_and_only_affects_next_activation(rig):
    c,p,db,mpd,_=rig
    p.start_episode(1,announce=False)
    old=(p.saved['timer_seconds'],p.saved['when_queue_empty'])
    data={'minutes':30,'when_queue_empty':'random'}
    assert c.put('/api/v1/config/sleep',json=data).json()==data
    assert (p.saved['timer_seconds'],p.saved['when_queue_empty'])==old
    assert Player(Database(db.path),mpd,FakeNotifications()).sleep_defaults()==data
    r=c.post('/api/v1/playback/sleep').json()
    assert r['timer']['minutes']==30 and r['when_queue_empty']=='random'
    assert c.put('/api/v1/config/sleep',json={'minutes':0,'when_queue_empty':'random'}).status_code==422
    assert c.put('/api/v1/config/sleep',json={'minutes':15,'when_queue_empty':'stop'}).status_code==422


def test_api_default_policy_resolves_config_and_explicit_policy_overrides(rig):
    c,p,_,_,_=rig
    c.post('/api/v1/playback/normal')
    c.put('/api/v1/config/sleep',json={'minutes':20,'when_queue_empty':'random'})
    r=c.post('/api/v1/playback/play',json={'timer':'default','when_queue_empty':'default'})
    assert r.status_code==200 and r.json()['timer']['minutes']==20 and r.json()['when_queue_empty']=='random'
    c.post('/api/v1/playback/toggle')
    r=c.post('/api/v1/playback/play',json={'when_queue_empty':'random_unheard'}).json()
    assert r['when_queue_empty']=='random_unheard'


def test_unheard_random_includes_started_restarts_and_never_repeats_completed(rig):
    c,p,db,mpd,_=rig
    db.execute('UPDATE episodes SET completed=1')
    db.execute('UPDATE episodes SET completed=0,position=450,last_started=10 WHERE id=3')
    r=c.post('/api/v1/playback/play',json={'when_queue_empty':'random_unheard'}).json()
    assert r['current']['id']==3 and mpd.elapsed==0
    assert p.random_episode()['id']==3
    db.execute('UPDATE episodes SET completed=1 WHERE id=3')
    assert p.random_episode() is None
    assert c.get('/api/v1/browser/candidates?selection=random_unheard').json()==[]
    p.saved['when_queue_empty']='random'
    assert len(c.get('/api/v1/browser/candidates?selection=random').json())==5
    assert p.random_episode() is not None


def test_queue_and_explicit_episode_resume_while_random_restarts(rig):
    c,p,db,mpd,_=rig
    db.execute('UPDATE episodes SET position=450 WHERE id=3')
    p.enqueue(3);p.play();assert p.saved['episode_id']==3 and mpd.elapsed==450
    c.post('/api/v1/episodes/play',json={'episode_id':3});assert mpd.elapsed==450
    assert c.get('/api/v1/state').json()['when_queue_empty']=='random_unheard'


def test_failed_sleep_start_rolls_back_normal_settings(rig):
    c,p,db,mpd,_=rig
    c.post('/api/v1/playback/normal');db.execute('UPDATE episodes SET completed=1')
    r=c.post('/api/v1/playback/sleep')
    assert r.status_code==409
    assert p.saved['timer_seconds']==0 and p.saved['when_queue_empty']=='stop'


def test_pwa_assets_are_served_with_manifest_mime_and_sw_scope(tmp_path):
    static=Path(__file__).resolve().parents[1]/'frontend'/'dist'
    app=create_app(Settings(database=str(tmp_path/'p.sqlite3'),static_dir=str(static)),background=False)
    with TestClient(app) as c:
        r=c.get('/manifest.webmanifest');assert r.status_code==200 and r.headers['content-type'].startswith('application/manifest+json')
        m=r.json();assert m['display']=='standalone' and m['scope']=='/' and m['start_url']=='/'
        assert {x['url'] for x in m['shortcuts']}=={'/#player','/#sleep','/#management'}
        for icon in m['icons']:assert c.get(icon['src']).status_code==200
        r=c.get('/sw.js');assert r.status_code==200 and r.headers['service-worker-allowed']=='/'
        assert r.headers['cache-control']=='no-cache'
        assert 'data-playpod-offline' in c.get('/offline.html').text


def test_sleep_after_completed_normal_episode_selects_an_unheard_episode(rig):
    c,p,db,mpd,_=rig
    c.post('/api/v1/playback/normal');p.start_episode(1,announce=False)
    mpd.elapsed=1199;p.sync();mpd.state='stop';mpd.elapsed=0;p.sync()
    assert p.episode(1)['completed']
    r=c.post('/api/v1/playback/sleep')
    assert r.status_code==200 and r.json()['current']['id']!=1
    assert mpd.elapsed==0


def test_english_pwa_manifest_and_release_version(rig):
    c,_,_,_,_=rig
    assert c.get('/api/live').json()['version']=='1.0.0'
    en=c.get('/manifest-en.webmanifest')
    assert en.status_code==200 and en.json()['lang']=='en'
    assert en.json()['shortcuts'][1]['name']=='Sleep'
    assert c.get('/manifest.webmanifest').json()['lang']=='de'
