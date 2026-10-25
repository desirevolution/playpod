import threading
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import Settings
from app.integrations import Notifications
from app.player import Player
from test_announcements import announcement, end_intro, AUDIO


def enqueue(c, p, text='Hallo', start=True):
    response = c.post('/api/v1/announcements', json={'text': text})
    assert response.status_code == 202, response.text
    data = response.json()
    assert data['state'] == 'queued' and data['queue_position'] >= 1
    if start:
        assert p.process_announcements()
    return data['id']


def status(c, id_):
    return c.get('/api/v1/announcements/' + id_).json()


@pytest.mark.parametrize('state', ['play', 'pause', 'stop', 'empty'])
def test_text_announcement_restores_source_state_position_and_queue(announcement, state):
    c,p,db,mpd,n = announcement
    if state != 'empty':
        p.start_episode(1, announce=False)
        mpd.elapsed = 123
        p.sync()
        if state == 'pause':
            p.pause()
        elif state == 'stop':
            mpd.call('stop')
            p.sync()
    p.enqueue(2)
    revision = p.revision
    before = p.episode(1)
    activity = c.get('/api/v1/activity').json()
    id_ = enqueue(c, p, '  Die Waschmaschine ist fertig.  ')
    data = c.get('/api/v1/state').json()
    assert data['announcement_kind'] == 'custom' and data['phase'] == 'announcement'
    assert data['announcement_text'] == 'Die Waschmaschine ist fertig.'
    assert data['timer']['suspended'] and mpd.song['file'] == AUDIO
    assert status(c, id_)['state'] == 'playing' and not p.mode
    p._checkpoint()
    end_intro(p, mpd)
    assert p.state()['phase'] == 'episode' and status(c, id_)['state'] == 'done'
    assert mpd.state == ('stop' if state in ('empty', 'stop') else state)
    if state in ('play', 'pause'):
        assert mpd.song['file'].endswith('/1.mp3') and mpd.elapsed == 123
    assert p.episode(1) == before
    assert [ep['id'] for ep in p.queue()] == [2] and p.revision == revision
    assert c.get('/api/v1/activity').json() == activity
    n.title_audio.assert_called_once_with('Die Waschmaschine ist fertig.')


def test_generation_leaves_playback_running_then_freezes_remaining_period(announcement):
    c,p,_,mpd,n = announcement
    now = [1000.]
    p.clock = lambda: now[0]
    p.start_episode(1, announce=False)
    def generate(text):
        assert mpd.state == 'play' and mpd.song['file'].endswith('/1.mp3')
        now[0] += 10
        mpd.elapsed = 55
        return AUDIO
    n.title_audio.side_effect = generate
    enqueue(c, p)
    assert p.remaining() == 890
    run = p.saved['activity_run']
    now[0] += 20
    p.sync()
    assert p.remaining() == 890 and p.state()['elapsed'] == 55
    end_intro(p, mpd)
    assert mpd.elapsed == 55 and p.remaining() == 890
    assert p.saved['activity_run'] == run
    now[0] += 5
    assert p.remaining() == 885


@pytest.mark.parametrize('failure', [None, OSError('TTS unavailable')])
def test_generation_failure_does_not_pause_and_is_inspectable(announcement, failure):
    c,p,_,mpd,n = announcement
    p.start_episode(1, announce=False)
    before = list(mpd.calls)
    if isinstance(failure, Exception):
        n.title_audio.side_effect = failure
    else:
        n.title_audio.return_value = failure
    id_ = enqueue(c, p)
    assert status(c, id_)['state'] == 'failed' and status(c, id_)['error']
    assert mpd.calls == before and mpd.state == 'play'
    assert not p.saved.get('intro') and not p.announcement_lock.locked()


def test_fifo_without_podcast_snippet_and_timer_stays_frozen_for_entire_batch(announcement):
    c,p,_,mpd,n = announcement
    now = [1000.]
    p.clock = lambda: now[0]
    p.start_episode(1, announce=False)
    mpd.elapsed = 84
    now[0] += 10
    first = enqueue(c, p, 'Erste')
    second = enqueue(c, p, 'Zweite', start=False)
    third = enqueue(c, p, 'Dritte', start=False)
    assert [item['id'] for item in c.get('/api/v1/announcements').json()] == [first, second, third]
    assert status(c, second)['queue_position'] == 1 and status(c, third)['queue_position'] == 2
    mpd.calls.clear()
    for id_ in (second, third):
        end_intro(p, mpd)
        assert p.saved['intro']['waiting_next'] and p.remaining() == 890
        assert mpd.state == 'stop'
        now[0] += 5
        assert p.process_announcements()
        assert status(c, id_)['state'] == 'playing'
        assert p.remaining() == 890
        assert not any(call[0]=='start' and call[1].endswith('/1.mp3') for call in mpd.calls)
    end_intro(p, mpd)
    assert mpd.state == 'play' and mpd.elapsed == 84 and p.remaining() == 890
    assert all(status(c, id_)['state']=='done' for id_ in (first,second,third))
    assert [call.args[0] for call in n.title_audio.call_args_list] == ['Erste','Zweite','Dritte']


def test_fire_and_forget_generation_does_not_block_enqueue_or_controls(announcement):
    c,p,_,mpd,n = announcement
    p.start_episode(1, announce=False)
    entered, release = threading.Event(), threading.Event()
    def generate(text):
        entered.set()
        assert release.wait(3)
        return AUDIO
    n.title_audio.side_effect = generate
    id_ = enqueue(c, p, start=False)
    worker = threading.Thread(target=p.process_announcements)
    worker.start()
    try:
        assert entered.wait(2)
        second = enqueue(c, p, 'Zweite', start=False)
        assert status(c, id_)['state'] == 'generating'
        assert status(c, second)['state'] == 'queued'
        assert mpd.state == 'play'
        assert c.post('/api/v1/playback/pause').status_code == 200
    finally:
        release.set()
        worker.join(timeout=4)
    assert not worker.is_alive() and status(c, id_)['state'] == 'playing'
    end_intro(p, mpd)
    p.process_announcements()
    end_intro(p, mpd)
    assert mpd.state == 'pause' and mpd.song['file'].endswith('/1.mp3')


def test_start_failure_restores_previous_paused_position_and_records_failure(announcement):
    c,p,_,mpd,_ = announcement
    p.start_episode(1, announce=False)
    mpd.elapsed = 84
    p.pause()
    mpd.bad_urls.add(AUDIO)
    id_ = enqueue(c, p)
    assert status(c, id_)['state'] == 'failed'
    assert not p.saved.get('intro') and mpd.state == 'pause'
    assert mpd.elapsed == 84 and mpd.song['file'].endswith('/1.mp3')


@pytest.mark.parametrize('failure', ['decode', 'timeout'])
def test_audio_error_or_timeout_restores_playback(announcement, failure):
    c,p,_,mpd,_ = announcement
    now = [1000.]
    p.clock = lambda: now[0]
    p.start_episode(1, announce=False)
    mpd.elapsed = 61
    id_ = enqueue(c, p)
    if failure == 'decode':
        mpd.error = 'invalid audio'
    else:
        now[0] += 121
    p.sync()
    assert status(c, id_)['state'] == 'failed'
    assert not p.saved.get('intro') and mpd.state == 'play'
    assert mpd.elapsed == 61 and mpd.song['file'].endswith('/1.mp3')


def test_last_queued_generation_failure_still_resumes_podcast(announcement):
    c,p,_,mpd,n = announcement
    p.start_episode(1, announce=False)
    first = enqueue(c, p)
    last = enqueue(c, p, 'Zweite', start=False)
    end_intro(p, mpd)
    n.title_audio.return_value = None
    p.process_announcements()
    assert status(c, first)['state'] == 'done'
    assert status(c, last)['state'] == 'failed'
    assert not p.saved.get('intro') and mpd.state == 'play'
    assert mpd.song['file'].endswith('/1.mp3')


def test_failed_middle_job_is_skipped_without_resuming_between_messages(announcement):
    c,p,_,mpd,n = announcement
    p.start_episode(1, announce=False)
    enqueue(c, p, 'Erste')
    bad = enqueue(c, p, 'Kaputt', start=False)
    last = enqueue(c, p, 'Dritte', start=False)
    end_intro(p, mpd)
    mpd.calls.clear()
    n.title_audio.side_effect = [None, AUDIO]
    assert p.process_announcements()
    assert status(c, bad)['state'] == 'failed'
    assert p.process_announcements()
    assert status(c, last)['state'] == 'playing'
    assert not any(call[0]=='start' and call[1].endswith('/1.mp3') for call in mpd.calls)
    end_intro(p, mpd)
    assert mpd.state == 'play' and mpd.song['file'].endswith('/1.mp3')


def test_restart_after_announcement_eof_advances_pending_queue(announcement):
    c,p,db,mpd,n = announcement
    p.start_episode(1, announce=False)
    first = enqueue(c, p)
    second = enqueue(c, p, 'Zweite', start=False)
    mpd.state = 'stop'
    restored = Player(db, mpd, n)
    restored.sync()
    assert restored.announcement_status(first)['state'] == 'done'
    assert restored.process_announcements()
    assert restored.announcement_status(second)['state'] == 'playing'
    end_intro(restored, mpd)
    assert mpd.state == 'play' and mpd.song['file'].endswith('/1.mp3')


def test_queue_and_return_context_survive_restart_and_manual_change_cancels_batch(announcement):
    c,p,db,mpd,n = announcement
    p.start_episode(1, announce=False)
    mpd.elapsed = 64
    first = enqueue(c, p)
    second = enqueue(c, p, 'Zweite', start=False)
    restored = Player(db, mpd, n)
    restored.sync()
    assert restored.state()['announcement_kind'] == 'custom'
    end_intro(restored, mpd)
    restored.process_announcements()
    assert restored.announcement_status(first)['state'] == 'done'
    assert restored.announcement_status(second)['state'] == 'playing'
    third = restored.announce('Dritte')['id']
    mpd.calls.clear()
    restored.start_episode(2, announce=False)
    assert not any(call[0]=='start' and call[1].endswith('/1.mp3') for call in mpd.calls)
    assert restored.saved['episode_id'] == 2 and not restored.saved.get('intro')
    assert restored.announcement_status(second)['state'] == 'cancelled'
    assert restored.announcement_status(third)['state'] == 'cancelled'


def test_queued_text_waits_for_existing_title_announcement(announcement):
    c,p,_,mpd,n = announcement
    p.start_episode(1)
    id_ = enqueue(c, p, start=False)
    assert not p.process_announcements() and n.title_audio.call_count == 1
    end_intro(p, mpd)
    assert p.process_announcements() and status(c, id_)['state'] == 'playing'


def test_favorite_mode_speech_joins_batch_without_interrupting_or_api_error(announcement):
    c,p,_,mpd,n = announcement
    p.start_episode(1, announce=False)
    enqueue(c, p, 'Hallo')
    calls = list(mpd.calls)
    response = c.post('/api/v1/mode/toggle')
    assert response.status_code == 200 and response.json()['favorites_only']
    assert mpd.calls == calls and p.state()['announcement_text'] == 'Hallo'
    end_intro(p, mpd)
    assert p.process_announcements()
    assert p.state()['announcement_text'] == 'Favoriten'
    end_intro(p, mpd)
    assert mpd.song['file'].endswith('/1.mp3') and mpd.state == 'play'
    assert [call.args[0] for call in n.title_audio.call_args_list] == ['Hallo', 'Favoriten']


@pytest.mark.parametrize('body', [{}, {'text':''}, {'text':'   '}, {'text':'x'*2001}, {'text':123}, {'text':'Hallo','url':'http://audio'}])
def test_text_validation(announcement, body):
    c,p,_,mpd,n = announcement
    assert c.post('/api/v1/announcements', json=body).status_code == 422
    n.title_audio.assert_not_called()
    assert not p.announcements and not mpd.calls


def test_missing_mpd_has_explicit_error(tmp_path):
    app = create_app(Settings(database=str(tmp_path/'no-mpd.sqlite3')), background=False)
    with TestClient(app) as c:
        response = c.post('/api/v1/announcements', json={'text':'Hallo'})
        assert response.status_code == 503 and response.json()['error']['code'] == 'mpd_not_configured'


def test_existing_node_red_tts_contract_is_reused(announcement, monkeypatch):
    c,p,_,mpd,_ = announcement
    p.notifications = Notifications(Settings(tts_audio_url='http://node-red.test/tts'))
    post = Mock(return_value=Mock(json=lambda: {'url':AUDIO}))
    monkeypatch.setattr('app.integrations.requests.post', post)
    enqueue(c, p, 'Tür geöffnet.')
    assert post.call_args.args == ('http://node-red.test/tts',)
    assert post.call_args.kwargs['data'] == 'Tür geöffnet.'.encode('utf-8')
    assert post.call_args.kwargs['headers']['Content-Type'] == 'text/plain;charset=utf-8'


def test_missing_tts_and_queue_limit_and_unknown_status(announcement):
    c,p,_,mpd,_ = announcement
    assert c.get('/api/v1/announcements/unknown').status_code == 404
    for i in range(50):
        enqueue(c, p, str(i), start=False)
    assert c.post('/api/v1/announcements', json={'text':'voll'}).status_code == 429
    assert not mpd.calls
    p.notifications = Notifications(Settings())
    response = c.post('/api/v1/announcements', json={'text':'Hallo'})
    assert response.status_code == 503 and response.json()['error']['code'] == 'tts_not_configured'


def test_worker_processes_accepted_request_without_further_api_call(announcement):
    c,p,_,mpd,n = announcement
    started = threading.Event()
    original = mpd.start
    def start(*args, **kwargs):
        result = original(*args, **kwargs)
        started.set()
        return result
    mpd.start = start
    p.start_announcement_worker()
    enqueue(c, p, start=False)
    assert started.wait(2)
    with p.lock:
        assert p.state()['announcement_kind'] == 'custom'
        assert mpd.state == 'play' and mpd.song['file'] == AUDIO
