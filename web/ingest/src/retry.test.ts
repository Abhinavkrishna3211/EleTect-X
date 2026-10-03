import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ACK_RETRY, isPermanentWriteError, withRetry, type RetryOptions } from './retry.js';

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

test('a permanent error is thrown back without being retried', async () => {
  const clock = fakeClock();
  let calls = 0;
  await assert.rejects(
    withRetry('w', async () => {
      calls++;
      throw { code: '23503', message: 'insert or update violates foreign key constraint' };
    }, { ...clock, isPermanent: isPermanentWriteError }),
    // PostgREST rejects with a plain object, not an Error.
    (err: unknown) => (err as { code: string }).code === '23503',
  );
  assert.equal(calls, 1, 'a frame the database will never accept must not hold the queue');
  assert.deepEqual(clock.slept, []);
});

// The asymmetry that keeps alerts alive: only the data's own fault is
// permanent. Everything that an admin or time could fix is waited on.
test('only data errors are permanent', () => {
  assert.equal(isPermanentWriteError({ code: '23503' }), true, 'foreign key violation');
  assert.equal(isPermanentWriteError({ code: '22P02' }), true, 'invalid text representation');
  assert.equal(isPermanentWriteError({ code: '42703' }), false, 'undefined column - a migration fixes it');
  assert.equal(isPermanentWriteError({ code: '57P03' }), false, 'database starting up');
  assert.equal(isPermanentWriteError(new Error('fetch failed')), false, 'network');
  assert.equal(isPermanentWriteError(undefined), false);
});

// ACK_RETRY never gives up on a transient failure, because not acking is the
// backpressure: the broker holds the frame rather than this process dropping
// it. A free-tier Supabase project asleep for longer than half an hour must
// not cost a night of alerts.
test('the ack budget outlasts the old 30-minute deadline', async () => {
  let t = 0;
  let calls = 0;
  const out = await withRetry('w', async () => {
    calls++;
    if (t < 6 * 60 * 60_000) throw new Error('fetch failed');
    return 'ok';
  }, { ...ACK_RETRY, now: () => t, sleep: async (ms) => { t += ms; } });
  assert.equal(out, 'ok');
  assert.ok(calls > 60, `gave up early after ${calls} attempts`);
});
