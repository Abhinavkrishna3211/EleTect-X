import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '@/lib/auth'
import { criticalQueue, relativeTime, speciesIcon, speciesLabel, type EventRow } from '@/lib/dashboard'
import { supabase } from '@/lib/supabase'

// How far back to look for criticals nobody has taken yet.
//
// The Overview feed holds the 20 newest events of any kind, which on a busy
// night is about an hour. An unacknowledged critical must not be allowed to
// scroll out of the window underneath a run of foxes - an officer opening the
// dashboard at dawn has to see the 2am one that nobody answered. So the queue
// runs its own query against the partial index migration 0006 added for it
// (priority = 'critical' and acked_at is null) rather than filtering what the
// feed happens to be holding.
const BACKLOG_LIMIT = 20

// Prefer whichever copy of an event is acknowledged.
//
// The same row can arrive twice - once in the realtime window, once in the
// backlog query, once more when we re-read it after pressing the button - and
// the copies can disagree about acked_at while a realtime UPDATE is in flight.
// An acknowledgement is monotonic: acknowledge_event() only fires where
// `acked_at is null`, and nothing ever clears it. So "the acked one wins" is
// always the newer truth, and it resolves the merge without comparing clocks.
function preferAcked(have: EventRow | undefined, next: EventRow): EventRow {
  if (!have) return next
  return have.acked_at != null ? have : next
}

interface CriticalQueueProps {
  events: EventRow[]
  nodeNames?: Map<string, string>
  onSelect?: (nodeId: string) => void
}

export function CriticalQueue({ events, nodeNames, onSelect }: CriticalQueueProps) {
  const { user } = useAuth()
  // Rows this component fetched itself: the backlog at mount, plus any row we
  // re-read after acknowledging it.
  const [fetched, setFetched] = useState<Map<number, EventRow>>(new Map())
  const [names, setNames] = useState<Map<string, string>>(new Map())
  const [takingId, setTakingId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const absorb = useCallback((row: EventRow) => {
    setFetched((prev) => new Map(prev).set(row.id, row))
  }, [])

  useEffect(() => {
    let active = true
    supabase
      .from('events')
      .select('*')
      .eq('priority', 'critical')
      .is('acked_at', null)
      .order('ts', { ascending: false })
      .limit(BACKLOG_LIMIT)
      .then(({ data }) => {
        if (!active || !data) return
        setFetched((prev) => {
          const next = new Map(prev)
          for (const row of data as EventRow[]) next.set(row.id, preferAcked(next.get(row.id), row))
          return next
        })
      })
    return () => {
      active = false
    }
  }, [])

  const { open, taken } = useMemo(() => {
    const merged = new Map<number, EventRow>()
    for (const e of [...events, ...fetched.values()]) {
      merged.set(e.id, preferAcked(merged.get(e.id), e))
    }
    return criticalQueue([...merged.values()])
  }, [events, fetched])

  // Who took it. acked_by is a uuid, which tells an officer nothing; staff can
  // read profiles (p_staff_read), so resolve the handful of ids on screen.
  const ackedIds = useMemo(
    () => [...new Set(taken.map((e) => e.acked_by).filter((id): id is string => id != null))],
    [taken],
  )
  const missingIds = useMemo(
    () => ackedIds.filter((id) => id !== user?.id && !names.has(id)),
    [ackedIds, names, user],
  )

  useEffect(() => {
    if (missingIds.length === 0) return
    let active = true
    supabase
      .from('profiles')
      .select('id, full_name')
      .in('id', missingIds)
      .then(({ data }) => {
        if (!active || !data) return
        setNames((prev) => {
          const next = new Map(prev)
          for (const p of data as { id: string; full_name: string | null }[]) {
            next.set(p.id, p.full_name ?? 'An officer')
          }
          return next
        })
      })
    return () => {
      active = false
    }
  }, [missingIds])

  async function take(id: number) {
    setTakingId(id)
    setError(null)
    const { error: rpcError } = await supabase.rpc('acknowledge_event', { p_event_id: id })
    if (rpcError) {
      setError('Could not record that. Check your connection and try again.')
      setTakingId(null)
      return
    }
    // Re-read rather than assuming it is now ours. The first acknowledgement
    // wins server-side, so if another officer pressed it a moment earlier this
    // call changed nothing and the row carries their name - which is exactly
    // what this officer needs to see, and what an optimistic update would hide.
    const { data } = await supabase.from('events').select('*').eq('id', id).maybeSingle()
    if (data) absorb(data as EventRow)
    setTakingId(null)
  }

  // Nothing outstanding and nothing recently handled: render nothing. The
  // feed's header already says ALL CLEAR, and a permanent empty panel at the
  // top of the dashboard trains officers to skip the place the real one
  // appears.
  if (open.length === 0 && taken.length === 0) return null

  function whoTook(event: EventRow): string {
    if (!event.acked_by) return 'An officer'
    if (event.acked_by === user?.id) return 'You'
    return names.get(event.acked_by) ?? 'Another officer'
  }

  function describe(event: EventRow): string {
    const parts: string[] = []
    if (event.node_id) parts.push(nodeNames?.get(event.node_id) ?? event.node_id)
    parts.push(relativeTime(event.ts))
    return parts.join(' · ')
  }

  return (
    <section
      aria-label="Critical events needing a response"
      className="overflow-hidden rounded-2xl border"
      style={{ borderColor: 'rgba(226,91,74,0.45)', background: 'rgba(226,91,74,0.07)' }}
    >
      <div
        className="flex flex-wrap items-baseline justify-between gap-2 border-b px-4.5 py-3.5"
        style={{ borderColor: 'rgba(226,91,74,0.25)' }}
      >
        <h2 className="text-brand-red m-0 font-sans text-sm font-semibold">
          Deterrence failed · send someone
        </h2>
        <span className="text-brand-red font-mono text-[11px] font-semibold">
          {open.length > 0 ? `${open.length} AWAITING RESPONSE` : 'ALL TAKEN'}
        </span>
      </div>

      <p className="text-brand-fg/65 m-0 px-4.5 pt-3 font-sans text-[13px] leading-relaxed">
        The node ran its full escalation and the animal stayed. Say you are going so the rest of the
        team knows it is covered.
      </p>

      <div className="flex flex-col gap-2 px-4.5 py-3">
        {open.map((e) => (
          <div
            key={e.id}
            className="border-brand-fg/10 flex flex-wrap items-center gap-3 rounded-xl border bg-[#0B0D0B] px-3.5 py-3"
          >
            <span className="shrink-0 text-lg" aria-hidden="true">
              {speciesIcon(e.species)}
            </span>
            <button
              onClick={() => e.node_id && onSelect?.(e.node_id)}
              disabled={!e.node_id}
              className="min-w-40 flex-1 text-left disabled:cursor-default"
            >
              <span className="text-brand-red block font-sans text-[14px] font-semibold">
                {speciesLabel(e.species)} did not retreat
              </span>
              <span className="text-brand-fg/45 mt-0.5 block truncate font-mono text-[11.5px]">
                {describe(e)}
              </span>
            </button>
            <button
              onClick={() => take(e.id)}
              disabled={takingId != null}
              className="text-brand-red min-h-11 shrink-0 rounded-full border px-4.5 py-2.5 font-sans text-[13px] font-semibold transition-colors disabled:opacity-60"
              style={{ background: 'rgba(226,91,74,0.14)', borderColor: 'rgba(226,91,74,0.5)' }}
            >
              {takingId === e.id ? 'Recording…' : "I'm responding"}
            </button>
          </div>
        ))}

        {taken.map((e) => (
          <div
            key={e.id}
            className="border-brand-fg/8 flex flex-wrap items-center gap-3 rounded-xl border px-3.5 py-2.5"
          >
            <span className="shrink-0 text-base opacity-60" aria-hidden="true">
              {speciesIcon(e.species)}
            </span>
            <span className="min-w-40 flex-1">
              <span className="text-brand-fg/70 block font-sans text-[13px] font-medium">
                {speciesLabel(e.species)} · {describe(e)}
              </span>
            </span>
            <span className="text-brand-green shrink-0 font-mono text-[11.5px] font-semibold">
              {whoTook(e)} responding · {relativeTime(e.acked_at)}
            </span>
          </div>
        ))}
      </div>

      {error && (
        <p className="text-brand-red m-0 px-4.5 pb-3.5 font-mono text-[11.5px]" role="alert">
          {error}
        </p>
      )}
    </section>
  )
}
