import assert from 'node:assert/strict';
import { test } from 'node:test';

// sweep.ts imports supabase.ts, which builds a client at module load. The
// client makes no network call when it is constructed, but it does refuse to
// exist without a URL and a key, so give it throwaway ones before the import.
process.env.SUPABASE_URL ??= 'http://localhost:54321';
process.env.SUPABASE_SERVICE_ROLE_KEY ??= 'test-key';

const { sweepOfflineNodes, OFFLINE_AFTER_MS } = await import('./sweep.js');
type NodeUpdater = Parameters<typeof sweepOfflineNodes>[1];

interface Recorded {
  values?: { status: string };
  eq?: [string, string];
  lt?: [string, string];
}

// Records the filters the sweep applies, and hands back whatever rows the
// test says the update matched.
function recorder(rows: Array<{ id: string }>): { db: NodeUpdater; seen: Recorded } {
  const seen: Recorded = {};
  const db = {
    from: () => ({
      update: (values: { status: string }) => {
        seen.values = values;
        return {
          eq: (column: string, value: string) => {
            seen.eq = [column, value];
            return {
              lt: (lcolumn: string, lvalue: string) => {
                seen.lt = [lcolumn, lvalue];
                return { select: async () => ({ data: rows, error: null }) };
              },
            };
          },
        };
      },
    }),
  };
  return { db: db as unknown as NodeUpdater, seen };
}

// The regression this exists for. The sweep writes a status nobody asked it
// to write, so the only thing keeping it safe is what it refuses to touch:
// 'maintenance' is a person saying they are already dealing with it, and
// 'alert' is a detection nobody has cleared. Both outrank a timer.
test('the sweep only ever moves online nodes, and only stale ones', async () => {
  const { db, seen } = recorder([{ id: 'node-a' }]);
  const now = Date.parse('2026-10-03T12:00:00Z');
  const moved = await sweepOfflineNodes(now, db);

  assert.equal(moved, 1);
  assert.deepEqual(seen.values, { status: 'offline' });
  assert.deepEqual(seen.eq, ['status', 'online'], 'must not touch alert or maintenance');
  assert.equal(seen.lt?.[0], 'last_seen');
  assert.equal(
    seen.lt?.[1],
    new Date(now - OFFLINE_AFTER_MS).toISOString(),
    'the cutoff is one threshold back from now, not from anything else',
  );
});

// A node that has reported inside the window is simply not matched - there is
// no second code path that could mark a live node dead.
test('the sweep reports nothing when every node is fresh', async () => {
  const { db } = recorder([]);
  assert.equal(await sweepOfflineNodes(Date.now(), db), 0);
});

// A sweep that silently swallowed a database error would leave the dashboard
// green and say so in the logs, which is the failure it was written to stop.
test('a failed sweep throws rather than reporting success', async () => {
  const db = {
    from: () => ({
      update: () => ({
        eq: () => ({
          lt: () => ({ select: async () => ({ data: null, error: { message: 'boom' } }) }),
        }),
      }),
    }),
  } as unknown as NodeUpdater;
  // PostgREST hands back a plain object, not an Error, so assert on the value.
  await assert.rejects(
    () => sweepOfflineNodes(Date.now(), db),
    (err: unknown) => (err as { message: string }).message === 'boom',
  );
});
