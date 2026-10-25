from unittest.mock import Mock

import pytest

from app.player import Player


@pytest.fixture
def sleep_rig(rig):
    c,p,db,mpd,n=rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    return c,p,db,mpd,n,now


@pytest.mark.parametrize('action',['play','toggle'])
@pytest.mark.parametrize('minutes',[15,30])
def test_resume_restarts_selected_period_and_pause_does_not_count(sleep_rig,action,minutes):
    c,p,_,mpd,_,now=sleep_rig
    p.timer(minutes*60)
    now[0]+=180
    c.post('/api/v1/playback/pause')
    assert p.remaining()==minutes*60-180
    now[0]+=7200
    p.sync()
    assert p.remaining()==minutes*60-180
    s=c.post('/api/v1/playback/'+action).json()
    assert s['state']=='play' and s['timer']['remaining']==minutes*60
    now[0]+=minutes*60+1
    p.sync()
    assert mpd.state=='pause' and p.remaining()==0
    s=c.post('/api/v1/playback/play').json()
    assert s['timer']['remaining']==minutes*60 and s['state']=='play'


@pytest.mark.parametrize('body',[None,{'timer':'keep'},{'timer':'default'}])
def test_manual_next_restarts_period_with_or_without_option(sleep_rig,body):
    c,p,_,_,_,now=sleep_rig
    p.timer(1800)
    p.enqueue(2)
    now[0]+=300
    s=c.post('/api/v1/playback/next',**({'json':body} if body is not None else {})).json()
    period=900 if body=={'timer':'default'} else 1800
    assert s['current']['id']==2 and s['timer']['remaining']==period
    assert s['timer']['minutes']==period/60


def test_selected_episode_start_restarts_timer_and_natural_eof_does_not(sleep_rig):
    c,p,_,mpd,_,now=sleep_rig
    now[0]+=200
    s=c.post('/api/v1/episodes/play',json={'episode_id':2}).json()
    assert s['timer']['remaining']==900
    p.enqueue(3)
    now[0]+=300
    mpd.elapsed=1199
    p.sync()
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.saved['episode_id']==3 and p.remaining()==600
    now[0]+=601
    p.sync()
    assert mpd.state=='pause'


def test_manual_next_can_restart_just_before_old_deadline_during_tts_request(sleep_rig):
    c,p,_,_,n,now=sleep_rig
    p.enqueue(2)
    now[0]+=899
    def generate(_):
        now[0]+=3
        return None
    n.title_audio=generate
    s=c.post('/api/v1/playback/next').json()
    assert s['state']=='play' and s['current']['id']==2
    assert s['timer']['remaining']==900


def test_title_speech_waits_for_episode_before_starting_rearmed_timer(sleep_rig):
    c,p,_,mpd,n,now=sleep_rig
    n.title_audio=Mock(return_value='http://ha.test/title.wav')
    p.enqueue(2)
    now[0]+=899
    s=c.post('/api/v1/playback/next').json()
    assert s['phase']=='announcement' and s['timer']['remaining']==900
    assert s['timer']['suspended']
    now[0]+=3
    p.sync()
    assert p.remaining()==900 and mpd.state=='play'
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.saved['episode_id']==2 and p.remaining()==900
    now[0]+=10
    assert p.remaining()==890


def test_resume_during_existing_title_rearms_timer_without_consuming_speech(sleep_rig):
    c,p,_,mpd,n,now=sleep_rig
    n.title_audio=Mock(return_value='http://ha.test/title.wav')
    p.start_episode(2)
    now[0]+=100
    p.pause()
    now[0]+=1000
    s=c.post('/api/v1/playback/toggle').json()
    assert s['phase']=='announcement' and s['timer']['remaining']==900
    now[0]+=3
    p.sync()
    assert p.remaining()==900
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.saved['episode_id']==2 and p.remaining()==900


def test_timer_off_remains_off_without_remote_default(sleep_rig):
    c,p,_,_,_,now=sleep_rig
    p.timer(0)
    p.pause();now[0]+=1000
    assert not c.post('/api/v1/playback/play').json()['timer']['enabled']
    p.enqueue(2)
    assert not c.post('/api/v1/playback/next').json()['timer']['enabled']
    assert c.post('/api/v1/playback/next',json={'timer':'default'}).json()['timer']['remaining']==900


def test_failed_next_keeps_previous_timer_deadline(sleep_rig):
    c,p,db,_,_,now=sleep_rig
    db.execute('DELETE FROM episodes WHERE id<>1')
    p.mode=True
    db.execute('UPDATE feeds SET favorite=0')
    now[0]+=300
    deadline=p.saved['deadline']
    r=c.post('/api/v1/playback/next')
    assert r.status_code==409 and p.saved['deadline']==deadline and p.remaining()==600


def test_restart_during_playback_does_not_rearm_timer_but_user_resume_does(sleep_rig):
    c,p,db,mpd,n,now=sleep_rig
    now[0]+=100
    p.persist()
    restored=Player(db,mpd,n,clock=lambda:now[0])
    restored.sync()
    assert restored.remaining()==800
    restored.pause();now[0]+=200
    restored.play()
    assert restored.remaining()==900


def test_external_mpd_pause_resume_restarts_selected_period(sleep_rig):
    c,p,_,mpd,_,now=sleep_rig
    now[0]+=60
    mpd.state='pause';p.sync()
    assert p.remaining()==840
    now[0]+=1000
    mpd.state='play';p.sync()
    assert p.remaining()==900


def test_manual_resume_of_mode_rearms_interrupted_title_until_episode(sleep_rig):
    c,p,_,mpd,n,now=sleep_rig
    n.title_audio=Mock(side_effect=lambda text:'http://ha.test/mode.wav' if text=='Favoriten' else 'http://ha.test/title.wav')
    p.start_episode(2)
    now[0]+=100
    p.set_mode(True)
    p.pause();now[0]+=1000
    p.play()
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.state()['announcement_kind']=='title' and p.state()['timer']['suspended']
    now[0]+=3
    p.sync()
    assert p.remaining()==900
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.saved['episode_id']==2 and p.remaining()==900


def test_automatic_source_error_does_not_extend_sleep_timer(sleep_rig):
    c,p,_,mpd,_,now=sleep_rig
    p.enqueue(2)
    now[0]+=300
    mpd.error='decoder failure'
    p.sync()
    assert p.saved['episode_id']==2 and p.remaining()==600


def test_changing_timer_during_manual_next_title_waits_for_actual_episode(sleep_rig):
    c,p,_,mpd,n,now=sleep_rig
    n.title_audio=Mock(return_value='http://ha.test/title.wav')
    p.enqueue(2)
    c.post('/api/v1/playback/next')
    c.put('/api/v1/timer',json={'minutes':30})
    now[0]+=5
    p.sync()
    assert p.remaining()==1800 and p.saved['deadline'] is None
    mpd.state='stop';mpd.elapsed=0
    p.sync()
    assert p.remaining()==1800


@pytest.mark.parametrize('action', ['play', 'toggle'])
def test_ui_resume_preserves_remaining_and_extension_while_api_still_restarts(sleep_rig, action):
    c,p,_,mpd,_,now=sleep_rig
    now[0]+=120
    c.post('/api/v1/playback/pause')
    assert p.remaining()==780
    assert c.post('/api/v1/timer/extend',json={'minutes':5}).status_code==200
    assert p.remaining()==1080
    now[0]+=3600
    result=c.post('/api/v1/playback/'+action,json={'timer':'preserve'})
    assert result.status_code==200 and result.json()['timer']['remaining']==1080
    assert mpd.state=='play'
    now[0]+=15
    c.post('/api/v1/playback/pause')
    assert p.remaining()==1065
    c.post('/api/v1/playback/'+action)
    assert p.remaining()==900


def test_ending_sleep_pauses_and_disables_timer_and_random(sleep_rig):
    c,p,_,mpd,_,now=sleep_rig
    now[0]+=120
    result=c.post('/api/v1/playback/normal')
    assert result.status_code==200
    state=result.json()
    assert state['state']=='pause' and mpd.state=='pause'
    assert not state['sleep_mode'] and not state['timer']['enabled']
    assert state['when_queue_empty']=='stop'
    now[0]+=3600
    assert p.remaining()==0


def test_ui_play_after_expiry_starts_a_new_period(sleep_rig):
    c,p,_,mpd,_,now=sleep_rig
    now[0]+=901
    p.sync()
    assert mpd.state=='pause' and p.remaining()==0
    r=c.post('/api/v1/playback/toggle',json={'timer':'preserve'})
    assert r.status_code==200 and r.json()['state']=='play'
    assert r.json()['timer']['remaining']==900
