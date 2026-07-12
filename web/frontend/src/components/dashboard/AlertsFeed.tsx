import { useState } from 'react'
import { relativeTime, type EventRow } from '@/lib/dashboard'

// The feed used to render every fetched event flat — 20 rows at ~76px, which on a
// 390px phone was 1510px, 59% of the whole Overview page, and pushed the decision
// card ("Why the AI acted") below all of it. An officer in the field had to scroll
// past the entire history to reach the reasoning for the detection in front of them.
// Default to the most recent few; the rest are one tap away, never dropped.
const COLLAPSED_COUNT = 5

// Rough species → glyph map for the feed. Unknown species fall back to a generic
// marker; this is a visual affordance only, never load-bearing.
const SPECIES_ICON: Record<string, string> = {
  elephant: '🐘',
  boar: '🐗',
  gaur: '🐃',
  deer: '🦌',
  monkey: '🐒',
  leopard: '🐆',
  tiger: '🐅',
}

function iconFor(species: string | null): string {
  if (!species) return '📡'
  const key = species.toLowerCase()
  for (const name in SPECIES_ICON) if (key.includes(name)) return SPECIES_ICON[name]
  return '📡'
}

function titleFor(event: EventRow): string {
  const species = event.species ? event.species[0].toUpperCase() + event.species.slice(1) : 'Detection'
  return event.action ? `${species} · ${event.action}` : species
}

function metaFor(event: EventRow): string {
  const parts: string[] = []
  if (event.node_id) parts.push(event.node_id)
  parts.push(relativeTime(event.ts))
  if (event.confidence != null) parts.push(`${Math.round(event.confidence * 100)}%`)
  if (event.outcome) parts.push(event.outcome)
  return parts.join(' · ')
}

interface AlertsFeedProps {
  events: EventRow[]
  selectedNodeId: string | null
  onSelect: (id: string) => void
  className?: string
}

export function AlertsFeed({ events, selectedNodeId, onSelect, className = '' }: AlertsFeedProps) {
  const [expanded, setExpanded] = useState(false)
  const highCount = events.filter((e) => e.priority === 'high').length

  const hasMore = events.length > COLLAPSED_COUNT
  const visible = expanded || !hasMore ? events : events.slice(0, COLLAPSED_COUNT)
  const hiddenCount = events.length - visible.length

  return (
    <div className={`border-brand-fg/10 overflow-hidden rounded-2xl border bg-[#0B0D0B] ${className}`}>
      <div className="border-brand-fg/8 flex items-center justify-between border-b px-4.5 py-3.5">
        <h3 className="m-0 font-sans text-sm font-semibold">Alerts</h3>
        <span className="text-brand-red font-mono text-[11px] font-semibold">
          {highCount > 0 ? `${highCount} HIGH PRIORITY` : 'ALL CLEAR'}
        </span>
      </div>

      {events.length === 0 ? (
        <p className="text-brand-fg/40 m-0 px-4.5 py-6 text-center font-mono text-[12px]">
          No detections yet
        </p>
      ) : (
        <div className="flex flex-col">
          {visible.map((e) => {
            const high = e.priority === 'high'
            const active = e.node_id != null && e.node_id === selectedNodeId
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
                  style={{ background: high ? 'rgba(226,91,74,0.12)' : '#0F1D14' }}
                >
                  {iconFor(e.species)}
                </span>
                <span className="min-w-0 flex-1">
                  <span
                    className={`block truncate font-sans text-[13.5px] font-semibold ${
                      high ? 'text-brand-red' : 'text-brand-fg'
                    }`}
                  >
                    {titleFor(e)}
                  </span>
                  <span className="text-brand-fg/45 mt-0.5 block truncate font-mono text-[11.5px]">
                    {metaFor(e)}
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
              {expanded ? 'SHOW LESS' : `SHOW ALL ${events.length} (${hiddenCount} MORE)`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
