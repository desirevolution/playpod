from contextlib import contextmanager
from app.feeds import duration_seconds, safe_html

RSS=b'''<?xml version="1.0"?><rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel><title>Feed name</title><item><guid>abc</guid><title>First</title><enclosure url="http://example.test/audio.mp3" type="audio/mpeg"/><itunes:duration>1:02:03</itunes:duration></item><item><guid>trailer</guid><title>Trailer</title><itunes:episodeType>trailer</itunes:episodeType><enclosure url="http://example.test/t.mp3" type="audio/mpeg"/></item></channel></rss>'''


class FakeResponse:
    status_code=200
    url='http://example.test/rss'
    headers={'Content-Type':'application/rss+xml'}
    def __init__(self,content=RSS,status=200):
        self.content=content
        self.status_code=status
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def raise_for_status(self):pass
    def iter_content(self,size):yield self.content


def test_feed_idempotence_title_update_and_guid(rig,monkeypatch):
    client,p,db,mpd,n=rig
    response=FakeResponse()
    monkeypatch.setattr('app.feeds.requests.get',lambda *a,**k:response)
    jobs=client.app.state.jobs
    assert jobs.refresh(1,'http://example.test/rss')==1
    ep=db.one("SELECT * FROM episodes WHERE guid='abc'")
    assert ep['duration']==3723
    db.execute('UPDATE episodes SET bookmarked=1,position=10 WHERE id=?',(ep['id'],))
    response.content=RSS.replace(b'First',b'Renamed')
    jobs.refresh(1,'http://example.test/rss')
    eps=db.rows("SELECT * FROM episodes WHERE guid='abc'")
    assert len(eps)==1
    assert eps[0]['title']=='Renamed'
    assert eps[0]['bookmarked']==1
    assert eps[0]['position']==10
    assert not db.one("SELECT 1 FROM episodes WHERE guid='trailer'")


def test_url_check_classifies_temporary_and_missing(rig,monkeypatch):
    jobs=rig[0].app.state.jobs
    monkeypatch.setattr('app.feeds.requests.get',lambda *a,**k:FakeResponse(status=404))
    assert jobs.check('http://example.test/a')['status']=='unreachable'
    monkeypatch.setattr('app.feeds.requests.get',lambda *a,**k:FakeResponse(status=503))
    assert jobs.check('http://example.test/a')['status']=='temporary_error'
    monkeypatch.setattr('app.feeds.requests.get',lambda *a,**k:FakeResponse(status=200))
    assert jobs.check('http://example.test/a')['status']=='reachable'


def test_descriptions_sanitized_and_duration():
    assert 'onerror' not in safe_html('<img src=x onerror=alert(1)>')
    assert 'javascript:' not in safe_html('<a href="javascript:alert(1)">x</a>')
    assert duration_seconds('1:02:03')==3723
    assert duration_seconds('unknown')==0


def test_feed_refresh_prefers_guid_over_another_episodes_url(rig, monkeypatch):
    client, _, db, _, _ = rig
    db.execute("UPDATE episodes SET source_key='guid:abc',position=42 WHERE id=2")
    response = FakeResponse(RSS.replace(b'audio.mp3', b'1.mp3'))
    monkeypatch.setattr('app.feeds.requests.get', lambda *args, **kwargs: response)

    assert client.app.state.jobs.refresh(1, 'http://example.test/rss') == 1

    assert db.one('SELECT title FROM episodes WHERE id=1')['title'] == 'Episode 1'
    episode = db.one('SELECT title,url,position FROM episodes WHERE id=2')
    assert episode == {'title': 'First', 'url': 'http://example.test/1.mp3', 'position': 42}


def test_display_title_survives_refresh_and_can_be_cleared(rig, monkeypatch):
    client, _, db, _, _ = rig
    url = 'http://example.test/rss'
    monkeypatch.setattr('app.feeds.requests.get', lambda *args, **kwargs: FakeResponse())
    jobs = client.app.state.jobs
    assert client.put('/api/v1/feeds/1', json={'url': url, 'title': 'Mein Podcast'}).is_success
    assert jobs.refresh(1, url) == 1

    feed = client.get('/api/v1/feeds', params={'q': 'Mein Podcast'}).json()[0]
    assert feed['title'] == feed['display_title'] == 'Mein Podcast'
    assert db.one('SELECT title FROM feeds WHERE id=1')['title'] == 'Feed name'
    assert client.get('/api/v1/episodes/1').json()['podcast'] == 'Mein Podcast'
    assert client.get('/api/v1/activity').json()['items'][0]['podcast'] == 'Mein Podcast'

    assert client.put('/api/v1/feeds/1', json={'url': url, 'display_title': None}).is_success
    feed = client.get('/api/v1/feeds', params={'q': 'Feed name'}).json()[0]
    assert feed['title'] == 'Feed name' and feed['display_title'] is None
