import json


def test_catalog_search_matches_podcast_episode_unicode_and_literal_symbols(rig):
    c,_,db,_,_=rig
    db.execute("UPDATE feeds SET title='Über Glück' WHERE id=1")
    db.execute("UPDATE episodes SET title='Straße 100%' WHERE id=4")
    for query,ids,feeds in [('ÜBER',[1,2,3],[1]),('GLÜCK',[1,2,3],[1]),('STRASSE',[4],[2]),('100%',[4],[2]),('%',[4],[2]),('absent',[],[])]:
        result=c.get('/api/v1/episodes',params={'q':query}).json()
        assert {e['id'] for e in result['items']}==set(ids)
        assert result['total']==len(ids)
        assert {f['id'] for f in c.get('/api/v1/feeds',params={'q':query}).json()}==set(feeds)
    assert c.get('/api/v1/episodes',params={'q':'ÜBER','feed_id':2}).json()['total']==0


def test_last_refresh_is_persistent_and_distinguishes_running_failed_feeds(rig):
    c,_,db,_,_=rig
    assert c.get('/api/v1/config').json()['rss_last_refresh'] is None
    db.execute("INSERT INTO jobs(id,kind,state,created,finished,results) VALUES('old','refresh','done',10,20,'[]')")
    db.execute("INSERT INTO jobs(id,kind,state,created,finished,results) VALUES('recent','refresh','done',30,40,?)",(json.dumps([{'ok':True},{'ok':False}]),))
    db.execute("INSERT INTO jobs(id,kind,state,created) VALUES('scan','media','running',50)")
    assert c.get('/api/v1/config').json()['rss_last_refresh']=={'created':30,'finished':40,'state':'done','errors':1}
    db.execute("INSERT INTO jobs(id,kind,state,created) VALUES('running','refresh','running',60)")
    assert c.get('/api/v1/config').json()['rss_last_refresh']=={'created':60,'finished':None,'state':'running','errors':0}


def test_empty_link_import_list_keeps_collection_favorite_and_files(rig,tmp_path):
    c,p,db,mpd,_=rig
    id_=db.execute("INSERT INTO feeds(url,title,kind,favorite) VALUES('playpod-links://manual','Linkimporte','links',1)")
    db.execute('UPDATE episodes SET feed_id=?,bookmarked=1,position=10 WHERE id=1',(id_,))
    d=c.app.state.downloads
    file=d.directory/'b4d8cf9b-af79-4618-b0ce-1c29b4f2763.audio'
    file.write_bytes(b'audio')
    db.execute("INSERT INTO downloads(episode_id,id,source_url,state,updated,received) VALUES(1,?,'http://test/audio','ready',1,5)",(file.stem,))
    p.start_episode(1,announce=False)
    p.enqueue(1)
    response=c.delete(f'/api/v1/feeds/{id_}/episodes')
    assert response.status_code==200 and response.json()=={'deleted':1,'files_deleted':False}
    assert mpd.state=='stop' and p.queue()==[]
    assert not db.one('SELECT 1 FROM episodes WHERE id=1')
    assert not db.one('SELECT 1 FROM downloads WHERE episode_id=1')
    assert db.one('SELECT favorite FROM feeds WHERE id=?',(id_,))['favorite']==1
    assert file.exists()
    assert c.delete('/api/v1/feeds/2/episodes').status_code==409
    assert c.delete('/api/v1/feeds/999/episodes').status_code==404


def test_import_label_upgrade_keeps_identity_favorite_and_custom_name(rig):
    from app.config import Settings
    from app.downloads import Downloads
    _,_,db,_,_=rig
    id_=db.execute("INSERT INTO feeds(url,title,kind,favorite) VALUES('playpod-links://manual','Einzelne Links','links',1)")
    for old,expected in [('Einzelne Links','YouTube · Einzelimporte'),('Linkimporte','YouTube · Einzelimporte'),('Eigene Auswahl','Eigene Auswahl')]:
        db.execute('UPDATE feeds SET title=? WHERE id=?',(old,id_))
        d=Downloads(db,Settings(database=db.path))
        assert db.one('SELECT id,title,favorite FROM feeds WHERE id=?',(id_,))=={'id':id_,'title':expected,'favorite':1}
        d.close()
