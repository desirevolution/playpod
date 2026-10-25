from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.config import Settings
from app.integrations import Notifications
from app.player import Player

AUDIO='http://ha.test:8123/api/tts_proxy/title.wav'


@pytest.fixture
def announcement(rig):
    c,p,db,mpd,notifications=rig
    notifications.title_audio=Mock(return_value=AUDIO)
    notifications.settings=SimpleNamespace(tts_playback_timeout_seconds=120)
    original=mpd.start
    def start(url,position=0,**kwargs):
        mpd.duration=3 if url==AUDIO else 1200
        return original(url,position,**kwargs)
    mpd.start=start
    return rig


def end_intro(player,mpd):
    mpd.state='stop'
    mpd.elapsed=0
    player.sync()


def test_intro_then_episode_no_early_progress_timer_or_queue_removal(announcement):
    c,p,db,mpd,n=announcement
    db.execute('UPDATE episodes SET position=42,bookmarked=1 WHERE id=1')
    p.enqueue(1)
    p.start_episode(1)
    assert mpd.song['file']==AUDIO
    s=p.state()
    assert s['phase']=='announcement' and s['current']['id']==1
    assert s['elapsed']==42 and s['duration']==1200
    assert not s['timer']['run_active'] and p.saved['deadline'] is None
    assert p.episode(1)['position']==42 and p.episode(1)['last_started'] is None
    mpd.elapsed=2
    p.sync()
    p._checkpoint()
    assert p.episode(1)['position']==42 and p.episode(1)['duration']==1200
    assert [e['id'] for e in p.queue()]==[1]
    end_intro(p,mpd)
    assert p.state()['phase']=='episode'
    assert mpd.song['file']=='http://example.test/1.mp3'
    assert mpd.elapsed==42
    assert p.state()['timer']['run_active']
    assert not p.queue()
    assert p.episode(1)['bookmarked']==1
    assert n.title_audio.call_count==1


def test_pause_and_resume_intro_remain_responsive(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    p.pause()
    assert mpd.state=='pause' and p.state()['phase']=='announcement'
    assert not p.saved['run_active']
    p.play()
    assert mpd.state=='play' and mpd.song['file']==AUDIO
    end_intro(p,mpd)
    assert p.state()['phase']=='episode'
    assert n.title_audio.call_count==1


def test_next_skips_intro_not_target_episode(announcement):
    c,p,db,mpd,n=announcement
    p.enqueue(1)
    p.start_episode(1)
    p.next()
    assert p.saved['episode_id']==1
    assert p.state()['phase']=='episode'
    assert mpd.song['file']=='http://example.test/1.mp3'
    assert n.title_audio.call_count==1


def test_relative_seek_changes_target_not_intro_audio(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    assert c.post('/api/v1/seek',json={'offset_seconds':30}).status_code==200
    assert p.state()['elapsed']==30
    assert mpd.elapsed==0 and mpd.song['file']==AUDIO
    assert c.post('/api/v1/seek',json={'offset_seconds':-30}).status_code==200
    assert p.state()['elapsed']==0
    p.seek(50)
    end_intro(p,mpd)
    assert mpd.elapsed==50


def test_intro_failure_falls_back_without_duplicate_announcement(announcement):
    c,p,db,mpd,n=announcement
    mpd.bad_urls.add(AUDIO)
    p.start_episode(1)
    assert p.saved['episode_id']==1 and p.state()['phase']=='episode'
    assert n.title_audio.call_count==1


def test_async_mpd_intro_error_falls_back(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    mpd.error='decoder error'
    p.sync()
    assert p.saved['episode_id']==1 and mpd.song['file'].endswith('/1.mp3')
    assert not p.queue()


def test_playback_timeout_falls_back_but_pauses_suspend_timeout(announcement):
    c,p,db,mpd,n=announcement
    clock=[1000.]
    p.clock=lambda:clock[0]
    n.settings.tts_playback_timeout_seconds=5
    p.start_episode(1)
    clock[0]=1002
    p.pause()
    clock[0]=2000
    p.sync()
    assert p.state()['phase']=='announcement'
    p.play()
    clock[0]=2004
    p.sync()
    assert p.state()['phase']=='episode'


def test_existing_timer_expires_in_intro_then_resume_starts_new_run(announcement):
    c,p,db,mpd,n=announcement
    clock=[1000.]
    p.clock=lambda:clock[0]
    p.start_episode(1)
    p.next()  # skip intro, start first actual episode
    p.saved['deadline']=1002
    p.enqueue(2)
    p.start_episode(2)
    clock[0]=1003
    p.sync()
    assert p.state()['phase']=='announcement' and p.status['state']=='pause'
    assert not p.saved['run_active'] and p.remaining()==0
    assert p.episode(2)['last_started'] is None
    assert [e['id'] for e in p.queue()]==[2]
    p.play()
    end_intro(p,mpd)
    assert p.saved['episode_id']==2 and p.remaining()==900


def test_timer_preset_during_first_intro_applies_to_episode(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    p.timer(1800)
    assert p.saved['deadline'] is None
    end_intro(p,mpd)
    assert p.saved['timer_seconds']==1800
    assert 1799 <= p.remaining() <= 1800


def test_restart_during_intro_recovers_without_progress_corruption(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    mpd.elapsed=2
    p.sync()
    restored=Player(db,mpd,n,media=p.media)
    restored.sync()
    assert restored.state()['phase']=='announcement'
    assert restored.episode(1)['last_started'] is None
    end_intro(restored,mpd)
    assert restored.saved['episode_id']==1
    assert n.title_audio.call_count==1


def test_restart_with_stopped_intro_does_not_autoplay(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    mpd.state='stop'
    restored=Player(db,mpd,n,media=p.media)
    restored.sync()
    assert mpd.state=='stop'
    assert restored.state()['phase']=='announcement'
    restored.play()
    assert restored.state()['phase']=='episode' and mpd.state=='play'


def test_external_source_change_cancels_pending_intro(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    mpd.start('http://example.test/2.mp3')
    p.sync()
    assert p.state()['phase']=='episode' and p.saved['episode_id']==2
    assert p.episode(1)['last_started'] is None


def test_deleted_target_cancels_intro(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    p.delete_episodes([1])
    assert not p.saved.get('intro') and mpd.state=='stop'
    p.sync()
    assert mpd.state=='stop'


def test_json_audio_endpoint_preserves_plain_text_contract(monkeypatch):
    response=Mock()
    response.json.return_value={'url':AUDIO}
    post=Mock(return_value=response)
    monkeypatch.setattr('app.integrations.requests.post',post)
    n=Notifications(Settings(tts_audio_url='http://node-red.test/tts-file'))
    assert n.title_audio('Grüße')==AUDIO
    assert post.call_args.args==('http://node-red.test/tts-file',)
    assert post.call_args.kwargs['data']=='Grüße'.encode()
    assert post.call_args.kwargs['headers']=={'Content-Type':'text/plain;charset=utf-8'}


@pytest.mark.parametrize('data',[{}, {'url':'file:///etc/passwd'}, [], {'url':None}])
def test_bad_json_audio_result_is_nonfatal(monkeypatch,data):
    response=Mock()
    response.json.return_value=data
    monkeypatch.setattr('app.integrations.requests.post',Mock(return_value=response))
    n=Notifications(Settings(tts_audio_url='http://node-red.test/tts-file'))
    assert n.title_audio('Episode') is None


def test_old_episode_progress_and_existing_deadline_survive_intro(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    p.next()
    mpd.elapsed=77
    p.sync()
    deadline=p.saved['deadline']
    p.start_episode(2)
    mpd.elapsed=1
    p.sync()
    p._checkpoint()
    assert p.episode(1)['position']==77
    assert p.episode(1)['duration']==1200
    assert p.episode(2)['last_started'] is None
    end_intro(p,mpd)
    assert p.saved['deadline']==deadline
    assert p.saved['episode_id']==2


def test_no_current_song_at_intro_eof_still_starts_target(announcement):
    c,p,db,mpd,n=announcement
    p.start_episode(1)
    mpd.song={}
    end_intro(p,mpd)
    assert p.saved['episode_id']==1 and p.state()['phase']=='episode'


def test_remote_toggle_default_timer_waits_for_first_episode(announcement):
    c,p,_,mpd,_=announcement
    now=[1000.]
    p.clock=lambda:now[0]
    p.timer(0)
    s=c.post('/api/v1/playback/toggle',json={'timer':'default'}).json()
    assert s['phase']=='announcement' and s['timer']['enabled']
    assert s['timer']['remaining']==900 and not s['timer']['run_active']
    now[0]+=2
    s=c.post('/api/v1/playback/toggle',json={'timer':'default'}).json()
    assert s['state']=='pause' and s['timer']['remaining']==900
    now[0]+=100
    s=c.post('/api/v1/playback/toggle',json={'timer':'default'}).json()
    assert s['state']=='play' and s['timer']['remaining']==900
    now[0]+=1
    end_intro(p,mpd)
    assert p.state()['timer']['run_active']
    assert p.remaining()==900
