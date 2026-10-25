import { test } from "node:test";
import assert from "node:assert/strict";
import { DisplayClock } from "../src/display-clock.ts";
const snapshot = (overrides = {}) => ({
  state: "play",
  elapsed: 10,
  duration: 100,
  current: { id: 1 },
  timer: { enabled: true, minutes: 15, remaining: 900 },
  ...overrides,
});
test("counts playback and sleep timer between polls", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  assert.deepEqual(c.read(1000), { elapsed: 11, remaining: 899 });
  assert.deepEqual(c.read(2000), { elapsed: 12, remaining: 898 });
});
test("sampling jitter does not reverse a displayed second", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  c.sync(
    snapshot({
      elapsed: 11,
      timer: { enabled: true, minutes: 15, remaining: 898 },
    }),
    2000,
  );
  assert.deepEqual(c.read(3000), { elapsed: 13, remaining: 897 });
});
test("pause freezes both displays and resume reanchors", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  c.sync(snapshot({ state: "pause", elapsed: 11 }), 1000);
  assert.deepEqual(c.read(9000), { elapsed: 11, remaining: 900 });
  c.sync(snapshot({ elapsed: 11 }), 10000);
  assert.deepEqual(c.read(11000), { elapsed: 12, remaining: 899 });
});
test("seek commands including short seeks reanchor immediately", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  c.sync(snapshot({ elapsed: 10 }), 1000, true);
  assert.equal(c.read(1000).elapsed, 10);
  c.sync(snapshot({ elapsed: 60 }), 2000);
  assert.equal(c.read(2000).elapsed, 60);
});
test("episode changes reset elapsed while preserving timer", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  c.sync(snapshot({ current: { id: 2 }, elapsed: 0 }), 1000);
  assert.equal(c.read(2000).elapsed, 1);
});
test("timer changes and disabled timer apply immediately", () => {
  const c = new DisplayClock();
  c.sync(snapshot(), 0);
  c.sync(
    snapshot({ timer: { enabled: true, minutes: 5, remaining: 300 } }),
    1000,
  );
  assert.equal(c.read(2000).remaining, 299);
  c.sync(
    snapshot({ timer: { enabled: false, minutes: 0, remaining: 0 } }),
    3000,
  );
  assert.equal(c.read(4000).remaining, 0);
});
test("clamps episode duration, timer zero and stale connections", () => {
  const c = new DisplayClock();
  c.sync(
    snapshot({
      elapsed: 99,
      timer: { enabled: true, minutes: 15, remaining: 1 },
    }),
    0,
  );
  assert.deepEqual(c.read(2000), { elapsed: 100, remaining: 0 });
  const d = new DisplayClock();
  d.sync(snapshot(), 0);
  assert.deepEqual(d.read(60000), { elapsed: 15, remaining: 895 });
  d.sync(snapshot({ elapsed: 30 }), 60000);
  assert.equal(d.read(60000).elapsed, 30);
});

test("announcement does not count episode progress or a new sleep timer", () => {
  const c = new DisplayClock();
  c.sync(
    snapshot({
      phase: "announcement",
      timer: { enabled: true, minutes: 15, remaining: 900, run_active: false },
    }),
    0,
  );
  assert.deepEqual(c.read(2000), { elapsed: 10, remaining: 900 });
});
test("existing sleep deadline counts during announcement", () => {
  const c = new DisplayClock();
  c.sync(
    snapshot({
      phase: "announcement",
      timer: { enabled: true, minutes: 15, remaining: 900, run_active: true },
    }),
    0,
  );
  assert.deepEqual(c.read(2000), { elapsed: 10, remaining: 898 });
});
test("episode start reanchors display after announcement", () => {
  const c = new DisplayClock();
  c.sync(
    snapshot({
      phase: "announcement",
      elapsed: 0,
      timer: { enabled: true, minutes: 15, remaining: 900, run_active: false },
    }),
    0,
  );
  c.sync(
    snapshot({
      phase: "episode",
      elapsed: 0,
      timer: { enabled: true, minutes: 15, remaining: 900, run_active: true },
    }),
    2000,
  );
  assert.deepEqual(c.read(3000), { elapsed: 1, remaining: 899 });
});

test('mode speech freezes episode time and an existing timer, then resumes', () => {
  const clock = new DisplayClock();
  clock.sync(snapshot({phase:'announcement',timer:{enabled:true,minutes:15,remaining:800,run_active:true,suspended:true}}), 0);
  assert.equal(clock.read(3000).elapsed, 10);
  assert.equal(clock.read(3000).remaining, 800);
  clock.sync(snapshot({phase:'episode',timer:{enabled:true,minutes:15,remaining:800,run_active:true,suspended:false}}), 3000);
  assert.equal(clock.read(4000).remaining, 799);
  assert.equal(clock.read(4000).elapsed, 11);
});

test('resume response resets timer to the full period while episode position continues', () => {
  const clock = new DisplayClock();
  clock.sync(snapshot({state:'pause',elapsed:123,timer:{enabled:true,minutes:15,remaining:120}}), 0);
  assert.equal(clock.read(5000).remaining,120);
  clock.sync(snapshot({state:'play',elapsed:123,duration:1200,timer:{enabled:true,minutes:15,remaining:900}}), 5000, true);
  assert.deepEqual(clock.read(6000), {elapsed:124,remaining:899});
});
