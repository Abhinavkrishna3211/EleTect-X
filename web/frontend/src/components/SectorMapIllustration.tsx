type NodeStatus = 'healthy' | 'attention' | 'alert'

interface SectorNode {
  id: string
  left: string
  top: string
  status: NodeStatus
}

const nodes: SectorNode[] = [
  { id: 'S7-02', left: '18%', top: '64%', status: 'healthy' },
  { id: 'S7-04', left: '74%', top: '58%', status: 'healthy' },
  { id: 'S7-05', left: '56%', top: '44%', status: 'healthy' },
  { id: 'S7-06', left: '38%', top: '58%', status: 'attention' },
  { id: 'S7-07', left: '30%', top: '38%', status: 'healthy' },
  { id: 'S7-08', left: '48%', top: '26%', status: 'healthy' },
  { id: 'S7-09', left: '68%', top: '20%', status: 'attention' },
  { id: 'S7-11', left: '84%', top: '12%', status: 'healthy' },
  { id: 'S7-12', left: '10%', top: '28%', status: 'alert' },
]

const statusColor: Record<NodeStatus, string> = {
  healthy: '#5fa97c',
  attention: '#d9b44a',
  alert: '#e25b4a',
}

export function SectorMapIllustration({ label }: { label: string }) {
  return (
    <div
      className="border-brand-fg/8 relative h-full w-full overflow-hidden rounded-2xl border"
      style={{
        background: 'radial-gradient(120% 90% at 30% 20%, #0F1D14 0%, #0A130E 55%, #070D0A 100%)',
      }}
    >
      <div
        className="absolute rounded-full blur-md"
        style={{
          left: '8%',
          top: '6%',
          width: '44%',
          height: '52%',
          background: 'radial-gradient(closest-side, rgba(47,94,63,0.5), rgba(47,94,63,0))',
        }}
      />
      <div
        className="absolute rounded-full blur-lg"
        style={{
          left: '52%',
          top: '-8%',
          width: '52%',
          height: '60%',
          background: 'radial-gradient(closest-side, rgba(38,82,55,0.45), rgba(38,82,55,0))',
        }}
      />
      <div
        className="absolute rounded-full blur-lg"
        style={{
          left: '-6%',
          top: '55%',
          width: '38%',
          height: '50%',
          background: 'radial-gradient(closest-side, rgba(43,74,50,0.4), rgba(43,74,50,0))',
        }}
      />
      <div
        className="absolute inset-0"
        style={{
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(233,237,230,0.05) 0px, rgba(233,237,230,0.05) 1px, transparent 1px, transparent 48px), repeating-linear-gradient(90deg, rgba(233,237,230,0.05) 0px, rgba(233,237,230,0.05) 1px, transparent 1px, transparent 48px)',
        }}
      />

      <svg viewBox="0 0 100 62" preserveAspectRatio="none" className="absolute inset-0 h-full w-full">
        <path
          d="M -2 44 C 18 40, 30 50, 46 46 C 62 42, 74 50, 102 45"
          fill="none"
          stroke="rgba(96,140,170,0.5)"
          strokeWidth="1.6"
        />
        <path
          d="M -2 58 L 30 55 L 62 57 L 102 53"
          fill="none"
          stroke="rgba(233,237,230,0.22)"
          strokeWidth="0.7"
          strokeDasharray="2 1.2"
        />
      </svg>

      <div className="absolute flex flex-col items-center gap-0.75" style={{ left: '14%', top: '78%' }}>
        <div className="bg-brand-fg/55 h-2.25 w-2.25 rotate-45" />
        <span className="text-brand-fg/50 font-mono text-[9px] tracking-[0.08em]">KOTHAMANGALAM</span>
      </div>
      <div className="absolute flex flex-col items-center gap-0.75" style={{ left: '66%', top: '82%' }}>
        <div className="bg-brand-fg/55 h-2.25 w-2.25 rotate-45" />
        <span className="text-brand-fg/50 font-mono text-[9px] tracking-[0.08em]">KUTTAMPUZHA</span>
      </div>

      {nodes.map((n) => (
        <div
          key={n.id}
          className="absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-0.75"
          style={{ left: n.left, top: n.top }}
        >
          <div
            className="h-2.75 w-2.75 rounded-full border-[1.5px] border-[#070D0Acc]"
            style={{ background: statusColor[n.status], boxShadow: `0 0 10px ${statusColor[n.status]}99` }}
          />
          <span className="text-brand-fg/65 font-mono text-[8.5px] font-semibold tracking-[0.06em]">{n.id}</span>
        </div>
      ))}

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
