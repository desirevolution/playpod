import test from 'node:test';
import assert from 'node:assert/strict';
import { managementLink, managementTarget, groupActivity } from '../src/activity.ts';

test('activity links target exact episodes or the initial feed; deleted entries have no link', () => {
  assert.equal(managementLink({episode_id: 77, feed_id: 4}), '#management/episodes/77');
  assert.equal(managementLink({kind: 'feed_added', episode_id: null, feed_id: 4}), '#management/feeds/4');
  assert.equal(managementLink({kind: 'completed', episode_id: null, feed_id: 4}), null);
  assert.equal(managementLink({episode_id: null, feed_id: null}), null);
  assert.deepEqual(managementTarget('#management/episodes/77'), {kind: 'episodes', id: 77});
  assert.deepEqual(managementTarget('#management/feeds/4'), {kind: 'feeds', id: 4});
  for (const hash of ['#management/episodes/-1', '#management/episodes/0', '#management/episodes/1x', '#management/episodes/9007199254740993']) assert.equal(managementTarget(hash), null);
});

test('activity is grouped by local calendar day without losing event order', () => {
  const events = [new Date(2026, 9, 25, 10), new Date(2026, 9, 25, 8), new Date(2026, 9, 24, 23)].map((date,id) => ({id, created: date.getTime()/1000}));
  const groups = groupActivity(events);
  assert.deepEqual(groups.map(group => group.items.map(event => event.id)), [[0,1],[2]]);
  assert.equal(groups[0].day.getHours(), 0);
});
