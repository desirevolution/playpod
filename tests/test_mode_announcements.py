from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.player import Player

TITLE='http://ha.test/title.wav'
FAVORITES='http://ha.test/favorites.wav'
NORMAL='http://ha.test/normal.wav'


@pytest.fixture
def mode_rig(rig):
    c,p,db,mpd,n=rig
    n.settings=SimpleNamespace(tts_playback_timeout_seconds=120)
    n.title_audio=Mock(side_effect=lambda text: FAVORITES if text=='Favoriten' else NORMAL if text=='Normal' else TITLE)
    original=mpd.start
    def start(url,position=0,**kwargs):
        mpd.duration=2 if url in (TITLE,FAVORITES,NORMAL) else 1200
        return original(url,position,**kwargs)
    mpd.start=start
    return rig


def finish(p,mpd):
    mpd.state='stop'
    mpd.elapsed=0
    p.sync()


@pytest.mark.parametrize('state',['play','pause','stop','empty'])
def test_mode_speaks_in_every_state_and_restores_without_queue_changes(mode_rig,state):
    c,p,db,mpd,n=mode_rig
    if state!='empty':
        p.start_episode(1,announce=False)
        mpd.elapsed=123
        p.sync()
        if state=='pause':p.pause()
        elif state=='stop':mpd.call('stop');p.sync()
    p.enqueue(2)
    revision=p.revision
    before=p.episode(1)
    r=c.post('/api/v1/mode/toggle')
    assert r.status_code==200
    s=r.json()
    assert s['favorites_only']
    assert s['phase']=='announcement' and s['announcement_kind']=='mode'
    assert s['announcement_text']=='Favoriten' and s['timer']['suspended']
    assert mpd.song['file']==FAVORITES and mpd.state=='play'
    p._checkpoint()
    assert p.episode(1)==before
    finish(p,mpd)
    assert p.state()['phase']=='episode'
    assert mpd.state==('stop' if state in ('stop','empty') else state)
    if state in ('play','pause'):
        assert mpd.song['file'].endswith('/1.mp3') and mpd.elapsed==123
    assert p.episode(1)==before
    assert [e['id'] for e in p.queue()]==[2] and p.revision==revision
    n.title_audio.assert_called_once_with('Favoriten')


def test_mode_freezes_timer_and_progress_until_restoration(mode_rig):
    c,p,_,mpd,_=mode_rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    p.timer(1800)
    now[0]+=10
    mpd.elapsed=88
    p.set_mode(True)
    assert p.remaining()==1790
    now[0]+=30
    p.sync()
    assert p.remaining()==1790 and p.state()['elapsed']==88
    finish(p,mpd)
    assert p.remaining()==1790 and mpd.elapsed==88
    now[0]+=5
    assert p.remaining()==1785


def test_mode_from_idle_does_not_begin_run_or_consume_timer(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.timer(1800)
    p.set_mode(True)
    assert not p.saved['run_active'] and p.saved['preset_pending']
    finish(p,mpd)
    p.sync()
    assert mpd.state=='stop' and not p.saved['run_active']
    assert p.remaining()==1800 and p.saved['preset_pending']


def test_mode_interrupts_title_and_resumes_its_position_without_repeating_request(mode_rig):
    c,p,db,mpd,n=mode_rig
    db.execute('UPDATE episodes SET position=42 WHERE id=1')
    p.enqueue(1)
    p.start_episode(1)
    mpd.elapsed=1.2
    p.set_mode(True)
    assert p.state()['elapsed']==42
    assert p.episode(1)['last_started'] is None
    finish(p,mpd)
    assert p.state()['announcement_kind']=='title'
    assert mpd.song['file']==TITLE and mpd.elapsed==1.2
    assert [e['id'] for e in p.queue()]==[1]
    finish(p,mpd)
    assert mpd.song['file'].endswith('/1.mp3') and mpd.elapsed==42
    assert not p.queue()
    assert [c.args[0] for c in n.title_audio.call_args_list]==['Episode 1','Favoriten']


def test_repeated_toggles_replace_mode_speech_keep_one_return_context(mode_rig):
    c,p,_,mpd,n=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=75
    p.set_mode(True)
    p.set_mode(False)
    assert mpd.song['file']==NORMAL
    assert p.state()['announcement_text']=='Normal'
    assert not p.saved['intro']['resume']['playback'].get('intro')
    finish(p,mpd)
    assert mpd.song['file'].endswith('/1.mp3') and mpd.elapsed==75
    assert [c.args[0] for c in n.title_audio.call_args_list]==['Favoriten','Normal']


def test_idempotent_mode_put_does_not_repeat_speech(mode_rig):
    c,p,_,mpd,n=mode_rig
    p.set_mode(True)
    calls=len(mpd.calls)
    r=c.put('/api/v1/mode',json={'favorites_only':True})
    assert r.status_code==200 and len(mpd.calls)==calls
    n.title_audio.assert_called_once_with('Favoriten')


def test_mode_start_failure_restores_source_and_still_changes_mode(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    p.pause()
    mpd.elapsed=60
    mpd.bad_urls.add(FAVORITES)
    r=c.post('/api/v1/mode/toggle')
    assert r.status_code==200 and r.json()['favorites_only']
    assert mpd.state=='pause' and mpd.song['file'].endswith('/1.mp3')
    assert mpd.elapsed==60 and not p.saved.get('intro')


def test_async_mode_decode_failure_and_timeout_return_to_source(mode_rig):
    c,p,_,mpd,_=mode_rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    p.set_mode(True)
    mpd.error='bad announcement'
    p.sync()
    assert mpd.song['file'].endswith('/1.mp3')
    p.set_mode(False)
    now[0]+=121
    p.sync()
    assert mpd.song['file'].endswith('/1.mp3') and not p.saved.get('intro')


def test_pause_mode_suspends_its_timeout_and_restores_prior_pause(mode_rig):
    c,p,_,mpd,_=mode_rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    p.pause()
    p.set_mode(True)
    now[0]+=30
    p.pause()
    now[0]+=200
    p.sync()
    assert p.state()['announcement_kind']=='mode' and mpd.state=='pause'
    p.play()
    now[0]+=89
    p.sync()
    assert p.state()['announcement_kind']=='mode'
    now[0]+=2
    p.sync()
    assert mpd.state=='pause' and mpd.song['file'].endswith('/1.mp3')


def test_mode_return_context_survives_restart_and_stopped_restart_waits(mode_rig):
    c,p,db,mpd,n=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=67
    p.set_mode(True)
    restored=Player(db,mpd,n)
    restored.sync()
    assert restored.state()['announcement_kind']=='mode'
    finish(restored,mpd)
    assert mpd.song['file'].endswith('/1.mp3') and mpd.elapsed==67
    restored.set_mode(False)
    mpd.state='stop'
    stopped=Player(db,mpd,n)
    stopped.sync()
    assert stopped.state()['announcement_kind']=='mode' and mpd.state=='stop'
    stopped.play()
    assert mpd.state=='play' and mpd.song['file'].endswith('/1.mp3')


def test_external_source_change_cancels_mode_return(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=71
    p.set_mode(True)
    mpd.start('http://example.test/2.mp3',12)
    p.sync()
    assert not p.saved.get('intro') and p.saved['episode_id']==2
    assert p.episode(1)['position']==71


def test_delete_current_episode_cancels_mode_return(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    p.set_mode(True)
    p.delete_episodes([1])
    p.sync()
    assert not p.saved.get('intro') and mpd.state=='stop'
    assert p.state()['current'] is None


def test_seek_and_timer_changes_during_mode_apply_to_restored_episode(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    p.set_mode(True)
    assert c.post('/api/v1/seek',json={'offset_seconds':35}).status_code==200
    assert p.state()['elapsed']==35 and mpd.elapsed==0
    p.timer(1800)
    assert p.saved['deadline'] is None
    finish(p,mpd)
    assert mpd.elapsed==35 and p.remaining()==pytest.approx(1800,abs=1)


def test_next_during_mode_advances_and_can_reset_default_timer(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    p.timer(0)
    p.enqueue(2)
    p.set_mode(True)
    r=c.post('/api/v1/playback/next',json={'timer':'default'})
    assert r.status_code==200
    assert r.json()['current']['id']==2 and r.json()['announcement_kind']=='title'
    finish(p,mpd)
    assert mpd.song['file'].endswith('/2.mp3')
    assert p.remaining()==pytest.approx(900,abs=1)


def test_mode_audio_generation_failure_does_not_change_playback(mode_rig):
    c,p,_,mpd,n=mode_rig
    p.start_episode(1,announce=False)
    p.pause()
    n.title_audio.side_effect=OSError('Node-RED unavailable')
    response=c.post('/api/v1/mode/toggle')
    assert response.status_code==200 and response.json()['favorites_only']
    assert not p.saved.get('intro') and mpd.state=='pause'
    assert mpd.song['file'].endswith('/1.mp3')


def test_mode_mpd_outage_preserves_return_context(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=93
    p.set_mode(True)
    mpd.unavailable=True
    p.sync()
    assert p.status['state']=='error' and p.saved['intro']['resume']
    mpd.unavailable=False
    finish(p,mpd)
    assert mpd.state=='play' and mpd.elapsed==93
    assert mpd.song['file'].endswith('/1.mp3')


def test_mode_resumes_paused_title_without_starting_episode(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1)
    mpd.elapsed=.8
    p.pause()
    p.set_mode(True)
    finish(p,mpd)
    assert p.state()['announcement_kind']=='title' and mpd.state=='pause'
    assert mpd.song['file']==TITLE and mpd.elapsed==.8
    assert p.episode(1)['last_started'] is None


def test_mode_pause_read_failure_still_restores_original_playback(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=81
    snapshot=mpd.snapshot
    failed=[False]
    def flaky_snapshot():
        if mpd.state=='pause' and not failed[0]:
            failed[0]=True
            raise OSError('connection lost after pause')
        return snapshot()
    mpd.snapshot=flaky_snapshot
    p.set_mode(True)
    assert failed[0]
    assert p.mode and not p.saved.get('intro')
    assert mpd.state=='play' and mpd.elapsed==81
    assert mpd.song['file'].endswith('/1.mp3')


def test_failed_read_after_title_restore_does_not_drop_pending_episode(mode_rig):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1)
    mpd.elapsed=1
    p.set_mode(True)
    snapshot=mpd.snapshot
    failed=[False]
    def flaky_snapshot():
        if mpd.song.get('file')==TITLE and not failed[0]:
            failed[0]=True
            raise OSError('connection lost after restoring title')
        return snapshot()
    mpd.snapshot=flaky_snapshot
    finish(p,mpd)
    assert p.saved['intro']['kind']=='mode' and p.saved['intro']['restoring']
    p.sync()
    assert p.state()['announcement_kind']=='title' and mpd.elapsed==1
    finish(p,mpd)
    assert p.saved['episode_id']==1 and mpd.song['file'].endswith('/1.mp3')


@pytest.mark.parametrize('wanted', ['play', 'pause'])
@pytest.mark.parametrize('empty_song', [False, True])
def test_buffered_mode_return_is_pending_without_error_or_repeated_start(mode_rig, wanted, empty_song):
    c,p,_,mpd,_=mode_rig
    now=[1000.]
    p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    mpd.elapsed=81
    if wanted=='pause':p.pause()
    p.set_mode(True)
    remaining=p.remaining()
    start=mpd.start
    target=[]
    def buffered_start(url, position=0, **kwargs):
        id_=start(url,position,**kwargs)
        target.append(dict(mpd.song))
        mpd.state='stop'
        if empty_song:mpd.song={}
        return id_
    mpd.start=buffered_start
    finish(p,mpd)
    starts=len(mpd.calls)
    for _ in range(3):
        now[0]+=1
        p.sync()
        response=c.get('/api/v1/state')
        assert response.status_code==200 and not response.json()['error']
        assert response.json()['announcement_kind']=='mode'
        assert p.remaining()==remaining
    assert len(mpd.calls)==starts
    mpd.song=target[0]
    mpd.state=wanted
    p.sync()
    assert p.state()['phase']=='episode' and not p.state()['error']
    assert mpd.state==wanted and mpd.elapsed==81
    assert p.remaining()==remaining


def test_lost_read_after_mode_return_does_not_restart_the_podcast(mode_rig):
    _,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=123
    p.set_mode(True)
    snapshot=mpd.snapshot
    def read_failure():
        if mpd.song.get('file','').endswith('/1.mp3'):
            mpd.snapshot=snapshot
            raise OSError('read lost after accepted restore')
        return snapshot()
    mpd.snapshot=read_failure
    finish(p,mpd)
    count=len(mpd.calls)
    p.sync()
    assert len(mpd.calls)==count
    assert p.state()['phase']=='episode' and mpd.elapsed==123


@pytest.mark.parametrize('action', ['next', 'episode'])
def test_manual_change_during_mode_does_not_briefly_restart_old_episode(mode_rig, action):
    c,p,_,mpd,_=mode_rig
    p.start_episode(1,announce=False)
    mpd.elapsed=81
    p.enqueue(2)
    p.set_mode(True)
    mpd.calls.clear()
    if action=='next':response=c.post('/api/v1/playback/next')
    else:response=c.post('/api/v1/episodes/play',json={'episode_id':2})
    assert response.status_code==200
    assert not any(call[0]=='start' and call[1].endswith('/1.mp3') for call in mpd.calls)
    finish(p,mpd)
    assert p.saved['episode_id']==2
