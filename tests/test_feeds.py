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
