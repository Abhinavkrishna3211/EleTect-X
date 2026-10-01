// Retries a failed uplink write until Supabase takes it or the deadline passes.
//
// An uplink that fails to write is otherwise gone for good: ChirpStack has
// already acked it to the node, so nothing upstream will send it again. The
// usual cause is Supabase being briefly unreachable (a free-tier project that
// paused, a network blip at the gateway site, a migration not yet applied), and
// those all clear on their own or with one fix by an admin - so keep trying for
// long enough to cover that, then give up loudly rather than queue forever.
// Re-running a write that actually landed is safe: writeEvent/writeStatus drop
// a seq they have already stored.

export interface RetryOptions {
  firstDelayMs: number;
  maxDelayMs: number;
  deadlineMs: number;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export const UPLINK_RETRY: RetryOptions = {
  firstDelayMs: 2_000,
  maxDelayMs: 60_000,
  deadlineMs: 30 * 60_000,
};

const defaultSleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export async function withRetry<T>(
  label: string,
  fn: () => Promise<T>,
  opts: RetryOptions = UPLINK_RETRY,
): Promise<T> {
  const sleep = opts.sleep ?? defaultSleep;
  const now = opts.now ?? Date.now;
  const giveUpAt = now() + opts.deadlineMs;
  let delay = opts.firstDelayMs;
  for (let attempt = 1; ; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (now() + delay > giveUpAt) {
        console.error(`Giving up on ${label} after ${attempt} attempts:`, err);
        throw err;
      }
      console.warn(`${label} failed (attempt ${attempt}), retrying in ${delay / 1000}s:`, errorText(err));
      await sleep(delay);
      delay = Math.min(delay * 2, opts.maxDelayMs);
    }
  }
}

function errorText(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (err && typeof err === 'object' && 'message' in err) return String((err as { message: unknown }).message);
  return String(err);
}
