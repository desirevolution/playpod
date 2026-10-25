import test from 'node:test';
import assert from 'node:assert/strict';
import { BrowserPlayer } from '../src/browser-player.ts';

class AudioFake extends EventTarget {
  currentTime=0;duration=100;readyState=0;paused=true;ended=false;volume=.55;seeking=false;src='';error=null;blocked=false;plays=0;
  load(){this.ended=false;this.currentTime=0;this.readyState=0;if(this.src)queueMicrotask(()=>{this.readyState=1;this.dispatchEvent(new Event('loadedmetadata'));});}
  async play(){this.ended=false;this.plays++;if(this.blocked)throw Object.assign(new Error('blocked'),{name:'NotAllowedError'});this.paused=false;await Promise.resolve();this.dispatchEvent(new Event('playing'));}
  pause(){this.paused=true;this.dispatchEvent(new Event('pause'));}
  removeAttribute(){this.src='';}
  advance(n){if(!this.paused)this.currentTime+=n;this.dispatchEvent(new Event('timeupdate'));}
  finish(){this.ended=true;this.currentTime=100;this.paused=true;this.dispatchEvent(new Event('ended'));}
}
function rig(t,saved={}){
  const calls=[],audio=new AudioFake(),data=new Map([['playpod.browser.v1',JSON.stringify({seconds:900,when_queue_empty:'random_unheard',...saved})]]);
  const storage={getItem:key=>data.get(key)||null,setItem:(key,value)=>data.set(key,value)};
  const ep=id=>({id,feed_id:1,title:'Episode '+id,podcast:'Podcast',duration:100,position:0,completed:0,bookmarked:0,url:'http://source/'+id});
  const request=async(path,method='GET',body)=>{
    calls.push({path,method,body});
    if(path.startsWith('episodes/'))return ep(Number(path.split('/')[1]));
    if(path.startsWith('browser/episodes/'))return {episode:ep(Number(path.split('/')[2])),url:'/media/'+path.split('/')[2],source_kind:'local'};
    if(path.startsWith('browser/candidates'))return [{id:1},{id:2},{id:3}];
    if(path==='browser/progress')return {ok:true};
    throw new Error('Unexpected backend call '+path);
  };
  const p=new BrowserPlayer(request,()=>{},audio,storage);
  t.after(()=>p.dispose());
  return {p,audio,calls,data,request};
}
const settled=()=>new Promise(r=>setTimeout(r,0));

test('prepared browser audio reports usage while paused and releases it on disposal', async t => {
  const {p,calls}=rig(t,{seconds:0,when_queue_empty:'stop'});
  await p.init(); await p.start(1); await p.progressChain;
  assert.equal(calls.filter(c=>c.path==='browser/progress').at(-1).body.in_use,true);
  p.pause(); await p.progressChain;
  assert.equal(calls.filter(c=>c.path==='browser/progress').at(-1).body.in_use,true);
  p.dispose(); await p.progressChain;
  assert.equal(calls.filter(c=>c.path==='browser/progress').at(-1).body.in_use,false);
});

test('activity playback identifiers survive pause and reload and change on replay', async t => {
  const {p,audio,calls,data}=rig(t, {seconds:0,when_queue_empty:'stop'});
  await p.init();
  await p.start(1);
  await p.progressChain;
  const first=p.playbackId;
  assert.match(first,/^[0-9a-f]{32}$/);
  p.pause(); await p.play();
  assert.equal(p.playbackId,first);
  assert.equal(JSON.parse(data.get('playpod.browser.v1')).playback_id,first);
  const restored=rig(t,JSON.parse(data.get('playpod.browser.v1'))).p;
  await restored.init();
  assert.equal(restored.playbackId,first);
  audio.finish(); await settled(); await p.progressChain;
  const completed=calls.filter(call=>call.path==='browser/progress'&&call.body.completed);
  assert.equal(completed.length,1);
  assert.equal(completed[0].body.playback_id,first);
  await p.play();
  assert.notEqual(p.playbackId,first);
});

test('browser controls and queue never use MPD endpoints',async t=>{
  const {p,audio,calls}=rig(t);await p.init();
  await p.command('queue','POST',{episode_id:2});
  await p.command('playback/play','POST');
  assert.equal(p.current.id,2);assert.equal(p.queue.length,0);assert.equal(audio.paused,false);
  await p.command('volume/adjust','POST',{delta:5});assert.equal(p.snapshot().volume,60);
  await p.command('seek','POST',{position_seconds:50});assert.equal(audio.currentTime,50);
  assert.ok(calls.every(c=>c.path.startsWith('browser/')||c.path.startsWith('episodes/')));
});

test('timer consumes playback only, seeks do not consume it, resume and manual next rearm',async t=>{
  const {p,audio}=rig(t);await p.start(1);
  audio.advance(30);assert.equal(p.left,870);
  await p.command('seek','POST',{position_seconds:60});p.tick();assert.equal(p.left,870);
  p.pause();audio.advance(20);assert.equal(p.left,870);
  await p.play();assert.equal(p.left,900);
  audio.advance(10);await p.command('queue','POST',{episode_id:2});await p.next();
  assert.equal(p.current.id,2);assert.equal(p.left,900);
  await p.command('timer','PUT',{minutes:30});p.pause();await p.play();assert.equal(p.left,1800);
});

test('automatic EOF keeps remaining time and uses local queue',async t=>{
  const {p,audio}=rig(t);await p.start(1);await p.command('queue','POST',{episode_id:2});
  audio.finish();await settled();
  assert.equal(p.current.id,2);assert.equal(p.left,800);assert.equal(p.queue.length,0);
});

test('expiry pauses without consuming queue; off stays off',async t=>{
  const {p,audio}=rig(t);await p.start(1);await p.command('queue','POST',{episode_id:2});
  p.seconds=10;p.left=10;audio.advance(11);
  assert.equal(audio.paused,true);assert.equal(p.left,0);assert.equal(p.queue.length,1);
  await p.command('timer','PUT',{minutes:0});await p.play();audio.advance(80);
  assert.equal(audio.paused,false);assert.equal(p.snapshot().timer.enabled,false);
});

test('reload restores browser queue and position without autoplay',async t=>{
  const {p,audio}=rig(t,{current:1,position:42,queue:[2,3],seconds:1800});await p.init();
  assert.equal(audio.plays,0);assert.equal(p.snapshot().state,'pause');assert.equal(p.snapshot().elapsed,42);
  assert.deepEqual(p.queue.map(e=>e.id),[2,3]);await p.play();assert.equal(audio.currentTime,42);
});

test('autoplay denial keeps queue until an explicit successful play',async t=>{
  const {p,audio}=rig(t);await p.command('queue','POST',{episode_id:2});audio.blocked=true;
  await assert.rejects(p.next(),{name:'NotAllowedError'});
  assert.equal(p.queue.length,1);assert.equal(p.current.id,2);assert.equal(audio.paused,true);
  audio.blocked=false;await p.play();assert.equal(p.queue.length,0);
});

test('paused target cancels an outstanding source request',async t=>{
  const {p,audio,request}=rig(t);let resolve;
  p.request=path=>path.startsWith('browser/episodes/')?new Promise(r=>resolve=r):request(path);
  const start=p.start(1);p.pause();resolve({episode:{id:1,position:0,duration:100},url:'/media/1',source_kind:'local'});
  await start;assert.equal(audio.plays,0);assert.equal(audio.paused,true);
});

test('queue reorder and undo stay local',async t=>{
  const {p}=rig(t);await p.start(1);await p.command('queue','POST',{episode_id:2});await p.command('queue','POST',{episode_id:3});
  await p.command('queue/order','PUT',{ids:[3,2],revision:p.revision});await p.next();
  assert.equal(p.current.id,3);await p.command('playback/undo','POST');assert.equal(p.current.id,1);
  assert.deepEqual(p.queue.map(e=>e.id),[3,2]);
});

test('normal playback defaults have no timer and no random fallback',async t=>{
  const {p,audio}=rig(t,{seconds:0,when_queue_empty:'stop'});await p.init();
  assert.equal(p.snapshot().timer.enabled,false);assert.equal(p.snapshot().when_queue_empty,'stop');
  await assert.rejects(p.play(),/Warteschlange/);assert.equal(audio.plays,0);
  await p.start(1);audio.finish();await settled();assert.equal(p.current.id,1);assert.equal(audio.paused,true);
  assert.equal(p.error,'');
});

test('sleep widget preserves current audio and ending sleep pauses playback',async t=>{
  const {p,audio}=rig(t,{seconds:0,when_queue_empty:'stop'});await p.start(1);audio.advance(25);
  const calls=audio.plays;await p.command('playback/sleep','POST');
  assert.equal(audio.plays,calls);assert.equal(audio.currentTime,25);assert.equal(p.snapshot().sleep_mode,true);
  assert.equal(p.seconds,900);await p.command('playback/normal','POST');
  assert.equal(audio.paused,true);assert.equal(audio.currentTime,25);assert.equal(p.seconds,0);assert.equal(p.whenQueueEmpty,'stop');
});

test('random resumes from zero while queue and explicit episode retain progress',async t=>{
  const {p,audio,request}=rig(t);p.request=async(path,...args)=>{
    const result=await request(path,...args);
    if(path.startsWith('browser/episodes/'))result.episode.position=45;
    return result;
  };
  await p.next();assert.equal(audio.currentTime,0);
  await p.command('queue','POST',{episode_id:2});await p.next();assert.equal(audio.currentTime,45);
  await p.command('episodes/play','POST',{episode_id:3});assert.equal(audio.currentTime,45);
});

test('empty unheard pool stops and failed sleep start restores normal options',async t=>{
  const {p,request,audio}=rig(t,{seconds:0,when_queue_empty:'stop'});
  p.request=(path,...args)=>path.startsWith('browser/candidates')?Promise.resolve([]):request(path,...args);
  await assert.rejects(p.command('playback/sleep','POST'),/passende Episode/);
  assert.equal(p.seconds,0);assert.equal(p.whenQueueEmpty,'stop');assert.equal(audio.plays,0);
});

test('sleep after normal EOF selects another episode instead of replaying the heard one',async t=>{
  const {p,audio}=rig(t,{seconds:0,when_queue_empty:'stop'});await p.start(1);
  audio.finish();await settled();assert.equal(p.current.id,1);
  await p.command('playback/sleep','POST');assert.equal(p.current.id,2);assert.equal(audio.currentTime,0);
});


test('UI pause/resume preserves remaining time and extensions; default API behavior still rearms',async t=>{
  const {p,audio}=rig(t);await p.start(1);
  audio.advance(30);await p.command('playback/toggle','POST',{timer:'preserve'});
  assert.equal(p.left,870);assert.equal(audio.paused,true);
  await p.command('timer/extend','POST',{minutes:5});assert.equal(p.left,1170);
  audio.advance(10);assert.equal(p.left,1170);
  await p.command('playback/toggle','POST',{timer:'preserve'});
  assert.equal(p.left,1170);audio.advance(5);assert.equal(p.left,1165);
  await p.command('playback/pause','POST');
  await p.command('playback/play','POST');assert.equal(p.left,900);
});

test('UI resume after browser source needs reloading retains time',async t=>{
  const {p,audio}=rig(t);await p.start(1);audio.advance(25);p.pause();
  p.prepared=false;
  await p.command('playback/play','POST',{timer:'preserve'});
  assert.equal(p.left,875);assert.equal(audio.paused,false);
});


test('UI resume after timer expiry starts a new period',async t=>{
  const {p,audio}=rig(t);await p.start(1);p.seconds=p.left=10;
  audio.advance(11);assert.equal(audio.paused,true);assert.equal(p.left,0);
  await p.command('playback/toggle','POST',{timer:'preserve'});
  assert.equal(audio.paused,false);assert.equal(p.left,10);
});
