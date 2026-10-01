import { useMemo, useState } from 'react'
import {
  isCritical,
  isUrgent,
  priorityDisplay,
  relativeTime,
  speciesIcon,
  speciesLabel,
  speciesShort,
  type EventRow,
} from '@/lib/dashboard'

// The feed used to render every fetched event flat — 20 rows at ~76px, which on a
// 390px phone was 1510px, 59% of the whole Overview page, and pushed the decision
// card ("Why the AI acted") below all of it. An officer in the field had to scroll
// past the entire history to reach the reasoning for the detection in front of them.
// Default to the most recent few; the rest are one tap away, never dropped.
const COLLAPSED_COUNT = 5

// Show the species filter only once there is something to separate. One chip
// next to ALL is a control that does nothing.
const FILTER_MIN_SPECIES = 2

function titleFor(event: EventRow): string {
  const species = speciesLabel(event.species)
  return event.action ? `${species} · ${event.action}` : species
}

// A node that registered itself over LoRa is keyed by its DevEUI, which means
// nothing to an officer - show the name staff gave it when there is one.
function metaFor(event: EventRow, nodeNames?: Map<string, string>): string {
  const parts: string[] = []
  if (event.node_id) parts.push(nodeNames?.get(event.node_id) ?? event.node_id)
  parts.push(relativeTime(event.ts))
  if (event.confidence != null) parts.push(`${Math.round(event.confidence * 100)}%`)
  if (event.outcome) parts.push(event.outcome)
  return parts.join(' · ')
}

interface SpeciesTally {
  key: string
  species: string
  count: number
}

// Chips for the species actually in the window, not the whole vocabulary: an
// officer should not be offered a CHAINSAW filter on a night of foxes. Ordered
// by count so the thing filling the feed is the easiest thing to filter on.
function tally(events: EventRow[]): SpeciesTally[] {
  const counts = new Map<string, SpeciesTally>()
  for (const e of events) {
    const key = (e.species ?? '').trim().toLowerCase()
    if (!key) continue
    const seen = counts.get(key)
    if (seen) seen.count += 1
    else counts.set(key, { key, species: e.species as string, count: 1 })
  }
  return [...counts.values()].sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
}

interface AlertsFeedProps {
  events: EventRow[]
  selectedNodeId: string | null
  onSelect: (id: string) => void
  nodeNames?: Map<string, string>
  className?: string
}

export function AlertsFeed({
  events,
  selectedNodeId,
  onSelect,
  nodeNames,
  className = '',
}: AlertsFeedProps) {
  const [expanded, setExpanded] = useState(false)
  const [speciesFilter, setSpeciesFilter] = useState<string | null>(null)

  // Counted over every event, never over the filtered view. This line is the
  // sector's alarm state, and a filter an officer set to read a fox cluster
  // must not be able to make a critical elephant disappear from it.
  const criticalCount = events.filter((e) => isCritical(e.priority)).length
  const highCount = events.filter((e) => isUrgent(e.priority)).length - criticalCount

  const chips = useMemo(() => tally(events), [events])
  const showFilter = chips.length >= FILTER_MIN_SPECIES

  const filtered = useMemo(() => {
    if (!speciesFilter) return events
    return events.filter((e) => (e.species ?? '').trim().toLowerCase() === speciesFilter)
  }, [events, speciesFilter])

  const hasMore = filtered.length > COLLAPSED_COUNT
  const visible = expanded || !hasMore ? filtered : filtered.slice(0, COLLAPSED_COUNT)
  const hiddenCount = filtered.length - visible.length

  const statusLabel =
    criticalCount > 0
      ? `${criticalCount} NO RETREAT${highCount > 0 ? ` · ${highCount} HIGH` : ''}`
      : highCount > 0
        ? `${highCount} HIGH PRIORITY`
        : 'ALL CLEAR'

  return (
    <div className={`border-brand-fg/10 overflow-hidden rounded-2xl border bg-[#0B0D0B] ${className}`}>
      <div className="border-brand-fg/8 flex items-center justify-between border-b px-4.5 py-3.5">
        <h3 className="m-0 font-sans text-sm font-semibold">Alerts</h3>
        <span
          className="font-mono text-[11px] font-semibold"
          style={{ color: criticalCount + highCount > 0 ? '#e25b4a' : '#5fa97c' }}
        >
          {statusLabel}
        </span>
      </div>

      {showFilter && (
        <div
          className="border-brand-fg/8 flex flex-wrap gap-1.5 border-b px-4.5 py-2.5"
          role="group"
          aria-label="Filter alerts by species"
        >
          <button
            onClick={() => setSpeciesFilter(null)}
            aria-pressed={speciesFilter === null}
            className={`rounded-full border px-2.5 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] transition-colors ${
              speciesFilter === null
                ? 'border-brand-gold/60 text-brand-gold bg-[rgba(226,161,60,0.1)]'
                : 'border-brand-fg/15 text-brand-fg/55 hover:text-brand-fg'
            }`}
          >
            ALL {events.length}
          </button>
          {chips.map((c) => {
            const on = speciesFilter === c.key
            return (
              <button
                key={c.key}
                // Tapping the active chip clears it, so there is always a way
                // back without hunting for ALL.
                onClick={() => setSpeciesFilter(on ? null : c.key)}
                aria-pressed={on}
                className={`rounded-full border px-2.5 py-1 font-mono text-[10.5px] font-semibold tracking-[0.06em] transition-colors ${
                  on
                    ? 'border-brand-gold/60 text-brand-gold bg-[rgba(226,161,60,0.1)]'
                    : 'border-brand-fg/15 text-brand-fg/55 hover:text-brand-fg'
                }`}
              >
                <span aria-hidden="true">{speciesIcon(c.species)}</span> {speciesShort(c.species)}{' '}
                {c.count}
              </button>
            )
          })}
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="text-brand-fg/40 m-0 px-4.5 py-6 text-center font-mono text-[12px]">
          {events.length === 0
            ? 'No detections yet'
            : `No ${speciesLabel(speciesFilter).toLowerCase()} detections in this window`}
        </p>
      ) : (
        <div className="flex flex-col">
          {visible.map((e) => {
            const urgent = isUrgent(e.priority)
            const critical = isCritical(e.priority)
            const active = e.node_id != null && e.node_id === selectedNodeId
            const pill = priorityDisplay(e.priority)
            return (
              <button
                key={e.id}
                onClick={() => e.node_id && onSelect(e.node_id)}
                className={`border-brand-fg/5 flex items-center gap-3 border-b px-4.5 py-3.5 text-left transition-colors last:border-b-0 ${
                  active ? 'bg-[rgba(226,161,60,0.08)]' : 'hover:bg-brand-fg/4'
                }`}
              >
                <span
                  className="grid h-11 w-11 shrink-0 place-items-center rounded-[10px] text-lg"
                  style={{
                    background: critical
                      ? 'rgba(226,91,74,0.22)'
                      : urgent
                        ? 'rgba(226,91,74,0.12)'
                        : '#0F1D14',
                  }}
                  aria-hidden="true"
                >
                  {speciesIcon(e.species)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className={`min-w-0 truncate font-sans text-[13.5px] font-semibold ${
                        urgent ? 'text-brand-red' : 'text-brand-fg'
                      }`}
                    >
                      {titleFor(e)}
                    </span>
                    {/* The whole point of 'critical': a filled badge, not one
                        more red line, so "it did not leave" is readable at a
                        glance in a feed where 'high' is already red. */}
                    {critical && pill.fill && (
                      <span
                        className="shrink-0 rounded-full px-1.75 py-0.25 font-mono text-[9.5px] font-bold tracking-[0.07em]"
                        style={{ background: pill.fill, color: pill.color }}
                      >
                        {pill.label}
                      </span>
                    )}
                  </span>
                  <span className="text-brand-fg/45 mt-0.5 block truncate font-mono text-[11.5px]">
                    {metaFor(e, nodeNames)}
                  </span>
                </span>
              </button>
            )
          })}

          {hasMore && (
            <button
              onClick={() => setExpanded((v) => !v)}
              aria-expanded={expanded}
              className="border-brand-fg/8 text-brand-fg/60 hover:text-brand-fg hover:bg-brand-fg/4 min-h-11 border-t px-4.5 py-3 font-mono text-[11.5px] font-semibold tracking-[0.08em] transition-colors"
            >
              {expanded ? 'SHOW LESS' : `SHOW ALL ${filtered.length} (${hiddenCount} MORE)`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
