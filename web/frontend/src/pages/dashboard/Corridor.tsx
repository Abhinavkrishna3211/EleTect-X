import { useEffect, useMemo, useState } from 'react'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LiveMap } from '@/components/dashboard/LiveMap'
import { corridorRoleDisplay, geoPoints, toLatLng, type EventRow, type NodeRow } from '@/lib/dashboard'
import { incidentPath, istHM } from '@/lib/incident'

// Time each node holds the herd before the handoff advances (map + card in sync).
const STEP_MS = 1700
// The herd hops node-to-node here, so it needs a full ease to read as movement.
const HERD_MS = 1100

interface Activation {
  id: string
  steps: EventRow[] // ordered by corridor.seq
  start: string
}

function buildActivations(events: EventRow[]): Activation[] {
  const groups = new Map<string, EventRow[]>()
  for (const e of events) {
    if (!e.corridor) continue
    const arr = groups.get(e.corridor.activation) ?? []
    arr.push(e)
    groups.set(e.corridor.activation, arr)
  }
  const out: Activation[] = []
  for (const [id, arr] of groups) {
    const steps = arr.slice().sort((a, b) => (a.corridor!.seq - b.corridor!.seq) || a.ts.localeCompare(b.ts))
    out.push({ id, steps, start: steps[0]?.ts ?? '' })
  }
  // newest activation first
  return out.sort((a, b) => b.start.localeCompare(a.start))
}

export function Corridor() {
  const { rows: nodeRows } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const { rows: eventRows, loading } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 300,
  })

  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])
  const points = useMemo(() => geoPoints(nodes), [nodes])
  const activations = useMemo(() => buildActivations([...eventRows.values()]), [eventRows])

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = useMemo(
    () => activations.find((a) => a.id === selectedId) ?? activations[0] ?? null,
    [activations, selectedId],
  )
  const steps = useMemo(() => selected?.steps ?? [], [selected])

  // Handoff head: advances through the sequence and loops, driving both the
  // pulsing node on the map and the highlighted step card. Reset to the first
  // step whenever the selected activation changes (render-phase, per React docs).
  const [step, setStep] = useState(0)
  const [prevSel, setPrevSel] = useState(selected?.id)
  if (selected?.id !== prevSel) {
    setPrevSel(selected?.id)
    setStep(0)
  }
  useEffect(() => {
    if (steps.length < 2) return
    const id = setInterval(() => setStep((s) => (s + 1) % steps.length), STEP_MS)
    return () => clearInterval(id)
  }, [steps.length])

  const activeNodeId = steps[step]?.node_id ?? null
  const path = useMemo(() => incidentPath(steps, points), [steps, points])
  const corridor = useMemo(() => path.map(toLatLng), [path])

  const activeNodeIds = useMemo(() => new Set(activeNodeId ? [activeNodeId] : []), [activeNodeId])
  const herdPoint = activeNodeId ? points.get(activeNodeId) ?? null : null

  if (loading) {
    return (
      <div className="flex flex-col gap-4">
        <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Network intelligence</h1>
        <div className="border-brand-fg/10 text-brand-fg/40 grid h-64 place-items-center rounded-2xl border bg-[#0B0D0B] font-mono text-[12px]">
          Loading corridor…
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="m-0 mb-1 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Network intelligence</h1>
          <p className="text-brand-fg/60 m-0 max-w-[70ch] font-sans text-sm leading-relaxed">
            Nodes coordinate to open a safe corridor back to the forest, steering the herd away from villages, never
            trapping or panicking it.
          </p>
        </div>
        {activations.length > 1 && (
          <div className="flex flex-wrap gap-1.5">
            {activations.map((a) => {
              const on = a.id === selected?.id
              return (
                <button
                  key={a.id}
                  onClick={() => setSelectedId(a.id)}
                  className={`rounded-full border px-3 py-1.5 font-mono text-[11px] font-semibold transition-colors ${
                    on ? 'border-brand-gold text-brand-gold bg-[rgba(226,161,60,0.1)]' : 'border-brand-fg/15 text-brand-fg/55 hover:text-brand-fg'
                  }`}
                >
                  {a.id} · {a.start ? istHM(a.start) : '—'}
                </button>
              )
            })}
          </div>
        )}
      </div>

      <div className="h-[clamp(300px,44vw,440px)]">
        <LiveMap
          nodes={nodes}
          activeNodeIds={activeNodeIds}
          herd={herdPoint ? { lat: herdPoint.top, lng: herdPoint.left, count: steps.length, label: 'HERD → FOREST' } : null}
          herdTransitionMs={HERD_MS}
          corridor={corridor}
          fit="bounds"
          label="SAFE-HERDING CORRIDOR"
        />
      </div>

      {steps.length === 0 ? (
        <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-8 text-center">
          <p className="text-brand-fg/50 m-0 font-sans text-sm">No coordinated corridor activations recorded yet.</p>
        </div>
      ) : (
        <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
          {steps.map((e, i) => {
            const role = e.corridor ? corridorRoleDisplay(e.corridor.role) : null
            const on = i === step
            return (
              <div
                key={e.id}
                className="rounded-2xl border p-4.5 transition-all duration-300"
                style={{
                  background: 'linear-gradient(160deg, rgba(15,29,20,0.5), rgba(11,13,11,0.2))',
                  borderColor: on ? 'rgba(226,161,60,0.5)' : 'rgba(233,237,230,0.09)',
                  transform: on ? 'translateY(-3px)' : 'none',
                }}
              >
                <div className="mb-1.5 flex items-center justify-between gap-2">
                  <p className="text-brand-gold m-0 font-mono text-[12px] font-semibold">{e.node_id ?? '—'}</p>
                  {role && (
                    <span
                      className="rounded-full border px-2 py-0.5 font-mono text-[9.5px] font-bold tracking-[0.08em]"
                      style={{ color: role.color, borderColor: role.color }}
                    >
                      {role.label}
                    </span>
                  )}
                </div>
                <p className="text-brand-fg/75 m-0 font-sans text-[13.5px] leading-relaxed">
                  {e.corridor?.note ?? e.action ?? 'Detection'}
                </p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
