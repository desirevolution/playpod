from copy import deepcopy
from uuid import uuid4
import pytest

from app.db import Database
from app.youtube import collection_url


def video(id_, **extra):
    return {'id': id_, 'title': 'Video ' + id_, 'url': 'https://www.youtube.com/watch?v=' + id_,
            'duration': 120, 'thumbnail': 'https://i.ytimg.com/' + id_ + '.jpg', **extra}


@pytest.fixture
def yt(rig, monkeypatch):
    c, p, db, mpd, _ = rig
    d, catalog, jobs = c.app.state.downloads, c.app.state.youtube, c.app.state.jobs
    d.ytdlp_enabled = True
    d.base_url = 'http://playpod.test'
    snapshot = {'title': 'Meine Playlist', 'thumbnail': 'https://example.test/cover.jpg', 'entries': [video('one'), video('two'), video('three')]}
    monkeypatch.setattr('app.ytdlp.catalog', lambda *args: deepcopy(snapshot))
    monkeypatch.setattr(jobs.executor, 'submit', lambda *args: None)
    def add(kind='yt_playlist', limit=None, key='PLtest'):
        url = 'https://www.youtube.com/playlist?list=' + key if kind == 'yt_playlist' else 'https://www.youtube.com/@test'
        response = c.post('/api/v1/youtube/collections', json={'url': url, 'kind': kind, 'limit': limit})
        assert response.status_code == 202, response.text
        # Test executes the accepted background job deterministically.
        jobs._run(response.json()['job_id'], 'refresh', response.json()['id'])
        return response.json()['id']
    return c, p, db, mpd, d, catalog, snapshot, add


def ready(db, d, id_):
    key = str(uuid4())
    (d.directory / (key + '.audio')).write_bytes(b'audio')
    db.execute("INSERT INTO downloads(episode_id,id,source_url,state,received,updated) VALUES(?,?,'https://example.test','ready',5,1) ON CONFLICT(episode_id) DO UPDATE SET id=excluded.id,state='ready',received=5", (id_, key))
    return d.directory / (key + '.audio')


def test_initial_limit_thumbnails_and_new_only_periodic_import(yt):
    c, p, db, _, d, catalog, snapshot, add = yt
    feed = add(limit=1)
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 1
    ep = db.one('SELECT * FROM episodes WHERE feed_id=?', (feed,))
    assert ep['cover'].endswith('one.jpg')
    assert c.get('/api/v1/feeds').json()[-1]['kind'] in ('rss', 'yt_playlist')
    assert not db.rows('SELECT * FROM downloads')
    catalog.refresh(feed)
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 1
    snapshot['entries'].insert(0, video('new'))
    catalog.refresh(feed)
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 2
    assert not db.rows('SELECT * FROM downloads')
    assert {e['id'] for e in p.db.rows("SELECT id FROM episodes WHERE feed_id=?", (feed,))}.isdisjoint({x['id'] for x in c.get('/api/v1/browser/candidates').json()})


def test_short_live_private_exclusion_and_duplicates_between_collections(yt):
    _, _, db, _, _, catalog, snapshot, add = yt
    snapshot['entries'] += [video('short', url='https://www.youtube.com/shorts/short'), video('live', live_status='is_live'), video('oldlive', live_status='was_live'), video('private', availability='private')]
    first, second = add(key='PL1'), add(key='PL2')
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id IN (?,?)', (first, second))['n'] == 6
    assert len(db.rows("SELECT id FROM episodes WHERE source_key='youtube:one'")) == 2
    catalog.refresh(first)
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (first,))['n'] == 3


def test_removed_entries_remain_only_while_copy_exists_and_failed_snapshot_never_prunes(yt, monkeypatch):
    c, _, db, _, d, catalog, snapshot, add = yt
    feed = add()
    ids = {e['source_key']: e['id'] for e in db.rows('SELECT * FROM episodes WHERE feed_id=?', (feed,))}
    file = ready(db, d, ids['youtube:one'])
    snapshot['entries'] = [video('three')]
    catalog.refresh(feed)
    assert db.one('SELECT source_present FROM episodes WHERE id=?', (ids['youtube:one'],))['source_present'] == 0
    assert file.exists()
    assert not db.one('SELECT id FROM episodes WHERE id=?', (ids['youtube:two'],))
    snapshot['entries'] = [{'title': 'Incomplete'}]
    with pytest.raises(ValueError): catalog.refresh(feed)
    assert db.one('SELECT id FROM episodes WHERE id=?', (ids['youtube:three'],))
    snapshot['entries'] = [video('three')]
    d.remove_copy(ids['youtube:one'])
    catalog.refresh(feed)
    assert not db.one('SELECT id FROM episodes WHERE id=?', (ids['youtube:one'],))


def test_hide_preserved_through_sync_and_excluded_from_random(yt):
    c, p, db, _, d, catalog, _, add = yt
    feed = add('yt_channel')
    id_ = db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))['id']
    ready(db, d, id_)
    assert c.put(f'/api/v1/episodes/{id_}/hidden', json={'value': True}).status_code == 200
    catalog.refresh(feed)
    assert db.one('SELECT hidden FROM episodes WHERE id=?', (id_,))['hidden'] == 1
    assert id_ not in [e['id'] for e in c.get('/api/v1/episodes').json()['items']]
    assert id_ in [e['id'] for e in c.get('/api/v1/episodes?filter=hidden').json()['items']]
    assert id_ not in [e['id'] for e in c.get('/api/v1/browser/candidates').json()]
    assert c.delete(f'/api/v1/episodes/{id_}').status_code == 409
    assert c.put(f'/api/v1/episodes/{id_}/hidden', json={'value': False}).status_code == 200


def test_bookmark_and_queue_download_once_and_removing_intent_keeps_download(yt):
    c, p, db, _, d, _, _, add = yt
    feed = add()
    id_ = db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))['id']
    assert c.put(f'/api/v1/episodes/{id_}/bookmark', json={'value': True}).status_code == 200
    task = db.one('SELECT id,state FROM downloads WHERE episode_id=?', (id_,))
    assert task['state'] == 'queued'
    assert c.post('/api/v1/queue', json={'episode_id': id_}).status_code == 200
    assert db.one('SELECT id FROM downloads WHERE episode_id=?', (id_,))['id'] == task['id']
    c.put(f'/api/v1/episodes/{id_}/bookmark', json={'value': False})
    c.delete(f'/api/v1/queue/{id_}')
    assert db.one('SELECT state FROM downloads WHERE episode_id=?', (id_,))['state'] == 'queued'


def test_collection_deletion_removes_files_and_single_import_can_be_removed(yt):
    c, _, db, _, d, _, _, add = yt
    feed = add()
    id_ = db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))['id']
    file = ready(db, d, id_)
    assert c.delete(f'/api/v1/feeds/{feed}').status_code == 200
    assert not file.exists() and not db.one('SELECT id FROM episodes WHERE id=?', (id_,))
    response = c.post('/api/v1/links', json={'url': 'https://youtu.be/single'})
    id_ = response.json()['episode_id']
    file = ready(db, d, id_)
    assert c.delete(f'/api/v1/episodes/{id_}').json()['file_deleted'] is True
    assert not file.exists()


def test_mpd_wait_freezes_sleep_timer_resumes_when_ready_and_pause_cancels(yt):
    c, p, db, mpd, d, _, _, add = yt
    feed = add()
    id_ = db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))['id']
    p.start_episode(1, announce=False)
    c.post('/api/v1/queue', json={'episode_id': id_})
    response = c.post('/api/v1/playback/next')
    assert response.status_code == 200, response.text
    assert response.json()['waiting_download'] is True
    assert p.saved['deadline'] is None
    remaining = p.remaining()
    p.sync()
    assert p.remaining() == remaining and mpd.state == 'pause'
    ready(db, d, id_)
    p.sync()
    assert p.state()['current']['id'] == id_ and mpd.state == 'play'
    assert not p.state()['waiting_download'] and not p.queue()
    other = db.one('SELECT id FROM episodes WHERE feed_id=? AND id<>?', (feed, id_))['id']
    c.post('/api/v1/queue', json={'episode_id': other})
    c.post('/api/v1/playback/next')
    c.post('/api/v1/playback/pause')
    ready(db, d, other)
    p.sync()
    assert mpd.state == 'pause' and not p.state()['waiting_download']


def test_failed_download_is_marked_and_queue_continues(yt):
    c, p, db, mpd, _, _, _, add = yt
    feed = add()
    id_ = db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))['id']
    c.post('/api/v1/queue', json={'episode_id': id_})
    c.post('/api/v1/queue', json={'episode_id': 2})
    c.post('/api/v1/playback/next')
    db.execute("UPDATE downloads SET state='error' WHERE episode_id=?", (id_,))
    p.sync()
    assert p.state()['current']['id'] == 2 and mpd.state == 'play'
    assert db.one('SELECT error FROM queue WHERE episode_id=?', (id_,))['error']


def test_collection_urls_are_explicit_and_channel_normalizes_to_videos():
    assert collection_url('https://youtube.com/@abc/shorts', 'yt_channel') == 'https://www.youtube.com/@abc/videos'
    assert collection_url('https://youtube.com/watch?v=abc&list=PL1', 'yt_playlist').endswith('playlist?list=PL1')
    for url in ['https://other.test/playlist?list=PL1', 'https://youtube.com/watch?v=abc']:
        with pytest.raises(ValueError): collection_url(url, 'yt_channel')
