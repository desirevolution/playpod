"""Real python-mpd2 sockets: connection lifetime, idle events and player deadlines."""
import socket
import socketserver
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest

from app.config import Settings
from app.integrations import MPD


def eventually(predicate, timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        threading.Event().wait(.02)
    assert predicate()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        s=self.server
        with s.condition:
            s.connections+=1
            version=s.version
            s.peers.add(self.request)
        self.wfile.write(b'OK MPD 0.24.0\n')
        batch=False
        try:
            while raw:=self.rfile.readline():
                command=raw.decode().strip()
                with s.condition:
                    s.commands.append(command)
                    name=command.split()[0]
                    args=[a.strip('"') for a in command.split()[1:]]
                    if name=='idle':
                        s.idlers.add(self.request)
                        while s.version==version and not s.stopped:
                            s.condition.wait(.05)
                        s.idlers.discard(self.request)
                        if s.stopped:return
                        version=s.version
                        reply='changed: player\n'
                    elif name=='command_list_ok_begin':
                        batch=True
                        continue
                    elif name=='command_list_end':
                        batch=False
                        reply=''
                    elif name=='status':
                        if s.drop_read:
                            s.drop_read=False
                            return
                        reply=f'state: {s.state}\nelapsed: {s.elapsed}\nduration: 1200\nvolume: {s.volume}\n'
                    elif name=='currentsong':reply=s.song_info()
                    elif name=='playlistinfo':reply=''.join(f'file: {url}\nId: {id_}\n' for id_,url in s.songs.items())
                    elif name=='addid':
                        s.counter+=1;s.songs[str(s.counter)]=args[0]
                        reply=f'Id: {s.counter}\n'
                    else:
                        reply=''
                        if name=='setvol':s.volume=int(args[0])
                        elif name=='playid':s.song_id=args[0];s.state='play';s.elapsed=0
                        elif name=='seekid':s.song_id=args[0];s.elapsed=float(args[1]);s.state='play'
                        elif name=='seekcur':s.elapsed=float(args[0])
                        elif name=='pause':s.state='pause' if args[0]=='1' else 'play'
                        elif name=='stop':s.state='stop'
                        elif name=='deleteid':s.songs.pop(args[0],None)
                        elif name=='clear':s.songs.clear();s.song_id=None;s.state='stop'
                        if name in ('setvol','playid','seekid','pause','stop','clear'):
                            s.version+=1;s.condition.notify_all()
                        if name=='setvol' and s.drop_write:
                            s.drop_write=False
                            return
                    self.wfile.write((reply+('list_OK\n' if batch else 'OK\n')).encode())
        except (OSError,ValueError):pass
        finally:
            with s.condition:
                s.peers.discard(self.request)
                s.idlers.discard(self.request)


@contextmanager
def protocol_server():
    s=socketserver.ThreadingTCPServer(('127.0.0.1',0),Handler)
    s.daemon_threads=True
    s.condition=threading.Condition()
    s.connections=0;s.version=0;s.commands=[];s.peers=set();s.idlers=set()
    s.stopped=False;s.drop_read=False;s.drop_write=False
    s.state='stop';s.elapsed=0;s.volume=55;s.counter=0;s.song_id=None;s.songs={}
    s.song_info=lambda: f'file: {s.songs[s.song_id]}\nId: {s.song_id}\n' if s.song_id in s.songs else ''
    thread=threading.Thread(target=s.serve_forever,daemon=True);thread.start()
    m=MPD(Settings(mpd_host='127.0.0.1',mpd_port=s.server_address[1]))
    try:yield s,m
    finally:
        m.close()
        with s.condition:
            s.stopped=True;s.condition.notify_all()
            for peer in list(s.peers):
                try:peer.shutdown(socket.SHUT_RDWR)
                except OSError:pass
        s.shutdown();s.server_close();thread.join(timeout=2)


def test_persistent_command_connection_serializes_concurrent_requests():
    with protocol_server() as (s,m):
        with ThreadPoolExecutor(max_workers=6) as pool:
            result=list(pool.map(lambda _: (m.call('setvol',60),m.snapshot())[1], range(12)))
        assert all(status['volume']=='60' for status,_ in result)
        assert s.connections==1


def test_only_lost_reads_are_retried():
    with protocol_server() as (s,m):
        m.snapshot()
        s.drop_read=True
        assert m.snapshot()[0]['volume']=='55'
        assert s.connections==2
        s.drop_write=True
        with pytest.raises(Exception):m.call('setvol',61)
        assert s.commands.count('setvol "61"')==1
        assert m.snapshot()[0]['volume']=='61'
        assert s.connections==3


def test_idle_wakes_on_event_reconnects_and_shutdown_unblocks_reader():
    with protocol_server() as (s,m):
        changed=threading.Event();m.start_events(changed.set)
        assert changed.wait(2)
        eventually(lambda: len(s.idlers)==1)
        changed.clear();m.call('setvol',62)
        assert changed.wait(2)
        eventually(lambda: len(s.idlers)==1)
        assert s.connections==2
        # Simulate a dead idle connection; reconnect must trigger reconciliation.
        changed.clear()
        with s.condition:
            for peer in list(s.idlers):peer.shutdown(socket.SHUT_RDWR)
            s.version+=1;s.condition.notify_all()
        eventually(lambda:s.connections>=3)
        assert changed.is_set()
        started=time.monotonic();m.close()
        assert time.monotonic()-started<1
        assert not m.event_thread.is_alive()


def test_monitor_uses_idle_instead_of_secondly_status_and_keeps_timer(rig):
    _,p,_,_,_=rig
    with protocol_server() as (s,m):
        p.mpd=m;p.start_monitor()
        try:
            eventually(lambda:p.status['state']=='stop')
            p.start_episode(1,announce=False)
            eventually(lambda:len(s.idlers)==1)
            threading.Event().wait(.3)
            reads=s.commands.count('status')
            threading.Event().wait(1.2)
            assert s.commands.count('status')==reads
            assert s.connections==2
            p.timer(1)
            eventually(lambda:p.status['state']=='pause')
            assert p.remaining()==0 and s.state=='pause'
        finally:p.close()


def test_idle_eof_advances_queue_without_near_end_poll(rig):
    _,p,_,_,_=rig
    with protocol_server() as (s,m):
        now=[1000.];p.clock=lambda:now[0]
        p.mpd=m;p.start_monitor()
        try:
            eventually(lambda:p.status['state']=='stop')
            p.timer(0);p.start_episode(1,announce=False);p.enqueue(2)
            eventually(lambda:len(s.idlers)==1)
            threading.Event().wait(.2)
            with s.condition:
                now[0]+=1200;s.state='stop';s.elapsed=0
                s.version+=1;s.condition.notify_all()
            eventually(lambda:p.saved['episode_id']==2)
            assert s.state=='play' and p.queue()==[]
        finally:p.close()


def test_cached_elapsed_and_checkpoint_advance_without_mpd_reads(rig):
    from unittest.mock import Mock
    c,p,db,mpd,_=rig
    now=[1000.];p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    mpd.snapshot=Mock(wraps=mpd.snapshot)
    now[0]+=7
    assert c.get('/api/v1/state').json()['elapsed']==7
    p._checkpoint(estimate=True)
    assert p.episode(1)['position']==7
    mpd.snapshot.assert_not_called()
    p.close()
    assert db.one('SELECT position FROM episodes WHERE id=1')['position']==7


def test_periodic_reconciliation_recovers_a_missed_event(rig,monkeypatch):
    import app.player
    monkeypatch.setattr(app.player,'MPD_RECONCILE_SECONDS',.2)
    _,p,_,_,_=rig
    with protocol_server() as (s,m):
        p.mpd=m;p.start_monitor()
        try:
            eventually(lambda:p.status['volume']==55)
            with s.condition:s.volume=72  # Deliberately omit an idle event.
            eventually(lambda:p.status['volume']==72,timeout=2)
        finally:p.close()


@pytest.mark.parametrize('wanted',['play','pause'])
def test_idle_tts_end_restores_episode_and_prior_pause(rig,wanted):
    _,p,_,_,n=rig
    with protocol_server() as (s,m):
        p.mpd=m;p.start_monitor()
        try:
            eventually(lambda:p.status['state']=='stop')
            p.start_episode(1,announce=False);p.seek(83)
            if wanted=='pause':p.pause()
            n.title_audio=lambda text:'http://ha.test/mode.wav'
            p.set_mode(True)
            eventually(lambda:len(s.idlers)==1)
            with s.condition:
                s.state='stop';s.elapsed=0;s.version+=1;s.condition.notify_all()
            eventually(lambda:not p.saved.get('intro'))
            assert p.status['state']==wanted and s.state==wanted
            assert s.songs[s.song_id]=='http://example.test/1.mp3'
            assert s.elapsed==83
        finally:p.close()


def test_announcement_timeout_still_advances_without_idle_event(rig):
    from types import SimpleNamespace
    _,p,_,_,n=rig
    with protocol_server() as (s,m):
        p.mpd=m;p.start_monitor()
        try:
            eventually(lambda:p.status['state']=='stop')
            n.title_audio=lambda text:'http://ha.test/title.wav'
            n.settings=SimpleNamespace(tts_playback_timeout_seconds=1)
            p.start_episode(1)
            assert p.saved.get('intro')
            eventually(lambda:p.saved['episode_id']==1)
            assert not p.saved.get('intro') and s.state=='play'
        finally:p.close()


def test_external_source_change_keeps_locally_advanced_progress(rig):
    _,p,_,mpd,_=rig
    now=[1000.];p.clock=lambda:now[0]
    p.start_episode(1,announce=False)
    now[0]+=7;p._checkpoint(estimate=True)
    now[0]+=1
    mpd.song={'file':'http://example.test/2.mp3','id':'99'};mpd.elapsed=123
    p.sync()
    assert p.episode(1)['position']==8
    assert p.saved['episode_id']==2 and p.status['elapsed']==123
