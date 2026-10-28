from copy import deepcopy
from uuid import uuid4
import pytest

from app.db import Database
from app.youtube import collection_url


def video(id_, **extra):
    return {'id': id_, 'title': 'Video ' + id_, 'url': 'https://www.youtube.com/watch?v=' + id_,
            'duration': 120, 'thumbnail': 'https://i.ytimg.com/' + id_ + '.jpg', **extra}


def test_localized_details_cache_is_language_specific_and_does_not_change_catalog(yt, monkeypatch):
    c, _, db, _, _, _, _, add = yt
    feed = add()
    ep = db.one('SELECT * FROM episodes WHERE feed_id=?', (feed,))
    calls = []
    def metadata(url, language, *args):
        calls.append((url, language))
        return {'title': 'Deutscher Titel' if language == 'de' else 'English title',
                'description': 'Text <script>unsafe</script>\nZeile 2',
                'thumbnail': 'https://i.ytimg.com/details.jpg'}
    monkeypatch.setattr('app.ytdlp.metadata', metadata)
    url = f"/api/v1/episodes/{ep['id']}"
    localized = c.get(url + '?language=de').json()
    assert localized['title'] == 'Deutscher Titel'
    assert localized['cover'].endswith('details.jpg')
    assert '&lt;script&gt;' in localized['description'] and '<br>' in localized['description']
    assert c.get(url + '?language=en').json()['title'] == 'English title'
    db.execute('UPDATE episodes SET bookmarked=1,position=42 WHERE id=?', (ep['id'],))
    cached = c.get(url + '?language=de').json()
    assert cached['bookmarked'] == 1 and cached['position'] == 42
    assert len(calls) == 2
    assert c.get(url).json()['title'] == ep['title']
    assert c.get(url + '?language=fr').status_code == 422
    # RSS details never invoke yt-dlp, even when a language was supplied.
    assert c.get('/api/v1/episodes/1?language=de').status_code == 200
    assert len(calls) == 2


def test_details_failure_keeps_existing_metadata_and_can_retry(yt, monkeypatch):
    c, _, db, _, _, _, _, add = yt
    feed = add()
    ep = db.one('SELECT * FROM episodes WHERE feed_id=?', (feed,))
    def fail(*args): raise ValueError('offline')
    monkeypatch.setattr('app.ytdlp.metadata', fail)
    url = f"/api/v1/episodes/{ep['id']}?language=de"
    result = c.get(url).json()
    assert result['title'] == ep['title'] and result['metadata_error']
    monkeypatch.setattr('app.ytdlp.metadata', lambda *args: {'title': 'Wieder verfügbar'})
    assert c.get(url).json()['title'] == 'Wieder verfügbar'


def test_library_uses_loaded_language_variant_and_can_search_it_without_network(yt, monkeypatch):
    c, _, db, _, _, catalog, _, add = yt
    feed = add()
    ep = db.one('SELECT * FROM episodes WHERE feed_id=?', (feed,))
    monkeypatch.setattr('app.ytdlp.metadata', lambda *args: {
        'title': 'Über die gegenwärtige Linke', 'description': 'Beschreibung',
        'thumbnail': 'https://example.test/de.jpg'})
    assert c.get(f"/api/v1/episodes/{ep['id']}?language=de").status_code == 200
    def fail(*args): raise AssertionError('Library must never extract metadata')
    monkeypatch.setattr('app.ytdlp.metadata', fail)
    url = f'/api/v1/episodes?feed_id={feed}'
    items = c.get(url + '&language=de').json()['items']
    assert next(e for e in items if e['id'] == ep['id'])['title'] == 'Über die gegenwärtige Linke'
    for suffix in ('', '&language=en'):
        assert next(e for e in c.get(url + suffix).json()['items'] if e['id'] == ep['id'])['title'] == ep['title']
    result = c.get(url + '&language=de&q=GEGENWÄRTIGE').json()
    assert result['total'] == 1 and result['items'][0]['id'] == ep['id']
    assert c.get(url + '&language=en&q=GEGENWÄRTIGE').json()['total'] == 0
    assert [f['id'] for f in c.get('/api/v1/feeds?language=de&q=gegenwärtige').json()] == [feed]
    assert c.get('/api/v1/feeds?language=en&q=gegenwärtige').json() == []
    catalog.refresh(feed)
    assert c.get(url + '&language=de&q=gegenwärtige').json()['items'][0]['title'] == 'Über die gegenwärtige Linke'
    assert db.one('SELECT title FROM episodes WHERE id=?', (ep['id'],))['title'] == ep['title']


def test_metadata_runner_requests_language_without_downloading(monkeypatch, capsys):
    import json
    from app import ytdlp_runner
    class Extractor:
        def __init__(self, options):
            assert options['extractor_args']['youtube']['lang'] == ['de']
            assert options['skip_download'] and options['noplaylist']
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert download is False
            return {'title': 'Titel', 'description': 'Beschreibung',
                    'thumbnails': [{'url': 'https://example.test/cover.jpg'}]}
    monkeypatch.setattr('yt_dlp.YoutubeDL', Extractor)
    monkeypatch.setattr(ytdlp_runner, 'javascript_options', lambda: {})
    ytdlp_runner.metadata('https://youtube.com/watch?v=abcdefghijk', 'de')
    result = json.loads(capsys.readouterr().out)
    assert result['description'] == 'Beschreibung' and result['thumbnails']


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
    snapshot['entries'] += [video('short', url='https://www.youtube.com/shorts/short'), video('live', live_status='is_live'), video('upcoming', live_status='is_upcoming'), video('private', availability='private')]
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


def test_legacy_empty_playlist_recovers_on_refresh_without_readding(yt):
    c, _, db, _, _, catalog, snapshot, add = yt
    feed = add(limit=1)
    # Previous versions could mark every discovered ID seen despite importing none.
    db.execute('DELETE FROM episodes WHERE feed_id=?', (feed,))
    db.execute('DELETE FROM settings WHERE key=?', (f'yt_skipped:{feed}',))
    assert db.get(f'yt_seen:{feed}') == ['one', 'three', 'two']
    assert catalog.refresh(feed) == 1
    assert db.one('SELECT title FROM episodes WHERE feed_id=?', (feed,))['title'] == 'Video one'
    catalog.refresh(feed)
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 1
    status = next(f for f in c.get('/api/v1/feeds').json() if f['id'] == feed)['import_status']
    assert status['found'] == 3 and status['stored'] == 1 and status['initial_limit_skipped'] == 2


def test_temporarily_private_video_is_imported_when_it_becomes_public(yt):
    _, _, db, _, _, catalog, snapshot, add = yt
    snapshot['entries'] = [video('one', availability='private'), video('two')]
    feed = add(limit=1)
    assert db.one('SELECT source_key FROM episodes WHERE feed_id=?', (feed,))['source_key'] == 'youtube:two'
    snapshot['entries'][0]['availability'] = 'public'
    assert catalog.refresh(feed) == 1
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 2


def test_populated_legacy_collection_keeps_its_initial_limit(yt):
    _, _, db, _, _, catalog, _, add = yt
    feed = add(limit=1)
    db.execute('DELETE FROM settings WHERE key=?', (f'yt_skipped:{feed}',))
    assert catalog.refresh(feed) == 0
    assert db.one('SELECT COUNT(*) n FROM episodes WHERE feed_id=?', (feed,))['n'] == 1


def test_empty_import_explains_excluded_and_unavailable_entries(yt):
    c, _, db, _, _, _, snapshot, add = yt
    snapshot['entries'] = [video('one', media_type='short'), video('two', live_status='is_live'), video('three', availability='private')]
    feed = add()
    status = next(f for f in c.get('/api/v1/feeds').json() if f['id'] == feed)['import_status']
    assert status['found'] == 3 and status['excluded'] == 2 and status['unavailable'] == 1 and status['stored'] == 0
    assert not db.one('SELECT id FROM episodes WHERE feed_id=?', (feed,))


def test_real_ytdlp_flat_video_metadata_passes_collector_and_import(yt, monkeypatch, capsys):
    import json
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeTabIE
    from app import ytdlp_runner
    with YoutubeDL({'quiet': True, 'cachedir': False}) as ydl:
        item = YoutubeTabIE(ydl)._extract_video({
            'videoId': 'abcdefghijk', 'title': {'runs': [{'text': 'Normales Video'}]},
            'lengthText': {'simpleText': '12:34'},
            'thumbnail': {'thumbnails': [{'url': 'https://i.ytimg.com/vi/abcdefghijk/hqdefault.jpg'}]},
            'publishedTimeText': {'simpleText': '2 days ago'},
        })
    class FlatExtractor:
        def __init__(self, options):
            assert options['extract_flat'] is True and options['skip_download'] is True
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, url, download):
            assert download is False
            return {'_type': 'playlist', 'title': 'Echte Metadatenform', 'entries': iter([item])}
    monkeypatch.setattr('yt_dlp.YoutubeDL', FlatExtractor)
    monkeypatch.setattr(ytdlp_runner, 'javascript_options', lambda: {})
    ytdlp_runner.catalog('https://youtube.com/playlist?list=PLtest')
    result = json.loads(capsys.readouterr().out)
    _, _, db, _, _, _, snapshot, add = yt
    snapshot.update(result)
    feed = add()
    ep = db.one('SELECT title,duration,cover FROM episodes WHERE feed_id=?', (feed,))
    assert ep['title'] == 'Normales Video' and ep['duration'] == 754
    assert ep['cover'].endswith('/hqdefault.jpg')


def test_collector_rejects_empty_result_when_youtube_declares_entries(monkeypatch):
    from app import ytdlp_runner
    class EmptyExtractor:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs):
            return {'_type': 'playlist', 'title': 'Playlist', 'playlist_count': 4, 'entries': []}
    monkeypatch.setattr('yt_dlp.YoutubeDL', EmptyExtractor)
    monkeypatch.setattr(ytdlp_runner, 'javascript_options', lambda: {})
    with pytest.raises(ValueError, match='Eintragsliste ist leer'):
        ytdlp_runner.catalog('https://youtube.com/playlist?list=PLtest')


def test_completed_live_recording_imports_and_repairs_previously_empty_collection(yt):
    _, _, db, _, _, catalog, snapshot, add = yt
    # Metadata shape observed for the user's actual one-video playlist "podsync".
    recording = video('_fywShwdD6c', live_status='was_live', is_live=None, was_live=None,
                      media_type=None, duration=4361, availability=None)
    snapshot['entries'] = []
    feed = add(limit=1)
    db.put(f'yt_seen:{feed}', ['_fywShwdD6c'])
    db.execute('DELETE FROM settings WHERE key=?', (f'yt_skipped:{feed}',))
    snapshot['entries'] = [recording]
    assert catalog.refresh(feed) == 1
    assert db.one('SELECT duration FROM episodes WHERE feed_id=?', (feed,))['duration'] == 4361
    assert db.get(f'yt_status:{feed}')['excluded'] == 0


@pytest.mark.parametrize('status,is_live,was_live,media_type,accepted', [
    ('was_live', False, True, 'livestream', True),
    ('was_live', None, None, None, True),
    ('post_live', False, True, 'livestream', True),
    ('is_live', True, False, 'livestream', False),
    ('is_upcoming', False, False, 'livestream', False),
    ('not_live', False, False, 'short', False),
])
def test_download_runner_uses_same_filter_as_catalog(monkeypatch, tmp_path, status, is_live, was_live, media_type, accepted):
    from app import ytdlp_runner
    processed = []
    info = {'id': 'abcdefghijk', 'title': 'Video', 'live_status': status,
            'is_live': is_live, 'was_live': was_live, 'media_type': media_type}
    class Extractor:
        def __init__(self, options): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def extract_info(self, *args, **kwargs): return info
        def add_post_processor(self, *args, **kwargs): pass
        def process_ie_result(self, value, download):
            assert download is True
            processed.append(value)
    monkeypatch.setattr('yt_dlp.YoutubeDL', Extractor)
    monkeypatch.setattr(ytdlp_runner, 'javascript_options', lambda: {})
    if accepted:
        ytdlp_runner.run('https://youtube.com/watch?v=abcdefghijk', tmp_path, 1000)
        assert processed == [info]
    else:
        with pytest.raises(ValueError):
            ytdlp_runner.run('https://youtube.com/watch?v=abcdefghijk', tmp_path, 1000)
        assert not processed
