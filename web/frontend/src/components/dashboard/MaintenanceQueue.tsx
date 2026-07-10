import { flagLabel, type MaintenanceCandidate, type MaintenanceRow } from '@/lib/fleet'

// The Fleet page's maintenance surface, in two parts:
//
//  1. Detected conditions — what the threshold rules currently see. These are NOT
//     yet in the database. An officer clicks "Raise flag" to commit one, so a page
//     view never silently writes rows (and two open tabs can't race to insert the
//     same flag). Candidates already raised are filtered out by the parent.
//  2. Open queue — unresolved `maintenance` rows, each resolvable in place.
//
// Both callbacks are async and disabled while in flight (busyKey), so a double
// click can't double-insert or double-resolve.

const SEVERITY_COLOR: Record<MaintenanceCandidate['severity'], string> = {
  critical: '#e25b4a',
  warn: '#d9b44a',
  info: '#5fa97c',
}

interface MaintenanceQueueProps {
  candidates: MaintenanceCandidate[]
  open: MaintenanceRow[]
  busyKey: string | null
  onRaise: (c: MaintenanceCandidate) => void
  onResolve: (row: MaintenanceRow) => void
}

export function MaintenanceQueue({ candidates, open, busyKey, onRaise, onResolve }: MaintenanceQueueProps) {
  return (
    <div className="flex flex-col gap-4">
      {/* Detected conditions strip */}
      <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-5">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h3 className="m-0 font-sans text-sm font-semibold">Detected conditions</h3>
          <span className="text-brand-fg/40 font-mono text-[10.5px] tracking-[0.08em]">
            {candidates.length === 0 ? 'NONE' : `${candidates.length} TO REVIEW`}
          </span>
        </div>
        {candidates.length === 0 ? (
          <p className="text-brand-fg/45 m-0 font-mono text-[12px]">
            All rule thresholds clear. Nothing to raise.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {candidates.map((c) => {
              const key = `${c.node_id}:${c.flag}`
              const color = SEVERITY_COLOR[c.severity]
              return (
                <div
                  key={key}
                  className="border-brand-fg/8 flex flex-wrap items-center gap-3 rounded-xl border px-3.5 py-3"
                >
                  <span
                    className="mt-0.5 h-2 w-2 shrink-0 rounded-full"
                    style={{ background: color, boxShadow: `0 0 6px ${color}` }}
                  />
                  <span className="text-brand-gold min-w-14 font-mono text-[12px] font-semibold">{c.node_id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-sans text-[13px] font-semibold" style={{ color }}>
                      {flagLabel(c.flag)}
                    </span>
                    <span className="text-brand-fg/60 block font-sans text-[12.5px] leading-snug">{c.reason}</span>
                  </span>
                  <button
                    onClick={() => onRaise(c)}
                    disabled={busyKey === key}
                    className="border-brand-gold/50 text-brand-gold hover:bg-brand-gold/10 min-h-9 shrink-0 rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors disabled:opacity-50"
                  >
                    {busyKey === key ? 'Raising…' : 'Raise flag'}
                  </button>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Open maintenance queue */}
      <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-5">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h3 className="m-0 font-sans text-sm font-semibold">Open maintenance queue</h3>
          <span className={`font-mono text-[10.5px] tracking-[0.08em] ${open.length ? 'text-brand-yellow' : 'text-brand-green'}`}>
            {open.length === 0 ? 'ALL CLEAR' : `${open.length} OPEN`}
          </span>
        </div>
        {open.length === 0 ? (
          <p className="text-brand-fg/45 m-0 font-mono text-[12px]">No open maintenance flags.</p>
        ) : (
          <div className="flex flex-col gap-2">
            {open.map((row) => (
              <div
                key={row.id}
                className="border-brand-fg/8 flex flex-wrap items-center gap-3 rounded-xl border px-3.5 py-3"
              >
                <span className="text-brand-gold min-w-14 font-mono text-[12px] font-semibold">{row.node_id}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 font-sans text-[13px] font-semibold">
                    {flagLabel(row.flag ?? '')}
                    {row.source === 'demo' && (
                      <span className="border-brand-fg/20 text-brand-fg/45 rounded-full border px-1.5 py-0 font-mono text-[9px] tracking-[0.08em]">
                        DEMO
                      </span>
                    )}
                  </span>
                  <span className="text-brand-fg/60 block font-sans text-[12.5px] leading-snug">{row.reason}</span>
                </span>
                <button
                  onClick={() => onResolve(row)}
                  disabled={busyKey === `resolve:${row.id}`}
                  className="border-brand-green/50 text-brand-green hover:bg-brand-green/10 min-h-9 shrink-0 rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors disabled:opacity-50"
                >
                  {busyKey === `resolve:${row.id}` ? 'Resolving…' : 'Resolve'}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
