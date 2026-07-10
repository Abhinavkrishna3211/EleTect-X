import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import {
  relativeTime,
  statusDisplay,
  type EventRow,
  type HealthRow,
  type NodeRow,
} from '@/lib/dashboard'

function Field({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-brand-fg/45 m-0 font-mono text-[10.5px] font-semibold tracking-[0.08em]">
        {label}
      </p>
      <p className="m-0 mt-0.75 font-sans text-[17px] font-semibold" style={color ? { color } : undefined}>
        {value}
      </p>
    </div>
  )
}

interface NodeDetailPanelProps {
  node: NodeRow
  latestEvent: EventRow | null
  onClose: () => void
}

// Digital twin for the selected node: its live vitals from `nodes` plus the last
// few `health` telemetry rows. Health is fetched on selection (not streamed) —
// the map already carries the live status signal.
export function NodeDetailPanel({ node, latestEvent, onClose }: NodeDetailPanelProps) {
  const [health, setHealth] = useState<HealthRow[]>([])
  const status = statusDisplay(node.status)

  useEffect(() => {
    let active = true
    supabase
      .from('health')
      .select('*')
      .eq('node_id', node.id)
      .order('ts', { ascending: false })
      .limit(6)
      .then(({ data }) => {
        if (active) setHealth((data ?? []) as HealthRow[])
      })
    return () => {
      active = false
    }
  }, [node.id])

  const battLow = node.battery_pct != null && node.battery_pct < 40
  const lastDetection = latestEvent
    ? `${latestEvent.species ?? 'Detection'} · ${relativeTime(latestEvent.ts)}`
    : 'None recorded'

  return (
    <div className="border-brand-gold/35 rounded-2xl border bg-[rgba(226,161,60,0.04)] p-5">
      <div className="mb-3.5 flex flex-wrap items-center justify-between gap-2.5">
        <h3 className="m-0 font-sans text-base font-semibold">Node {node.id} · digital twin</h3>
        <div className="flex items-center gap-2">
          <span
            className="rounded-full border px-2.5 py-0.75 font-mono text-[10.5px] font-bold tracking-[0.08em]"
            style={{ color: status.color, borderColor: status.color }}
          >
            {status.label}
          </span>
          <button
            onClick={onClose}
            aria-label="Close node detail"
            className="text-brand-fg/50 hover:text-brand-fg px-2 py-1 text-lg leading-none"
          >
            ✕
          </button>
        </div>
      </div>

      <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(130px,1fr))]">
        <Field
          label="BATTERY"
          value={node.battery_pct != null ? `${node.battery_pct}%` : '—'}
          color={battLow ? '#e25b4a' : '#5fa97c'}
        />
        <Field label="SOLAR INPUT" value={node.solar_w != null ? `${node.solar_w} W` : '—'} />
        <Field label="LAST SEEN" value={relativeTime(node.last_seen)} />
        <Field label="FIRMWARE" value={node.firmware ?? '—'} />
        <Field label="ROLE" value={(node.kind ?? 'guard').toUpperCase()} />
        <Field label="LAST DETECTION" value={lastDetection} />
      </div>

      {health.length > 0 && (
        <div className="border-brand-fg/8 mt-4 border-t pt-3.5">
          <p className="text-brand-fg/45 m-0 mb-2 font-mono text-[10.5px] font-semibold tracking-[0.08em]">
            RECENT HEALTH
          </p>
          <div className="flex flex-col gap-1.5">
            {health.map((h) => (
              <div
                key={h.id}
                className="text-brand-fg/60 flex justify-between font-mono text-[11.5px]"
              >
                <span>{relativeTime(h.ts)}</span>
                <span className="flex gap-3">
                  {h.battery_pct != null && <span>{h.battery_pct}%</span>}
                  {h.solar_w != null && <span>{h.solar_w} W</span>}
                  {h.temp_c != null && <span>{h.temp_c}°C</span>}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
