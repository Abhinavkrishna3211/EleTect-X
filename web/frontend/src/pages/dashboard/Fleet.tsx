import { useEffect, useMemo, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { FleetSummaryTiles } from '@/components/dashboard/FleetSummaryTiles'
import { Sparkline } from '@/components/dashboard/Sparkline'
import { MaintenanceQueue } from '@/components/dashboard/MaintenanceQueue'
import { NodeDetailPanel } from '@/components/dashboard/NodeDetailPanel'
import { relativeTime, statusDisplay, type EventRow, type HealthRow, type NodeRow } from '@/lib/dashboard'
import {
  dailyMeans,
  evaluateRules,
  isStale,
  operationalPct,
  type MaintenanceCandidate,
  type MaintenanceRow,
} from '@/lib/fleet'

type SortKey = 'status' | 'battery' | 'staleness'

// Attention-first status ordering for the roster: a dead node outranks one that
// merely needs service, which outranks a busy-but-healthy one.
const STATUS_RANK: Record<string, number> = { offline: 0, maintenance: 1, alert: 2, online: 3 }

export function Fleet() {
  const { rows: nodeRows, loading } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const { rows: maintRows } = useRealtimeTable<MaintenanceRow>('maintenance', 'id', {
    orderBy: { column: 'created_at', ascending: false },
  })
  const { rows: eventRows } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 50,
  })

  // 14-day health history, fetched once and grouped by node — too many rows to
  // stream, and the live signals that matter (status, flags) arrive via realtime.
  const [healthByNode, setHealthByNode] = useState<Map<string, HealthRow[]>>(new Map())
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('status')
  const [busyKey, setBusyKey] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const since = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString()
    supabase
      .from('health')
      .select('*')
      .gte('ts', since)
      .order('ts', { ascending: true })
      .then(({ data }) => {
        if (!active) return
        const map = new Map<string, HealthRow[]>()
        for (const h of (data ?? []) as HealthRow[]) {
          if (!h.node_id) continue
          const arr = map.get(h.node_id) ?? []
          arr.push(h)
          map.set(h.node_id, arr)
        }
        setHealthByNode(map)
      })
    return () => {
      active = false
    }
  }, [])

  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])
  const maintenance = useMemo(() => [...maintRows.values()], [maintRows])
  const events = useMemo(() => [...eventRows.values()], [eventRows])
  const openFlags = useMemo(() => maintenance.filter((m) => !m.resolved), [maintenance])

  const pct = operationalPct(nodes)

  // Rule candidates, minus anything already sitting unresolved in the queue — an
  // officer shouldn't be offered a flag they've already raised.
  const candidates = useMemo(() => {
    const raised = new Set(openFlags.map((m) => `${m.node_id}:${m.flag}`))
    return evaluateRules(nodes, healthByNode).filter((c) => !raised.has(`${c.node_id}:${c.flag}`))
  }, [nodes, healthByNode, openFlags])

  const flagCountByNode = useMemo(() => {
    const m = new Map<string, number>()
    for (const f of openFlags) if (f.node_id) m.set(f.node_id, (m.get(f.node_id) ?? 0) + 1)
    return m
  }, [openFlags])

  const sortedNodes = useMemo(() => {
    const arr = [...nodes]
    arr.sort((a, b) => {
      if (sortKey === 'battery') return (a.battery_pct ?? 999) - (b.battery_pct ?? 999)
      if (sortKey === 'staleness') {
        const ta = a.last_seen ? new Date(a.last_seen).getTime() : 0
        const tb = b.last_seen ? new Date(b.last_seen).getTime() : 0
        return ta - tb // oldest last_seen first
      }
      const ra = STATUS_RANK[a.status] ?? 9
      const rb = STATUS_RANK[b.status] ?? 9
      return ra - rb || a.id.localeCompare(b.id)
    })
    return arr
  }, [nodes, sortKey])

  const selectedNode = selectedNodeId ? (nodeRows.get(selectedNodeId) ?? null) : null
  const selectedNodeEvent = useMemo(
    () => (selectedNodeId ? (events.find((e) => e.node_id === selectedNodeId) ?? null) : null),
    [events, selectedNodeId],
  )

  async function raiseFlag(c: MaintenanceCandidate) {
    const key = `${c.node_id}:${c.flag}`
    setBusyKey(key)
    await supabase.from('maintenance').insert({
      node_id: c.node_id,
      flag: c.flag,
      reason: c.reason,
      source: 'rule',
    })
    setBusyKey(null)
  }

  async function resolveFlag(row: MaintenanceRow) {
    setBusyKey(`resolve:${row.id}`)
    await supabase.from('maintenance').update({ resolved: true }).eq('id', row.id)
    setBusyKey(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3.5">
        <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Fleet health</h1>
        <span className="text-brand-green font-mono text-[13px] font-semibold">{pct}% OPERATIONAL</span>
      </div>

      <FleetSummaryTiles nodes={nodes} operationalPct={pct} />

      {/* Roster controls */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-brand-fg/45 font-mono text-[11px] tracking-[0.08em]">SORT</span>
        {(['status', 'battery', 'staleness'] as SortKey[]).map((k) => (
          <button
            key={k}
            onClick={() => setSortKey(k)}
            className={`rounded-full border px-3 py-1.5 font-mono text-[11px] font-semibold transition-colors ${
              sortKey === k
                ? 'border-brand-gold text-brand-gold bg-[rgba(226,161,60,0.1)]'
                : 'border-brand-fg/15 text-brand-fg/55 hover:text-brand-fg'
            }`}
          >
            {k.toUpperCase()}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="border-brand-fg/10 text-brand-fg/40 grid h-40 place-items-center rounded-2xl border bg-[#0B0D0B] font-mono text-[12px]">
          Loading fleet…
        </div>
      ) : (
        <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(min(240px,100%),1fr))]">
          {sortedNodes.map((n) => {
            const st = statusDisplay(n.status)
            const points = dailyMeans(healthByNode.get(n.id) ?? [], 14)
            const battSeries = points.map((p) => p.battery)
            const solarSeries = points.map((p) => p.solar)
            const flags = flagCountByNode.get(n.id) ?? 0
            const stale = isStale(n.last_seen)
            const selected = n.id === selectedNodeId
            return (
              <button
                key={n.id}
                onClick={() => setSelectedNodeId(selected ? null : n.id)}
                className="rounded-2xl border p-4 text-left transition-colors"
                style={{
                  background: '#0B0D0B',
                  borderColor: selected ? 'rgba(226,161,60,0.6)' : 'rgba(233,237,230,0.09)',
                }}
              >
                <div className="mb-2.5 flex items-center justify-between gap-2">
                  <span className="font-mono text-[13px] font-semibold">{n.id}</span>
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: st.color, boxShadow: `0 0 8px ${st.color}` }}
                  />
                </div>
                <p className="text-brand-fg/50 m-0 mb-2.5 truncate font-sans text-[12px]">{n.name ?? '—'}</p>

                <div className="mb-1 flex items-center justify-between font-mono text-[10.5px]">
                  <span className="text-brand-fg/45">BATTERY</span>
                  <span style={{ color: (n.battery_pct ?? 100) < 40 ? '#e25b4a' : '#5fa97c' }}>
                    {n.battery_pct != null ? `${n.battery_pct}%` : '—'}
                  </span>
                </div>
                <Sparkline values={battSeries} color={(n.battery_pct ?? 100) < 40 ? '#e25b4a' : '#5fa97c'} min={0} max={100} />

                <div className="mt-2 mb-1 flex items-center justify-between font-mono text-[10.5px]">
                  <span className="text-brand-fg/45">SOLAR</span>
                  <span className="text-brand-gold">{n.solar_w != null ? `${n.solar_w} W` : '—'}</span>
                </div>
                <Sparkline values={solarSeries} color="#e2a13c" min={0} max={8} />

                <div className="border-brand-fg/8 mt-3 flex items-center justify-between border-t pt-2.5 font-mono text-[10.5px]">
                  <span className="text-brand-fg/45">{n.firmware ?? '—'}</span>
                  <span className={stale ? 'text-brand-yellow' : 'text-brand-fg/45'}>{relativeTime(n.last_seen)}</span>
                </div>
                {flags > 0 && (
                  <p className="text-brand-yellow m-0 mt-2 font-mono text-[10.5px] font-semibold">
                    {flags} OPEN FLAG{flags > 1 ? 'S' : ''}
                  </p>
                )}
              </button>
            )
          })}
        </div>
      )}

      {selectedNode && (
        <NodeDetailPanel
          node={selectedNode}
          latestEvent={selectedNodeEvent}
          onClose={() => setSelectedNodeId(null)}
        />
      )}

      <MaintenanceQueue
        candidates={candidates}
        open={openFlags}
        busyKey={busyKey}
        onRaise={raiseFlag}
        onResolve={resolveFlag}
      />
    </div>
  )
}
