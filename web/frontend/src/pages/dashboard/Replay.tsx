import { useEffect, useMemo, useRef, useState } from 'react'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LiveMap } from '@/components/dashboard/LiveMap'
import { geoPoints, toLatLng, type EventRow, type NodeRow } from '@/lib/dashboard'
import { herdAt, incidentPath, istHM, latestActivation, latestCluster, ms } from '@/lib/incident'

// Wall-clock advance rate of the auto-play head: replay one incident over ~14 s.
const PLAY_MS = 14_000
const TICK_MS = 90
// herdAt() already yields a continuous position, so the marker only needs enough
// transition to damp the 90 ms stepping of the play head.
const HERD_MS = 200

function dotColor(e: EventRow): string {
  if (e.corridor?.role === 'deter') return '#e25b4a'
  if (e.corridor?.role === 'escort') return '#5fa97c'
  if (e.priority === 'high') return '#e25b4a'
  return '#e2a13c'
}

function logText(e: EventRow): string {
  if (e.corridor?.note) {
    const who = e.node_id ? `${e.node_id} · ` : ''
    return `${who}${e.corridor.note}`
  }
  const species = e.species ? e.species[0].toUpperCase() + e.species.slice(1) : 'Detection'
  const bits = [e.node_id, species, e.action, e.outcome].filter(Boolean)
  return bits.join(' · ')
}

export function Replay() {
  const { rows: nodeRows } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const { rows: eventRows, loading } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 300,
  })

  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])
  const points = useMemo(() => geoPoints(nodes), [nodes])

  // The incident to replay: the latest coordinated activation, else the latest
  // time-contiguous cluster of detections. Ascending by time either way.
  const incident = useMemo(() => {
    const events = [...eventRows.values()]
    const activation = latestActivation(events)
    if (activation.length >= 2) return activation
    return latestCluster(events)
  }, [eventRows])

  const window = useMemo(() => {
    if (incident.length === 0) return null
    return { start: ms(incident[0].ts), end: ms(incident[incident.length - 1].ts) }
  }, [incident])

  const path = useMemo(() => incidentPath(incident, points), [incident, points])

  const [replayT, setReplayT] = useState(0) // 0..100
  const [playing, setPlaying] = useState(false)
  const rafStart = useRef<number>(0)

  // Reset to the start whenever a different incident loads (render-phase reset,
  // per React docs — avoids a cascading setState-in-effect).
  const winKey = window ? `${window.start}-${window.end}` : 'none'
  const [prevWin, setPrevWin] = useState(winKey)
  if (winKey !== prevWin) {
    setPrevWin(winKey)
    setReplayT(0)
    setPlaying(false)
  }

  // Auto-play head advances replayT on its own; pauses at the end.
  useEffect(() => {
    if (!playing) return
    rafStart.current = performance.now() - (replayT / 100) * PLAY_MS
    const id = setInterval(() => {
      const elapsed = performance.now() - rafStart.current
      const next = Math.min(100, (elapsed / PLAY_MS) * 100)
      setReplayT(next)
      if (next >= 100) setPlaying(false)
    }, TICK_MS)
    return () => clearInterval(id)
    // replayT intentionally omitted: it is the output being driven here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing])

  const tMs = window ? window.start + (replayT / 100) * (window.end - window.start) : 0

  // Nodes that have already fired at the current play head — they pulse on the map.
  const firedByT = useMemo(
    () => new Set(incident.filter((e) => ms(e.ts) <= tMs && e.node_id).map((e) => e.node_id as string)),
    [incident, tMs],
  )

  const herdPoint = useMemo(() => herdAt(incident, points, tMs), [incident, points, tMs])
  const corridor = useMemo(() => path.map(toLatLng), [path])

  const speciesLabel = incident.find((e) => e.species)?.species?.toUpperCase() ?? 'DETECTION'
  const subtitle = window
    ? `${speciesLabel} INCURSION · ${istHM(window.start)}–${istHM(window.end)} IST`
    : 'NO INCIDENT IN RANGE'

  const clock = window ? istHM(tMs) : '--:--'

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Incident replay</h1>
        <div className="border-brand-fg/10 text-brand-fg/40 grid h-64 place-items-center rounded-2xl border bg-[#0B0D0B] font-mono text-[12px]">
          Loading incident…
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="m-0 mb-1 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Incident replay</h1>
        <p className="text-brand-fg/50 m-0 font-mono text-[13px] font-medium">{subtitle}</p>
      </div>

      <div className="h-[clamp(300px,44vw,440px)]">
        <LiveMap
          nodes={nodes}
          activeNodeIds={firedByT}
          herd={
            window && herdPoint
              ? { lat: herdPoint.top, lng: herdPoint.left, count: Math.max(1, firedByT.size), label: 'HERD' }
              : null
          }
          herdTransitionMs={HERD_MS}
          corridor={corridor}
          fit="bounds"
          label="REPLAY"
        />
      </div>

      <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-5">
        <div className="mb-1.5 flex flex-wrap items-center gap-4">
          <span className="text-brand-gold min-w-22 font-serif text-[30px] leading-none">{clock}</span>
          <input
            type="range"
            min={0}
            max={100}
            step={0.1}
            value={replayT}
            onChange={(e) => {
              setPlaying(false)
              setReplayT(Number(e.target.value))
            }}
            aria-label="Replay position"
            disabled={!window}
            className="accent-brand-gold h-8 min-w-50 flex-1 cursor-pointer disabled:cursor-not-allowed"
          />
          <button
            onClick={() => setPlaying((p) => !p)}
            disabled={!window}
            className="bg-brand-gold hover:bg-brand-gold-hover text-brand-bg min-h-11 rounded-full px-5 py-2.5 font-sans text-[13px] font-semibold transition-colors disabled:opacity-40"
          >
            {playing ? 'Pause' : replayT >= 100 ? 'Replay' : 'Play'}
          </button>
        </div>
        {window && (
          <div className="text-brand-fg/40 flex justify-between font-mono text-[11px] font-medium">
            <span>{istHM(window.start)}</span>
            <span>{istHM(window.end)}</span>
          </div>
        )}
      </div>

      <div className="border-brand-fg/10 flex flex-col gap-2.5 rounded-2xl border bg-[#0B0D0B] p-5">
        {incident.length === 0 ? (
          <p className="text-brand-fg/40 m-0 py-4 text-center font-mono text-[12px]">No detections to replay</p>
        ) : (
          incident.map((e) => {
            const past = ms(e.ts) <= tMs
            return (
              <div
                key={e.id}
                className="flex items-start gap-3 transition-opacity duration-300"
                style={{ opacity: past ? 1 : 0.32 }}
              >
                <span className="text-brand-gold mt-px min-w-11 font-mono text-[12px] font-semibold">{istHM(e.ts)}</span>
                <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: dotColor(e) }} />
                <span className="text-brand-fg/85 font-sans text-[13.5px] leading-snug">{logText(e)}</span>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
