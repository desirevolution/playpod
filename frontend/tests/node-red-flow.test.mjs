import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const flow = JSON.parse(readFileSync(new URL('../../examples/node-red-playpod-v1.json', import.meta.url), 'utf8'));
const definition = flow.find(n => n.type === 'function');
const run = new Function('msg', 'node', definition.func);

test('Node-RED remote buttons produce the v1 methods, paths and JSON bodies', () => {
  const expected = {
    toggle:['POST','playback/toggle',{timer:'default',when_queue_empty:'default'}],
    play:['POST','playback/play',{timer:'default',when_queue_empty:'default'}], pause:['POST','playback/pause',{}],
    next:['POST','playback/next',{timer:'default',when_queue_empty:'default'}], forward:['POST','seek',{offset_seconds:30}],
    rewind:['POST','seek',{offset_seconds:-30}], volume_up:['POST','volume/adjust',{delta:5}],
    volume_down:['POST','volume/adjust',{delta:-5}], mode:['POST','mode/toggle',{}],
    extend:['POST','timer/extend',{minutes:5}], refresh:['POST','feeds/refresh',{}], state:['GET','state',undefined],
  };
  for (const [topic,[method,path,body]] of Object.entries(expected)) {
    const msg = run({topic,payload:'stale input'}, {error:assert.fail});
    assert.equal(msg.method, method);
    assert.equal(msg.url, 'http://PLAYPOD-HOST:9393/api/v1/'+path);
    assert.equal(msg.headers['Content-Type'],'application/json');
    assert.deepEqual(msg.payload,body);
  }
});

test('Node-RED example wires exist and unknown commands do not reach HTTP', () => {
  const ids = new Set(flow.map(n=>n.id));
  for (const n of flow) for (const output of n.wires??[]) for (const id of output) assert.ok(ids.has(id));
  const errors=[];
  for (const topic of ['unknown','__proto__','constructor'])
    assert.equal(run({topic}, {error:(...args)=>errors.push(args)}), null);
  assert.equal(errors.length,3);
});
