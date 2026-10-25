import time


def test_removed_legacy_endpoints_do_not_change_state(rig):
    client, p, _, mpd, _ = rig
    p.start_episode(1)
    before = (mpd.state, mpd.elapsed, mpd.volume, p.mode, p.saved['episode_id'])
    for url in ['/api/play', '/api/play?force=1', '/api/ff', '/api/rw',
                '/api/volume_up', '/api/volume_down', '/api/toggle_mode', '/api/update', '/api/status']:
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()['error']['code'] == 'not_found'
    assert before == (mpd.state, mpd.elapsed, mpd.volume, p.mode, p.saved['episode_id'])


def test_health_and_live_are_preserved(rig):
    client,p,_,mpd,_=rig
    assert client.get('/api/health').status_code==200
    mpd.unavailable=True
    assert client.get('/api/health').status_code==500
    assert client.get('/api/live').status_code==200
    p.sync()
    assert client.get('/api/v1/state').json()['state']=='error'


def test_new_api_validation_and_filters(rig):
    client,p,db,_,_=rig
    assert client.post('/api/v1/seek',json={'position_seconds':-1}).status_code==422
    assert client.put('/api/v1/volume',json={'value':101}).status_code==422
    assert client.put('/api/v1/timer',json={'minutes':-1}).status_code==422
    assert client.post('/api/v1/feeds',json={'url':'file:///tmp/x'}).status_code==422
    client.put('/api/v1/episodes/2/bookmark',json={'value':True})
    result=client.get('/api/v1/episodes?filter=marked').json()
    assert [e['id'] for e in result['items']]==[2]
    assert client.get('/api/v1/episodes?feed_id=2').json()['total']==2
    assert client.get('/api/v1/episodes?limit=2&offset=2').json()['total']==5


def test_cleanup_only_deletes_explicitly_unreachable(rig):
    client,p,db,_,_=rig
    assert client.post('/api/v1/cleanup/delete',json={'ids':[1]}).status_code==409
    db.execute("UPDATE episodes SET availability='temporary_error' WHERE id=1")
    assert client.post('/api/v1/cleanup/delete',json={'ids':[1]}).status_code==409
    db.execute("UPDATE episodes SET availability='unreachable' WHERE id=1")
    assert client.post('/api/v1/cleanup/delete',json={'ids':[1]}).json()=={'deleted':1}
    assert not db.one('SELECT 1 FROM episodes WHERE id=1')
    db.execute("UPDATE episodes SET availability='temporary_error' WHERE id=2")
    assert client.post('/api/v1/cleanup/delete',json={'ids':[2],'include_temporary':True}).json()=={'deleted':1}


def test_seek_works_while_paused_and_from_start_preserves_queue(rig):
    client,p,_,mpd,_=rig
    p.start_episode(1)
    p.pause()
    assert client.post('/api/v1/seek',json={'position_seconds':123}).status_code==200
    assert mpd.elapsed==123
    p.enqueue(2)
    client.post('/api/v1/episodes/play',json={'episode_id':1,'from_start':True})
    assert mpd.elapsed==0
    assert [e['id'] for e in p.queue()]==[2]
