import {
  fusedConfidence,
  modalityLabel,
  type EventRow,
  type Modality,
  type ModalityKind,
} from '@/lib/dashboard'

// Fixed display order so the card and radar always read seismic → audio → vision.
const MODALITY_ORDER: ModalityKind[] = ['seismic', 'acoustic', 'vision']

function ordered(modalities: Modality[]): Modality[] {
  return [...modalities].sort(
    (a, b) => MODALITY_ORDER.indexOf(a.kind) - MODALITY_ORDER.indexOf(b.kind),
  )
}

// One sensor's row: a check when it reported, its standalone confidence, and a
// bar sized by how much it moved the decision. A modality that dropped out shows
// as unavailable with no invented number.
function ModalityRow({ modality, maxContribution }: { modality: Modality; maxContribution: number }) {
  const label = modalityLabel(modality.kind)

  if (!modality.available) {
    return (
      <div className="flex items-center gap-2.5 opacity-55">
        <span className="text-brand-fg/40 w-3.5 text-center">–</span>
        <span className="flex-1 font-sans text-[13.5px]">{label}</span>
        <span className="text-brand-fg/40 font-mono text-[11px] tracking-wide">
          unavailable · dropped out
        </span>
      </div>
    )
  }

  const pct = modality.confidence != null ? Math.round(modality.confidence * 100) : null
  const barPct = maxContribution > 0 ? Math.max(0, (modality.contribution / maxContribution) * 100) : 0

  return (
    <div className="flex items-center gap-2.5">
      <span className="text-brand-green w-3.5 text-center">✔</span>
      <span className="flex-1 font-sans text-[13.5px]">{label}</span>
      <span className="bg-brand-fg/10 relative h-1.5 w-16 overflow-hidden rounded-full">
        <span
          className="bg-brand-gold absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${barPct}%` }}
        />
      </span>
      <span className="text-brand-green w-9 text-right font-mono text-[12px] font-semibold">
        {pct != null ? `${pct}%` : '—'}
      </span>
    </div>
  )
}

interface DecisionCardProps {
  event: EventRow | null
  // Slot for the confidence radar, added alongside the fused summary.
  radar?: React.ReactNode
  className?: string
}

export function DecisionCard({ event, radar, className = '' }: DecisionCardProps) {
  if (!event || !event.fusion) {
    return (
      <div className={`border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-4.5 ${className}`}>
        <h3 className="m-0 font-sans text-sm font-semibold">Why the AI acted</h3>
        <p className="text-brand-fg/40 m-0 mt-3 font-mono text-[12px]">
          No fused decision to explain yet.
        </p>
      </div>
    )
  }

  const modalities = ordered(event.fusion.modalities)
  const maxContribution = Math.max(
    0,
    ...modalities.filter((m) => m.available).map((m) => m.contribution),
  )
  const fused = fusedConfidence(event)
  const fusedPct = fused != null ? Math.round(fused * 100) : null

  return (
    <div className={`border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-4.5 ${className}`}>
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2.5">
        <h3 className="m-0 font-sans text-sm font-semibold">Why the AI acted · event {event.id}</h3>
        {event.outcome && (
          <span className="text-brand-bg bg-brand-green rounded-full px-2.5 py-0.75 font-mono text-[10.5px] font-bold tracking-wide">
            {event.outcome.toUpperCase()}
          </span>
        )}
      </div>

      <div className="mb-3.5 flex flex-col gap-2.25">
        {modalities.map((m) => (
          <ModalityRow key={m.kind} modality={m} maxContribution={maxContribution} />
        ))}
      </div>

      <div className="border-brand-fg/14 flex flex-wrap items-center gap-4 border-t border-dashed pt-3.5">
        {radar}
        <div className="min-w-0">
          <p className="text-brand-gold m-0 font-serif text-[34px] leading-none">
            {fusedPct != null ? `${fusedPct}%` : '—'}
          </p>
          <p className="text-brand-fg/50 mt-1.5 mb-2.5 font-mono text-[10.5px] font-semibold tracking-[0.1em]">
            FUSED CONFIDENCE
          </p>
          {event.action && (
            <p className="text-brand-gold m-0 font-sans text-[13.5px] font-semibold">
              → {event.action}
            </p>
          )}
          {event.species && (
            <p className="text-brand-fg/60 m-0 mt-0.75 font-sans text-[12.5px]">
              {event.species}
              {event.direction_deg != null ? ` · bearing ${event.direction_deg}°` : ''}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
