import sqlite3
import time

from app.activity import record, RETENTION_SECONDS
from app.db import Database
from test_feeds import FakeResponse, RSS


def events(client, **params):
    return client.get('/api/v1/activity', params=params).json()


def test_feed_initial_summary_then_only_new_insertions(rig, monkeypatch):
    c, _, db, _, _ = rig
    db.execute("INSERT INTO feeds(id,url,title) VALUES(3,'http://new.test/rss','New')")
    response = FakeResponse()
    monkeypatch.setattr('app.feeds.requests.get', lambda *a, **kw: response)
    jobs = c.app.state.jobs
    jobs.refresh(3, 'http://new.test/rss')
    first = events(c)['items']
    assert len(first) == 1 and first[0]['kind'] == 'feed_added'
    assert first[0]['count'] == 1 and first[0]['podcast'] == 'Feed name'
    jobs.refresh(3, 'http://new.test/rss')
    assert len(events(c)['items']) == 1
    response.content = RSS.replace(b'<guid>abc</guid>', b'<guid>new</guid>').replace(b'audio.mp3', b'new.mp3').replace(b'First', b'New episode')
    jobs.refresh(3, 'http://new.test/rss')
    new = events(c)['items'][0]
    assert new['kind'] == 'episode_added' and new['title'] == 'New episode'
    assert new['episode_id'] is not None
    # A newly introduced GUID for the same enclosure updates metadata without an event.
    response.content = response.content.replace(b'<guid>new</guid>', b'<guid>changed</guid>')
    jobs.refresh(3, 'http://new.test/rss')
    assert len(events(c)['items']) == 2


def test_existing_catalog_is_not_backfilled_as_initial_import(rig, monkeypatch):
    c, _, _, _, _ = rig
    monkeypatch.setattr('app.feeds.requests.get', lambda *a, **kw: FakeResponse())
    c.app.state.jobs.refresh(1, 'http://example.test/rss')
    assert [e['kind'] for e in events(c)['items']] == ['episode_added']


def test_mpd_end_replay_and_pause_skip(rig):
    c, p, db, mpd, _ = rig
    p.saved.update(timer_seconds=0, remaining=0, when_queue_empty='stop')
    p.start_episode(1, announce=False)
    p.command('pause')
    p.command('play')
    assert not events(c)['items']
    for _ in range(2):
        mpd.elapsed = 1199
        p.sync()
        mpd.state = 'stop'
        mpd.elapsed = 0
        p.sync()
        p.sync()
        p.start_episode(1, announce=False)
    items = events(c, kind='completed')['items']
    assert len(items) == 2 and all(e['target'] == 'mpd' and e['episode_id'] == 1 for e in items)
    p.enqueue(2)
    p.command('next')
    assert len(events(c)['items']) == 2


def test_browser_run_id_deduplicates_retries_and_allows_replay(rig):
    c, _, _, mpd, _ = rig
    before = list(mpd.calls)
    body = {'episode_id': 1, 'position': 1200, 'duration': 1200, 'completed': True, 'playback_id': 'first'}
    for _ in range(3):
        assert c.put('/api/v1/browser/progress', json=body).status_code == 200
    assert len(events(c)['items']) == 1
    c.put('/api/v1/browser/progress', json={**body, 'playback_id': 'second'})
    assert len(events(c)['items']) == 2
    assert mpd.calls == before
    assert c.put('/api/v1/browser/progress', json={**body, 'playback_id': ''}).status_code == 422


def test_legacy_browser_completion_is_idempotent_until_new_start(rig):
    c = rig[0]
    body = {'episode_id': 1, 'position': 1200, 'completed': True}
    c.put('/api/v1/browser/progress', json=body)
    c.put('/api/v1/browser/progress', json=body)
    assert len(events(c)['items']) == 1
    c.put('/api/v1/browser/progress', json={'episode_id': 1, 'position': 0, 'started': True})
    c.put('/api/v1/browser/progress', json=body)
    assert len(events(c)['items']) == 2


def test_retention_deleted_snapshots_filters_cursor_and_unseen(rig):
    c, _, db, _, _ = rig
    with db.connect() as conn:
        record(conn, 'episode_added', episode_id=1, now=time.time()-RETENTION_SECONDS-1)
        record(conn, 'episode_added', episode_id=2)
        record(conn, 'completed', episode_id=3, target='browser')
    assert len(events(c)['items']) == 2
    status = c.get('/api/v1/activity/status').json()
    assert status['unseen'] == 2
    assert c.get('/api/v1/activity/status', params={'after': status['latest']}).json()['unseen'] == 0
    page = events(c, limit=1)
    assert page['next_cursor'] == page['items'][0]['id']
    older = events(c, before=page['next_cursor'], limit=1)
    assert older['next_cursor'] is None and older['items'][0]['kind'] == 'episode_added'
    assert len(events(c, kind='new')['items']) == 1
    db.execute('DELETE FROM feeds WHERE id=1')
    deleted = events(c)['items'][0]
    assert deleted['episode_id'] is None and deleted['feed_id'] is None
    assert deleted['title'] == 'Episode 3' and deleted['podcast'] == 'Podcast A'
    assert c.get('/api/v1/activity?kind=bad').status_code == 422
    assert c.get('/api/v1/activity?limit=0').status_code == 422
    assert c.get('/api/v1/activity/status?after=-1').status_code == 422


def test_episode_location_finds_older_page_and_null_dates(rig):
    c, _, db, _, _ = rig
    for i in range(6, 125):
        db.execute('INSERT INTO episodes(id,feed_id,source_key,title,url,published) VALUES(?,1,?,?,?,?)',
                   (i, str(i), f'Episode {i}', f'http://e/{i}', 100 if i > 60 else None))
    for episode_id in (1, 40, 70, 124):
        location = c.get(f'/api/v1/episodes/{episode_id}/location').json()
        page = c.get('/api/v1/episodes', params={'feed_id': location['feed_id'], 'offset': location['offset']}).json()
        assert episode_id in [e['id'] for e in page['items']]
    assert c.get('/api/v1/episodes/999/location').status_code == 404


def test_v4_upgrade_backs_up_and_preserves_catalog_without_backfill(tmp_path):
    path = tmp_path/'old.sqlite3'
    db = Database(path)
    db.execute("INSERT INTO feeds(id,url,title) VALUES(1,'http://feed','Title')")
    db.execute("INSERT INTO episodes(id,feed_id,source_key,title,url,position) VALUES(1,1,'one','Episode','http://audio',123)")
    db.execute('DROP TABLE activity')
    db.execute('DELETE FROM schema_migrations WHERE version=5')
    db.execute('PRAGMA user_version=4')
    restored = Database(path)
    assert restored.one('PRAGMA user_version')['user_version'] == 5
    assert restored.one('SELECT position FROM episodes')['position'] == 123
    assert restored.rows('SELECT * FROM activity') == []
    with sqlite3.connect(str(path)+'.before-v5.sqlite3') as backup:
        assert backup.execute('PRAGMA user_version').fetchone()[0] == 4
        assert backup.execute('SELECT position FROM episodes').fetchone()[0] == 123
