import { useEffect, useMemo, useState } from 'react'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LiveMap } from '@/components/dashboard/LiveMap'
import { FleetSummaryTiles } from '@/components/dashboard/FleetSummaryTiles'
import { AlertsFeed } from '@/components/dashboard/AlertsFeed'
import { DecisionCard } from '@/components/dashboard/DecisionCard'
import { ConfidenceRadar } from '@/components/dashboard/ConfidenceRadar'
import { NodeDetailPanel } from '@/components/dashboard/NodeDetailPanel'
import type { EventRow, NodeRow } from '@/lib/dashboard'

// Live clock in IST, the sector's operating timezone — matches the timestamp
// beside the title in the design.
function useClockLabel() {
  const [label, setLabel] = useState('')
  useEffect(() => {
    const fmt = new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
    const tick = () => setLabel(`${fmt.format(new Date())} IST`)
    tick()
    const id = setInterval(tick, 30_000)
    return () => clearInterval(id)
  }, [])
  return label
}

export function Overview() {
  const { rows: nodeRows, loading } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const { rows: eventRows } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 20,
  })
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const clockLabel = useClockLabel()

  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])
  const events = useMemo(
    () => [...eventRows.values()].sort((a, b) => b.ts.localeCompare(a.ts)),
    [eventRows],
  )
  // The decision card explains the most recent event that carries a fusion pass.
  const decisionEvent = useMemo(() => events.find((e) => e.fusion) ?? null, [events])

  const selectedNode = selectedNodeId ? (nodeRows.get(selectedNodeId) ?? null) : null
  const selectedNodeEvent = useMemo(
    () => (selectedNodeId ? (events.find((e) => e.node_id === selectedNodeId) ?? null) : null),
    [events, selectedNodeId],
  )

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3.5">
        <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">
          Sector 7 · Kothamangalam
        </h1>
        <span className="text-brand-fg/45 font-mono text-[12.5px] font-medium">{clockLabel}</span>
      </div>

      <FleetSummaryTiles nodes={nodes} />

      <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(min(460px,100%),1fr))]">
        <div className="flex flex-col gap-2.5">
          <div className="h-[clamp(300px,42vw,420px)]">
            {loading ? (
              <div className="border-brand-fg/10 text-brand-fg/40 grid h-full place-items-center rounded-2xl border bg-[#0B0D0B] font-mono text-[12px]">
                Loading sector map…
              </div>
            ) : (
              <LiveMap nodes={nodes} selectedNodeId={selectedNodeId} onSelect={setSelectedNodeId} />
            )}
          </div>
          {selectedNode && (
            <NodeDetailPanel
              node={selectedNode}
              latestEvent={selectedNodeEvent}
              onClose={() => setSelectedNodeId(null)}
            />
          )}
        </div>

        {/* On a phone the decision card comes FIRST: it explains the detection the
            officer is looking at, and behind a flat alert list it was the last thing
            reachable. On desktop the feed leads, as designed — the column sits beside
            the map with room for both. */}
        <div className="flex min-w-0 flex-col gap-4">
          <DecisionCard
            event={decisionEvent}
            radar={
              decisionEvent?.fusion ? (
                <ConfidenceRadar modalities={decisionEvent.fusion.modalities} />
              ) : undefined
            }
            className="order-1 md:order-2"
          />
          <AlertsFeed
            events={events}
            selectedNodeId={selectedNodeId}
            onSelect={setSelectedNodeId}
            className="order-2 md:order-1"
          />
        </div>
      </div>
    </div>
  )
}
