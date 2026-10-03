// Retries a failed uplink write until Supabase takes it, the error turns out
// to be one retrying cannot fix, or the deadline passes.
//
// An uplink that fails to write used to be gone for good: ChirpStack had
// already acked it to the node, so nothing upstream would send it again. That
// is no longer true on the MQTT path - mqtt.ts acks manually, after the write,
// so an unacked message stays with the broker and is redelivered. The retry
// loop is still the first line of defence, because redelivery only happens
// after a reconnect and a frame that lands two seconds later is worth more
// than one that lands after the next restart.
//
// Re-running a write that actually landed is safe: writeEvent/writeStatus drop
// a frame digest they have already stored.

export interface RetryOptions {
  firstDelayMs: number;
  maxDelayMs: number;
  // Infinity never gives up. Only use that where the caller can apply
  // backpressure instead of buffering without limit - see ACK_RETRY.
  deadlineMs: number;
  // Errors that will fail identically however often they are retried. Thrown
  // straight back rather than slept on.
  isPermanent?: (err: unknown) => boolean;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export const UPLINK_RETRY: RetryOptions = {
  firstDelayMs: 2_000,
  maxDelayMs: 60_000,
  deadlineMs: 30 * 60_000,
};

// The budget used when the message will be redelivered if it is not acked.
//
// It never gives up, and that is safe here only because not acking is itself
// the brake: the broker stops sending once its in-flight window is full, so
// the backlog accumulates in mosquitto - which has persistence on and survives
// a restart - instead of in this process's heap. A free-tier Supabase project
// that auto-paused after a week of quiet takes longer to come back than the
// 30-minute UPLINK_RETRY deadline, and dropping a night of elephant alerts
// because a database was asleep is not an acceptable outcome. Waiting is.
//
// What must not be waited on forever is a message that can never succeed, so
// isPermanent is mandatory on this path: without it one malformed frame would
// stall every frame behind it.
export const ACK_RETRY: RetryOptions = {
  firstDelayMs: 2_000,
  maxDelayMs: 60_000,
  deadlineMs: Number.POSITIVE_INFINITY,
  isPermanent: isPermanentWriteError,
};

// Whether a failed write is the data's fault rather than the infrastructure's.
//
// Deliberately narrow. Only PostgreSQL class 22 (data exception) and class 23
// (integrity constraint violation) count - a value the column cannot hold, a
// foreign key to a node row that does not exist, a check that fails. Those
// describe a frame that will be rejected identically for ever.
//
// Everything else is treated as transient, including the ones that look
// permanent. A missing column (class 42) means a migration has not been
// applied yet, and an admin applying it is exactly the case where holding the
// data is better than discarding it. A paused project, an expired key and a
// network partition all clear on their own. The asymmetry is deliberate:
// retrying something unfixable costs a log line every minute, and discarding
// something fixable costs an elephant alert.
export function isPermanentWriteError(err: unknown): boolean {
  if (!err || typeof err !== 'object' || !('code' in err)) return false;
  const code = String((err as { code: unknown }).code ?? '');
  // PostgreSQL error codes are five characters of [0-9A-Z], not five digits -
  // 22P02 (invalid text representation) is the one most likely to arrive here.
  return /^(22|23)[0-9A-Z]{3}$/.test(code);
}

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
      if (opts.isPermanent?.(err)) {
        console.error(`Not retrying ${label} - the write cannot succeed:`, err);
        throw err;
      }
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
