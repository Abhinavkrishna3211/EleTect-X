import { statusDisplay, type MapPoint, type NodeStatus } from '@/lib/dashboard'

// Animated abstract sector map, ported from docs/design-reference/SectorMap.dc.html
// and driven by real data. Unlike the live Leaflet overview map, this stylised view
// can smoothly move a herd marker node-to-node and flow a corridor polyline, which
// is what the Replay scrub and the Corridor handoff need. The static public-page
// version lives in SectorMapIllustration.tsx; keep the two separate.

export interface SectorMapNode {
  id: string
  point: MapPoint // percent left/top on the map box
  status: NodeStatus
  active: boolean // ping ring (a node currently firing / steering)
}

export interface HerdMarker {
  point: MapPoint
  count: number
  label: string
}

interface SectorMapProps {
  nodes: SectorMapNode[]
  herd: HerdMarker | null
  // Ordered points of the safe-herding escape lane, percent [left, top] pairs.
  corridor: MapPoint[]
  label: string
}

export function SectorMap({ nodes, herd, corridor, label }: SectorMapProps) {
  const corridorPoints = corridor.map((p) => `${p.left},${p.top}`).join(' ')

  return (
    <div
      className="border-brand-fg/8 relative h-full w-full overflow-hidden rounded-2xl border"
      style={{
        background: 'radial-gradient(120% 90% at 30% 20%, #0F1D14 0%, #0A130E 55%, #070D0A 100%)',
      }}
    >
      {/* forest canopy blooms */}
      <div
        className="absolute rounded-full blur-md"
        style={{ left: '8%', top: '6%', width: '44%', height: '52%', background: 'radial-gradient(closest-side, rgba(47,94,63,0.5), rgba(47,94,63,0))' }}
      />
      <div
        className="absolute rounded-full blur-lg"
        style={{ left: '52%', top: '-8%', width: '52%', height: '60%', background: 'radial-gradient(closest-side, rgba(38,82,55,0.45), rgba(38,82,55,0))' }}
      />
      <div
        className="absolute rounded-full blur-lg"
        style={{ left: '-6%', top: '55%', width: '38%', height: '50%', background: 'radial-gradient(closest-side, rgba(43,74,50,0.4), rgba(43,74,50,0))' }}
      />
      {/* survey grid */}
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(233,237,230,0.05) 0px, rgba(233,237,230,0.05) 1px, transparent 1px, transparent 48px), repeating-linear-gradient(90deg, rgba(233,237,230,0.05) 0px, rgba(233,237,230,0.05) 1px, transparent 1px, transparent 48px)',
        }}
      />

      <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
        {/* river + forest-boundary reference paths (as in the design) */}
        <path d="M -2 44 C 18 40, 30 50, 46 46 C 62 42, 74 50, 102 45" fill="none" stroke="rgba(96,140,170,0.5)" strokeWidth="0.9" />
        <path d="M -2 58 L 30 55 L 62 57 L 102 53" fill="none" stroke="rgba(233,237,230,0.22)" strokeWidth="0.5" strokeDasharray="2 1.2" />
        {corridor.length >= 2 && (
          <polyline
            points={corridorPoints}
            fill="none"
            stroke="#E2A13C"
            strokeWidth="0.7"
            strokeDasharray="2.4 1.6"
            style={{ animation: 'et-dash 1.6s linear infinite' }}
          />
        )}
      </svg>

      {/* settlement markers */}
      <div className="absolute flex flex-col items-center gap-0.75" style={{ left: '14%', top: '82%' }}>
        <div className="bg-brand-fg/55 h-2.25 w-2.25 rotate-45" />
        <span className="text-brand-fg/50 font-mono text-[9px] tracking-[0.08em]">KOTHAMANGALAM</span>
      </div>
      <div className="absolute flex flex-col items-center gap-0.75" style={{ left: '66%', top: '86%' }}>
        <div className="bg-brand-fg/55 h-2.25 w-2.25 rotate-45" />
        <span className="text-brand-fg/50 font-mono text-[9px] tracking-[0.08em]">KUTTAMPUZHA</span>
      </div>

      {/* nodes */}
      {nodes.map((n) => {
        const { color } = statusDisplay(n.status)
        return (
          <div
            key={n.id}
            className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-0.75"
            style={{ left: `${n.point.left}%`, top: `${n.point.top}%`, zIndex: 3 }}
          >
            <div className="relative grid h-6.5 w-6.5 place-items-center">
              {n.active && (
                <span
                  className="absolute inset-0 rounded-full border-[1.5px]"
                  style={{ borderColor: color, animation: 'et-ping 1.4s ease-out infinite' }}
                />
              )}
              <span
                className="h-2.75 w-2.75 rounded-full border-[1.5px] border-[#070D0Acc]"
                style={{ background: color, boxShadow: `0 0 10px ${color}${n.active ? 'ff' : '99'}` }}
              />
            </div>
            <span className="text-brand-fg/65 font-mono text-[8.5px] font-semibold tracking-[0.06em]">{n.id}</span>
          </div>
        )
      })}

      {/* herd marker — CSS-transitions between node positions to animate movement */}
      {herd && (
        <div
          className="absolute flex flex-col items-center gap-1"
          style={{
            left: `${herd.point.left}%`,
            top: `${herd.point.top}%`,
            zIndex: 4,
            transform: 'translate(-50%,-50%)',
            transition: 'left 1.1s cubic-bezier(.4,0,.2,1), top 1.1s cubic-bezier(.4,0,.2,1)',
          }}
        >
          <div className="relative grid h-8.5 w-8.5 place-items-center">
            <span className="absolute inset-0 rounded-full border-[1.5px] border-[#E2A13C]" style={{ animation: 'et-ping 1.8s ease-out infinite' }} />
            <span className="text-brand-bg grid h-4.5 w-4.5 place-items-center rounded-full bg-[#E2A13C] font-mono text-[9px] font-bold">
              {herd.count}
            </span>
          </div>
          <span className="text-brand-gold rounded bg-[rgba(7,13,10,0.75)] px-1.5 py-0.5 font-mono text-[8.5px] font-bold tracking-[0.14em]">
            {herd.label}
          </span>
        </div>
      )}

      {/* header label */}
      <div className="text-brand-fg/55 absolute top-2.5 right-3 flex items-center gap-1.5 font-mono text-[9.5px] font-semibold">
        <span className="bg-brand-green inline-block h-1.75 w-1.75 rounded-full" />
        {label}
      </div>
      <div className="text-brand-fg/40 absolute right-3 bottom-2.5 font-mono text-[9px]">N ↑ · 1 km ——</div>
      <div className="text-brand-fg/55 absolute bottom-2.5 left-3 flex flex-wrap gap-3 font-mono text-[9px] font-medium">
        <span>
          <span className="bg-brand-green mr-1 inline-block h-1.75 w-1.75 rounded-full" />
          HEALTHY
        </span>
        <span>
          <span className="bg-brand-yellow mr-1 inline-block h-1.75 w-1.75 rounded-full" />
          ATTENTION
        </span>
        <span>
          <span className="bg-brand-red mr-1 inline-block h-1.75 w-1.75 rounded-full" />
          ALERT
        </span>
      </div>
    </div>
  )
}
