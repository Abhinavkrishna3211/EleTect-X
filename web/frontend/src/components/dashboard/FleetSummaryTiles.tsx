import { statusDisplay, type NodeRow, type NodeStatus } from '@/lib/dashboard'

// Summary of the sector's fleet by status bucket — the tile row at the top of
// the overview (design lines 752-760). Derived from the live node set; the full
// Fleet screen is a separate phase.
const ORDER: NodeStatus[] = ['online', 'maintenance', 'alert', 'offline']

export function FleetSummaryTiles({ nodes }: { nodes: NodeRow[] }) {
  const counts = ORDER.map((status) => ({
    status,
    ...statusDisplay(status),
    value: nodes.filter((n) => n.status === status).length,
  }))

  return (
    <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
      {counts.map((c) => (
        <div
          key={c.status}
          className="border-brand-fg/9 rounded-2xl border bg-[#0B0D0B] px-4.5 py-4"
        >
          <p className="m-0 font-serif text-[30px] leading-none" style={{ color: c.color }}>
            {c.value}
          </p>
          <p className="text-brand-fg/55 mt-2 font-mono text-[11px] font-semibold tracking-[0.1em]">
            {c.label}
          </p>
        </div>
      ))}
    </div>
  )
}
