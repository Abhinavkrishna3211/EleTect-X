import {
  fusedConfidence,
  isCritical,
  isUrgent,
  modalityLabel,
  priorityDisplay,
  speciesLabel,
  type EventRow,
  type Modality,
  type ModalityKind,
  type UplinkMeta,
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

// What the frame says the node did, in the order an officer reads it. Returns
// plain sentences rather than flag names: `safe_mode` and `deterrent_fired`
// mean nothing outside the firmware.
function uplinkFacts(uplink: UplinkMeta): string[] {
  const out: string[] = []
  if (uplink.tier != null) {
    out.push(uplink.tier === 0 ? 'No deterrent tier selected' : `Tier ${uplink.tier} selected`)
  }
  if (uplink.vision_confirmed != null) {
    out.push(
      uplink.vision_confirmed
        ? 'Confirmed on camera'
        : 'Not confirmed on camera — the node acted on ground and sound alone',
    )
  }
  if (uplink.safe_mode) out.push('Dry run — the deterrent was selected but held')
  else if (uplink.deterrent_fired === false && uplink.tier) out.push('Deterrent did not fire')
  else if (uplink.deterrent_fired) out.push('Deterrent fired')
  return out
}

// The one line that explains a 'critical'. The device measured this — it kept
// watching through the retreat tail after its top tier and the animal was
// still there — so the card says what was measured rather than inferring it.
function noRetreatLine(uplink: UplinkMeta | null): string {
  const tier = uplink?.tier
  return tier
    ? `Tier ${tier} fired and the animal had not left when the node stopped watching. ` +
        'The node is out of options — this needs people.'
    : 'Full deterrence fired and the animal had not left when the node stopped watching. ' +
        'The node is out of options — this needs people.'
}

function PriorityPill({ event }: { event: EventRow }) {
  if (!isUrgent(event.priority)) return null
  const pill = priorityDisplay(event.priority)
  if (pill.fill) {
    return (
      <span
        className="rounded-full px-2.5 py-0.75 font-mono text-[10.5px] font-bold tracking-wide"
        style={{ background: pill.fill, color: pill.color }}
      >
        {pill.label}
      </span>
    )
  }
  return (
    <span
      className="rounded-full border px-2.5 py-0.75 font-mono text-[10.5px] font-bold tracking-wide"
      style={{ color: pill.color, borderColor: pill.color }}
    >
      {pill.label}
    </span>
  )
}

function SpeciesLine({ event }: { event: EventRow }) {
  if (!event.species) return null
  return (
    <p className="text-brand-fg/60 m-0 mt-0.75 font-sans text-[12.5px]">
      {speciesLabel(event.species)}
      {event.direction_deg != null ? ` · bearing ${event.direction_deg}°` : ''}
    </p>
  )
}

interface DecisionCardProps {
  event: EventRow | null
  // Slot for the confidence radar, added alongside the fused summary.
  radar?: React.ReactNode
  className?: string
}

export function DecisionCard({ event, radar, className = '' }: DecisionCardProps) {
  if (!event) {
    return (
      <div className={`border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-4.5 ${className}`}>
        <h3 className="m-0 font-sans text-sm font-semibold">Why the AI acted</h3>
        <p className="text-brand-fg/40 m-0 mt-3 font-mono text-[12px]">
          No fused decision to explain yet.
        </p>
      </div>
    )
  }

  const fused = fusedConfidence(event)
  const fusedPct = fused != null ? Math.round(fused * 100) : null
  const critical = isCritical(event.priority)

  // A 'critical' event is the one an officer most needs explained, and it is
  // also the one least likely to carry a `fusion` blob: a real uplink is 11
  // bytes and cannot hold a per-modality breakdown, so only demo rows have
  // one. The card used to answer "no fused decision to explain yet" for every
  // genuine detection the node ever sent. Fall back to the frame, which does
  // say which tier fired, whether the camera confirmed, and whether the animal
  // left — and say plainly that the breakdown is what is missing.
  if (!event.fusion) {
    const facts = event.uplink ? uplinkFacts(event.uplink) : []
    return (
      <div className={`border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-4.5 ${className}`}>
        <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2.5">
          <h3 className="m-0 font-sans text-sm font-semibold">
            What the node reported · event {event.id}
          </h3>
          <PriorityPill event={event} />
        </div>

        {critical && (
          <p className="text-brand-red m-0 mb-3 font-sans text-[13px] leading-relaxed">
            {noRetreatLine(event.uplink)}
          </p>
        )}

        {facts.length > 0 ? (
          <ul className="m-0 mb-3.5 flex list-none flex-col gap-1.75 p-0">
            {facts.map((f) => (
              <li key={f} className="text-brand-fg/75 flex gap-2 font-sans text-[13px]">
                <span className="text-brand-fg/35" aria-hidden="true">
                  ·
                </span>
                <span>{f}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-brand-fg/40 m-0 mb-3.5 font-mono text-[12px]">
            This event carries no uplink frame.
          </p>
        )}

        <div className="border-brand-fg/14 border-t border-dashed pt-3.5">
          <p className="text-brand-gold m-0 font-serif text-[34px] leading-none">
            {fusedPct != null ? `${fusedPct}%` : '—'}
          </p>
          <p className="text-brand-fg/50 mt-1.5 mb-2.5 font-mono text-[10.5px] font-semibold tracking-[0.1em]">
            NODE CONFIDENCE
          </p>
          {event.action && (
            <p className="text-brand-gold m-0 font-sans text-[13.5px] font-semibold">
              → {event.action}
            </p>
          )}
          <SpeciesLine event={event} />
          <p className="text-brand-fg/35 m-0 mt-2.5 font-mono text-[10.5px] leading-relaxed">
            Per-modality breakdown not in this frame — the radio carries the decision, not the
            arithmetic behind it.
          </p>
        </div>
      </div>
    )
  }

  const modalities = ordered(event.fusion.modalities)
  const maxContribution = Math.max(
    0,
    ...modalities.filter((m) => m.available).map((m) => m.contribution),
  )

  return (
    <div className={`border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-4.5 ${className}`}>
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2.5">
        <h3 className="m-0 font-sans text-sm font-semibold">Why the AI acted · event {event.id}</h3>
        <div className="flex flex-wrap items-center gap-2">
          {/* Priority first: a green RETREATED pill beside a no-retreat event
              would be the card contradicting itself. */}
          <PriorityPill event={event} />
          {event.outcome && (
            <span className="text-brand-bg bg-brand-green rounded-full px-2.5 py-0.75 font-mono text-[10.5px] font-bold tracking-wide">
              {event.outcome.toUpperCase()}
            </span>
          )}
        </div>
      </div>

      {critical && (
        <p className="text-brand-red m-0 mb-3 font-sans text-[13px] leading-relaxed">
          {noRetreatLine(event.uplink)}
        </p>
      )}

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
          <SpeciesLine event={event} />
        </div>
      </div>
    </div>
  )
}
