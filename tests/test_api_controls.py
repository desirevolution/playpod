from concurrent.futures import ThreadPoolExecutor
import threading

import pytest


def test_remote_toggle_starts_with_default_after_timer_disabled(rig):
    c,p,_,_,_=rig
    p.timer(0)
    r=c.post('/api/v1/playback/toggle',json={'timer':'default'})
    assert r.status_code==200
    s=r.json()
    assert s['state']=='play'
    assert s['timer']=={'enabled':True,'minutes':15,'remaining':pytest.approx(900,abs=1),'run_active':True,'suspended':False}


@pytest.mark.parametrize('action',['play','toggle'])
def test_remote_resume_resets_timer_but_toggle_pause_does_not(rig,action):
    c,p,_,_,_=rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1)
    p.timer(1800)
    p.pause()
    s=c.post('/api/v1/playback/'+action,json={'timer':'default'}).json()
    assert s['state']=='play' and s['timer']['remaining']==900
    now[0]+=10
    s=c.post('/api/v1/playback/toggle',json={'timer':'default'}).json()
    assert s['state']=='pause' and s['timer']['remaining']==890
    now[0]+=100
    assert p.remaining()==890


def test_explicit_play_while_playing_does_not_rearm_timer(rig):
    c,p,_,_,_=rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1)
    now[0]+=100
    s=c.post('/api/v1/playback/play',json={'timer':'default'}).json()
    assert s['timer']['remaining']==800
    assert s['current']['id']==1


@pytest.mark.parametrize('body',[None,{}, {'timer':'keep'}])
def test_ui_toggle_preserves_disabled_timer(rig,body):
    c,p,_,_,_=rig
    p.start_episode(1)
    p.timer(0)
    p.pause()
    r=c.post('/api/v1/playback/toggle',**({'json':body} if body is not None else {}))
    assert r.status_code==200
    assert r.json()['state']=='play'
    assert not r.json()['timer']['enabled']


def test_remote_episode_start_and_manual_next_restart_timer(rig):
    c,p,_,_,_=rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.timer(0)
    s=c.post('/api/v1/episodes/play',json={'episode_id':1,'timer':'default'}).json()
    assert s['timer']['remaining']==900
    p.enqueue(2)
    now[0]+=30
    s=c.post('/api/v1/playback/next').json()
    assert s['current']['id']==2 and s['timer']['remaining']==900


def test_failed_default_start_restores_timer_configuration(rig):
    c,p,_,_,_=rig
    p.timer(0)
    before=p.state()['timer']
    r=c.post('/api/v1/episodes/play',json={'episode_id':999,'timer':'default'})
    assert r.status_code==404
    assert p.state()['timer']==before
    assert p.saved['preset_pending']


@pytest.mark.parametrize('action',['pause','undo'])
def test_default_timer_is_rejected_on_non_start_actions(rig,action):
    c,p,_,_,_=rig
    p.clock=lambda:1000.
    p.start_episode(1)
    before=p.state()
    assert c.post('/api/v1/playback/'+action,json={'timer':'default'}).status_code==422
    assert p.state()==before


def test_relative_seek_uses_latest_mpd_position_and_clamps(rig):
    c,p,_,mpd,_=rig
    p.start_episode(1)
    mpd.elapsed=100
    assert c.post('/api/v1/seek',json={'offset_seconds':30}).json()['elapsed']==pytest.approx(130,abs=.1)
    assert mpd.elapsed==130
    assert c.post('/api/v1/seek',json={'offset_seconds':-300}).json()['elapsed']==pytest.approx(0,abs=.1)
    assert mpd.elapsed==0
    p.pause()
    assert c.post('/api/v1/seek',json={'position_seconds':9999}).json()['elapsed']==1200


@pytest.mark.parametrize('body',[{}, {'seconds':30}, {'position_seconds':5,'offset_seconds':30},
    {'position_seconds':-1}, {'offset_seconds':'Infinity'}, {'offset_seconds':5,'typo':True}])
def test_seek_rejects_ambiguous_or_invalid_input(rig,body):
    c,*_=rig
    r=c.post('/api/v1/seek',json=body)
    assert r.status_code==422
    assert r.json()['error']['code']=='validation_error'
    assert isinstance(r.json()['error']['details'],list)


def test_relative_volume_atomic_under_concurrent_requests(rig):
    c,p,_,mpd,_=rig
    gate=threading.Barrier(4)
    def adjust(_):
        gate.wait(timeout=5)
        r=c.post('/api/v1/volume/adjust',json={'delta':5})
        assert r.status_code==200
        return r.json()['volume']
    with ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(adjust,range(4)))
    assert sorted(values)==[60,65,70,75]
    assert mpd.volume==75
    assert c.post('/api/v1/volume/adjust',json={'delta':100}).json()['volume']==100
    assert c.post('/api/v1/volume/adjust',json={'delta':-100}).json()['volume']==0


def test_mixer_unavailable_and_mpd_offline_are_reported(rig):
    c,p,_,mpd,_=rig
    mpd.volume=-1
    r=c.post('/api/v1/volume/adjust',json={'delta':5})
    assert r.status_code==409 and r.json()['error']['code']=='mixer_unavailable'
    assert not any(call[0]=='setvol' for call in mpd.calls)
    mpd.unavailable=True
    for path,body in [('playback/toggle',{'timer':'default'}),('volume/adjust',{'delta':5}),('seek',{'offset_seconds':30})]:
        r=c.post('/api/v1/'+path,json=body)
        assert r.status_code==503 and r.json()['error']['code']=='mpd_unavailable'


def test_mode_and_parametrized_timer_extension(rig):
    c,p,_,_,_=rig
    assert c.put('/api/v1/mode',json={'favorites_only':True}).json()['favorites_only']
    assert not c.post('/api/v1/mode/toggle').json()['favorites_only']
    assert c.put('/api/v1/mode',json={'value':True}).status_code==422
    p.timer(0)
    assert c.post('/api/v1/timer/extend',json={'minutes':10}).status_code==409
    assert c.put('/api/v1/timer',json={'minutes':17}).json()['timer']['minutes']==17
    assert c.post('/api/v1/timer/extend',json={'minutes':10}).json()['timer']['remaining']==1620
    assert c.post('/api/v1/timer/extend').json()['timer']['remaining']==1920


def test_openapi_and_job_acceptance_contract(rig,monkeypatch):
    c,p,_,_,_=rig
    monkeypatch.setattr(c.app.state.jobs,'start_job',lambda *a,**k:'job-123')
    for path in ['feeds/refresh','feeds/1/refresh','media/scan','cleanup/checks']:
        r=c.post('/api/v1/'+path)
        assert r.status_code==202
        assert r.json()=={'job_id':'job-123','status_url':'/api/v1/jobs/job-123'}
    schema=c.get('/openapi.json').json()
    assert '/api/play' not in schema['paths']
    response=schema['paths']['/api/v1/playback/{action}']['post']['responses']['200']
    assert response['content']['application/json']['schema']['$ref'].endswith('/PlayerResult')
    assert not schema['components']['schemas']['SeekInput']['additionalProperties']


def test_unknown_fields_rejected_for_management_and_queue(rig):
    c,*_=rig
    for method,path,body in [('post','queue',{'episode_id':1,'typo':True}),
                            ('post','feeds',{'url':'https://example.test/rss','typo':True}),
                            ('post','playback/toggle',{'timre':'default'})]:
        assert getattr(c,method)('/api/v1/'+path,json=body).status_code==422


@pytest.mark.parametrize('initial',['playing','paused','stopped'])
def test_next_with_default_timer_starts_queue_after_timer_off(rig,initial):
    c,p,_,mpd,_=rig
    if initial!='stopped':
        p.start_episode(1)
        if initial=='paused':p.pause()
    p.timer(0)
    p.enqueue(2)
    s=c.post('/api/v1/playback/next',json={'timer':'default'}).json()
    assert s['state']=='play' and s['current']['id']==2
    assert s['timer']['enabled'] and s['timer']['minutes']==15
    assert s['timer']['remaining']==pytest.approx(900,abs=1)


def test_next_default_timer_failure_restores_previous_setting(rig):
    c,p,db,_,_=rig
    p.timer(0)
    db.execute('DELETE FROM episodes')
    assert c.post('/api/v1/playback/next',json={'timer':'default'}).status_code==409
    assert not p.state()['timer']['enabled'] and p.saved['preset_pending']
