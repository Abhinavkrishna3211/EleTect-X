import { statusDisplay, type NodeRow, type NodeStatus } from '@/lib/dashboard'

// Summary of the sector's fleet by status bucket — the tile row at the top of the
// overview (design lines 752-760) and the Fleet page (design lines 921-930). On
// Overview it renders the four status buckets; the Fleet page passes
// `operationalPct` to append the fifth OPERATIONAL tile the design shows there.
const ORDER: NodeStatus[] = ['online', 'maintenance', 'alert', 'offline']

interface FleetSummaryTilesProps {
  nodes: NodeRow[]
  // When set, appends a "FLEET OPERATIONAL" tile. Omitted on Overview → 4 tiles.
  operationalPct?: number
}

export function FleetSummaryTiles({ nodes, operationalPct }: FleetSummaryTilesProps) {
  const counts = ORDER.map((status) => ({
    key: status as string,
    ...statusDisplay(status),
    value: String(nodes.filter((n) => n.status === status).length),
  }))

  const tiles =
    operationalPct != null
      ? [...counts, { key: 'operational', label: 'FLEET OPERATIONAL', color: '#E9EDE6', value: `${operationalPct}%` }]
      : counts

  return (
    <div
      className={`grid grid-cols-2 gap-2.5 ${operationalPct != null ? 'sm:grid-cols-3 lg:grid-cols-5' : 'sm:grid-cols-4'}`}
    >
      {tiles.map((c) => (
        <div key={c.key} className="border-brand-fg/9 rounded-2xl border bg-[#0B0D0B] px-4.5 py-4">
          <p className="m-0 font-serif text-[30px] leading-none" style={{ color: c.color }}>
            {c.value}
          </p>
          <p className="text-brand-fg/55 mt-2 font-mono text-[11px] font-semibold tracking-[0.1em]">{c.label}</p>
        </div>
      ))}
    </div>
  )
}
