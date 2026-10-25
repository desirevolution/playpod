import pytest
from app.player import Player, PlayerError


def test_next_uses_queue_then_random(rig):
    client, p, db, mpd, _ = rig
    p.start_episode(1)
    p.enqueue(3)
    p.enqueue(2)
    assert client.post('/api/v1/playback/next').status_code == 200
    assert p.saved['episode_id'] == 3
    assert [e['id'] for e in p.queue()] == [2]
    p.next()
    assert p.saved['episode_id'] == 2
    p.next()
    assert p.saved['episode_id'] != 2


def test_queue_edit_dedup_and_conflict(rig):
    _, p, _, _, _ = rig
    assert p.enqueue(2)
    assert not p.enqueue(2)
    p.enqueue(3)
    revision = p.revision
    p.reorder([3, 2], revision)
    assert [e['id'] for e in p.queue()] == [3, 2]
    with pytest.raises(PlayerError):
        p.reorder([2, 3], revision)
    with pytest.raises(PlayerError):
        p.reorder([2, 2], p.revision)


def test_natural_end_without_queue_uses_random_and_keeps_timer(rig):
    _, p, db, mpd, _ = rig
    p.start_episode(1)
    deadline = p.saved['deadline']
    mpd.elapsed = 1199
    p.sync()
    mpd.state = 'stop'
    mpd.elapsed = 0  # MPD can reset elapsed on EOF.
    p.sync()
    assert p.status['state'] == 'play'
    assert p.saved['episode_id'] != 1
    assert p.saved['deadline'] == deadline
    ep = p.episode(1)
    assert ep['completed'] == 1
    assert ep['position'] == 1200
    assert p.saved['run_active']


def test_natural_end_continues_queue_without_resetting_timer(rig):
    _, p, db, mpd, _ = rig
    clock = [1000.0]
    p.clock = lambda: clock[0]
    p.start_episode(1)
    p.enqueue(2)
    deadline = p.saved['deadline']
    mpd.elapsed = 1199
    p.sync()
    mpd.state = 'stop'
    mpd.elapsed = 0
    p.sync()
    assert p.saved['episode_id'] == 2
    assert p.saved['deadline'] == deadline
    assert p.episode(1)['completed'] == 1
    assert p.episode(1)['position'] == 1200


def test_external_stop_early_does_not_mark_completed(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    mpd.elapsed = 15
    p.sync()
    mpd.state = 'stop'
    p.sync()
    assert not p.episode(1)['completed']


def test_failed_start_not_marked_started(rig):
    _, p, _, mpd, _ = rig
    mpd.bad_urls.add('http://example.test/2.mp3')
    with pytest.raises(PlayerError):
        p.start_episode(2)
    assert p.episode(2)['last_started'] is None


def test_bad_queue_item_retained_and_skipped(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    p.enqueue(2)
    p.enqueue(3)
    mpd.bad_urls.add('http://example.test/2.mp3')
    p.next()
    assert p.saved['episode_id'] == 3
    assert p.queue()[0]['id'] == 2
    assert p.queue()[0]['queue_error']
    assert p.episode(2)['last_started'] is None


def test_timer_pause_resume_and_expiry(rig):
    _, p, _, mpd, _ = rig
    clock = [1000.0]
    p.clock = lambda: clock[0]
    p.start_episode(1)
    p.timer(1800)
    clock[0] += 60
    p.pause()
    assert p.remaining() == 1740
    clock[0] += 100
    p.play()
    assert p.remaining() == 1800
    p.timer(extend=300)
    assert p.remaining() == 2100
    clock[0] += 2101
    p.sync()
    assert mpd.state == 'pause'
    assert not p.saved['run_active']
    p.play()
    assert p.remaining() == 1800


def test_expired_timer_retried_after_mpd_outage(rig):
    _, p, _, mpd, _ = rig
    clock = [1000.0]
    p.clock = lambda: clock[0]
    p.start_episode(1)
    mpd.unavailable = True
    clock[0] += 901
    p.sync()
    assert p.status['state'] == 'error'
    assert p.saved['deadline'] is not None
    mpd.unavailable = False
    p.sync()
    assert mpd.state == 'pause'
    assert not p.saved['run_active']


def test_persistent_queue_mode_timer_and_resume(rig):
    _, p, db, mpd, n = rig
    p.start_episode(1)
    p.seek(345)
    p.enqueue(2)
    p.set_mode(True)
    p.timer(1800)
    p.persist()
    restored = Player(db, mpd, n)
    restored.sync()
    assert restored.queue()[0]['id'] == 2
    assert restored.mode
    assert restored.saved['timer_seconds'] == 1800
    assert restored.state()['current']['id'] == 1
    assert restored.status['elapsed'] == 345


def test_undo_restores_previous_position_and_queue(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    p.seek(200)
    p.enqueue(2)
    p.enqueue(3)
    p.next()
    p.undo_next()
    assert p.saved['episode_id'] == 1
    assert mpd.elapsed == 200
    assert [e['id'] for e in p.queue()] == [2, 3]
    p.next()
    p.enqueue(4)
    with pytest.raises(PlayerError):
        p.undo_next()


def test_bookmark_survives_play_and_delete_cascades(rig):
    client, p, db, mpd, _ = rig
    assert client.put('/api/v1/episodes/1/bookmark', json={'value': True}).status_code == 200
    p.start_episode(1)
    p.enqueue(2)
    assert p.episode(1)['bookmarked']
    assert client.delete('/api/v1/feeds/1').status_code == 200
    assert mpd.state == 'stop'
    assert not p.queue()
    assert not db.rows('SELECT * FROM episodes WHERE feed_id=1')
    assert p.saved['episode_id'] is None


def test_same_guid_different_feeds_allowed(rig):
    _, _, db, _, _ = rig
    for feed_id in [1, 2]:
        db.execute("INSERT INTO episodes(feed_id,source_key,title,url) VALUES(?,'guid:same','Title','http://example.test/same')", (feed_id,))
    assert len(db.rows("SELECT * FROM episodes WHERE source_key='guid:same'")) == 2


def test_external_song_switch_does_not_corrupt_episode_progress(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    p.seek(200)
    mpd.song = {'file':'http://example.test/2.mp3','id':'99'}
    mpd.elapsed = 20
    p.sync()
    assert p.saved['episode_id'] == 2
    assert p.episode(1)['position'] == pytest.approx(200, abs=.1)


def test_restart_with_empty_mpd_keeps_saved_progress(rig):
    _, p, db, mpd, n = rig
    p.start_episode(1)
    p.seek(500)
    mpd.song = {}
    mpd.state = 'stop'
    restored = Player(db, mpd, n)
    restored.sync()
    assert restored.episode(1)['position'] == 500


def test_timer_expiry_at_eof_does_not_start_next(rig):
    _, p, db, mpd, _ = rig
    clock = [1000.0]
    p.clock = lambda: clock[0]
    p.start_episode(1)
    p.enqueue(2)
    mpd.elapsed = 1199
    p.sync()
    mpd.state = 'stop'
    clock[0] += 901
    p.sync()
    assert p.saved['episode_id'] == 1
    assert [e['id'] for e in p.queue()] == [2]
    assert not p.saved['run_active']


def test_timer_can_be_chosen_before_first_play(rig):
    _, p, _, _, _ = rig
    p.timer(1800)
    p.play()
    assert p.saved['timer_seconds'] == 1800
    assert 1799 <= p.remaining() <= 1800


def test_mpd_outage_does_not_poison_queue(rig):
    _, p, _, mpd, _ = rig
    p.enqueue(2)
    p.enqueue(3)
    mpd.unavailable = True
    with pytest.raises(PlayerError, match='MPD'):
        p.next()
    assert [e['id'] for e in p.queue()] == [2, 3]
    assert all(not e['queue_error'] for e in p.queue())


def test_parallel_enqueue_and_backup(rig, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import sqlite3
    _, p, db, _, _ = rig
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(p.enqueue, [1, 2, 3, 4, 5] * 4))
    assert len(p.queue()) == 5
    backup = tmp_path / 'backup.sqlite3'
    db.backup(backup)
    with sqlite3.connect(backup) as restored:
        assert restored.execute('SELECT count(*) FROM queue').fetchone()[0] == 5


def test_natural_end_with_timer_disabled_continues(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    p.timer(0)
    mpd.elapsed = 1199
    p.sync()
    mpd.state = 'stop'
    p.sync()
    assert p.saved['episode_id'] != 1
    assert p.saved['timer_seconds'] == 0
    assert p.saved['deadline'] is None
    assert p.status['state'] == 'play'


def test_natural_end_with_no_playable_source_stops(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    mpd.elapsed = 1199
    p.sync()
    mpd.bad_urls.update(f'http://example.test/{i}.mp3' for i in range(1,6))
    mpd.state = 'stop'
    p.sync()
    assert p.status['state'] == 'stop'
    assert not p.saved['run_active']


def test_natural_random_fallback_respects_favorites(rig):
    _, p, _, mpd, _ = rig
    p.start_episode(1)
    p.set_mode(True)
    mpd.elapsed = 1199
    p.sync()
    mpd.state = 'stop'
    p.sync()
    assert p.saved['episode_id'] in (2,3)
