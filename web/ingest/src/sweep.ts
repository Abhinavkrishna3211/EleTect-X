// Marks nodes offline when they stop reporting.
//
// Nothing did this before. touchNode() sets a node 'online' on every uplink,
// and the only other writer is staff, so a node whose battery died, whose
// antenna came loose, or that a tree fell on stayed green on the dashboard
// indefinitely - the one failure the fleet view exists to make visible was the
// one it could not show. Silence is not an event, so no uplink-driven code
// path can ever notice it; something has to look at the clock.
//
// It runs in this process rather than as a pg_cron job because the bridge is
// already the thing that owns `status`, it already has the service-role key,
// and adding a second writer on a different schedule would mean two components
// racing over one column. The cost is that liveness is only swept while the
// bridge is up - but if the bridge is down nothing is being ingested either,
// and every node is about to be swept offline anyway, so the failure mode is
// honest rather than silently wrong.
//
// Deliberately one-directional. It only moves 'online' to 'offline'; the
// reverse is touchNode()'s job, on evidence of an actual uplink. It never
// touches 'maintenance', which is a staff member saying "I know, I am working
// on it", or 'alert', which is a detection nobody has cleared - overwriting
// either would destroy a human decision to report a machine one.

import { supabase } from './supabase.js';

// Six missed heartbeats. The node sends status every LORA_STATUS_INTERVAL_MS
// (10 minutes, device/mcu/src/config.h), so this tolerates a handful of lost
// uplinks - normal over LoRa - before calling a node dead. It is the same
// hour that web/frontend's isStale() uses, on purpose: a node the dashboard
// greys out as stale and a node the database calls offline should never be
// two different sets.
export const OFFLINE_AFTER_MS = Number(process.env.NODE_OFFLINE_AFTER_MS ?? 60 * 60 * 1000);

// A third of the threshold, so a node is called offline within ~20 minutes of
// crossing it. Frequent enough to be useful, far too infrequent to matter as
// load: one indexed update against a table with a handful of rows.
export const SWEEP_INTERVAL_MS = Number(process.env.NODE_SWEEP_INTERVAL_MS ?? OFFLINE_AFTER_MS / 3);

// The slice of the Supabase client this uses. Narrow on purpose: the test
// substitutes a recorder that captures the filters, because the guarantee
// worth pinning is not that the update runs but that it is *confined* -
// drop the status filter and the next sweep quietly erases every
// 'maintenance' flag an engineer set before walking into the forest.
export interface NodeUpdater {
  from(table: 'nodes'): {
    update(values: { status: string }): {
      eq(column: string, value: string): {
        lt(column: string, value: string): {
          select(columns: string): Promise<{ data: Array<{ id: string }> | null; error: unknown }>;
        };
      };
    };
  };
}

// Returns how many nodes were moved to 'offline'. Exported for tests and for
// a one-shot run; sweepNodesForever() is what index.ts starts.
export async function sweepOfflineNodes(
  now = Date.now(),
  db: NodeUpdater = supabase as unknown as NodeUpdater,
): Promise<number> {
  const cutoff = new Date(now - OFFLINE_AFTER_MS).toISOString();
  const { data, error } = await db
    .from('nodes')
    .update({ status: 'offline' })
    .eq('status', 'online')
    .lt('last_seen', cutoff)
    .select('id');
  if (error) throw error;

  const ids = (data ?? []).map((n) => n.id as string);
  if (ids.length) {
    console.warn(`Marked ${ids.length} node(s) offline after ${OFFLINE_AFTER_MS / 60000} min silent: ${ids.join(', ')}`);
  }
  return ids.length;
}

// A node that has never reported has last_seen null, which `lt` does not
// match, so it stays at whatever status it was seeded with rather than being
// declared dead before it has been switched on.
export function sweepNodesForever(): NodeJS.Timeout {
  const tick = () => {
    sweepOfflineNodes().catch((err) => {
      // Never fatal. A failed sweep means the dashboard is stale for another
      // interval; killing the bridge over it would stop ingest as well, which
      // is strictly worse.
      console.error('Node offline sweep failed:', err);
    });
  };
  tick();
  const timer = setInterval(tick, SWEEP_INTERVAL_MS);
  // Do not hold the event loop open on the sweep alone.
  timer.unref?.();
  return timer;
}
