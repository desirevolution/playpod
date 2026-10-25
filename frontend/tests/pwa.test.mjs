import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../public/sw.js',import.meta.url),'utf8');
function worker(offline=false,redirect=false){
  const handlers={},cached=new Map();
  const cache={put:async(path,response)=>cached.set(path,response),};
  const caches={open:async()=>cache,keys:async()=>[],delete:async()=>true,match:async(path)=>cached.get(typeof path==='string'?path:new URL(path.url).pathname)};
  const self={location:{origin:'https://playpod.test'},clients:{claim:async()=>{}},addEventListener:(name,fn)=>handlers[name]=fn,skipWaiting:()=>assert.fail('must never interrupt active playback')};
  const fetch=async(input)=>{
    if(offline)throw new Error('offline');
    const path=typeof input==='string'?input:new URL(input.url).pathname;
    const r=new Response(redirect?'Login':path==='/offline.html'?'<main data-playpod-offline>Keine Verbindung</main>':'icon');
    Object.defineProperty(r,'url',{value:redirect?'https://login.test/':'https://playpod.test'+path});
    Object.defineProperty(r,'redirected',{value:redirect});return r;
  };
  vm.runInNewContext(source,{self,caches,fetch,URL,Response});
  return {handlers,cached};
}
async function install(w){let task;w.handlers.install({waitUntil:p=>task=p});await task;}

test('PWA caches only static offline notice/icons and never a login redirect',async()=>{
  const w=worker();await install(w);
  assert.deepEqual([...w.cached.keys()].sort(),['/icons/icon-192.png','/icons/icon-512.png','/offline.html']);
  const redirected=worker(false,true);await install(redirected);assert.equal(redirected.cached.size,0);
  assert.equal(w.handlers.message,undefined);
});

test('service worker leaves audio and API requests entirely untouched',()=>{
  const w=worker();
  for(const path of ['/api/v1/state','/api/v1/browser/episodes/1/stream','/downloads/id','/media/1'])
    w.handlers.fetch({request:{url:'https://playpod.test'+path,mode:'cors',method:'GET'},respondWith:()=>assert.fail('must not intercept media/API')});
});

test('offline navigation returns the explicit offline notice',async()=>{
  const w=worker(true);w.cached.set('/offline.html',new Response('Keine Verbindung zu PlayPod'));
  let task;w.handlers.fetch({request:{url:'https://playpod.test/',mode:'navigate',method:'GET'},respondWith:p=>task=p});
  assert.equal(await(await task).text(),'Keine Verbindung zu PlayPod');
});
