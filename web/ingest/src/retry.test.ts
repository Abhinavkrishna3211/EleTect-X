import { test } from 'node:test';
import assert from 'node:assert/strict';
import { withRetry, type RetryOptions } from './retry.js';

// A fake clock: sleep advances time instead of waiting.
function fakeClock(): RetryOptions & { slept: number[] } {
  let t = 0;
  const slept: number[] = [];
  return {
    firstDelayMs: 1_000,
    maxDelayMs: 4_000,
    deadlineMs: 20_000,
    now: () => t,
    sleep: async (ms) => {
      slept.push(ms);
      t += ms;
    },
    slept,
  };
}

test('withRetry returns as soon as the write succeeds', async () => {
  const clock = fakeClock();
  let calls = 0;
  const out = await withRetry('w', async () => {
    calls++;
    if (calls < 3) throw new Error('fetch failed');
    return 'ok';
  }, clock);
  assert.equal(out, 'ok');
  assert.equal(calls, 3);
  assert.deepEqual(clock.slept, [1_000, 2_000]);
});

test('withRetry backs off up to the cap, then gives up at the deadline', async () => {
  const clock = fakeClock();
  let calls = 0;
  await assert.rejects(
    withRetry('w', async () => {
      calls++;
      throw new Error('fetch failed');
    }, clock),
    /fetch failed/,
  );
  // 1 + 2 + 4 + 4 + 4 + 4 = 19 s; the next 4 s wait would pass the 20 s deadline.
  assert.deepEqual(clock.slept, [1_000, 2_000, 4_000, 4_000, 4_000, 4_000]);
  assert.equal(calls, 7);
});
