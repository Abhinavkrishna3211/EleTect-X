import { useState, type FormEvent } from 'react'
import { supabase } from '@/lib/supabase'
import type { NodeRow } from '@/lib/dashboard'
import { parsePosition } from '@/lib/fleet'

// A node that joins over LoRa registers itself with only its DevEUI: no name an
// officer would recognise and no position. Without a position it is missing from
// every map, and send-alert cannot find residents within 3 km of it - so placing
// a new node is part of commissioning it, done here by an admin. The write is
// still gated by RLS (n_admin_all); this form is only shown to admins as a
// convenience, not as the access control.

const INPUT =
  'border-brand-fg/15 focus:border-brand-gold w-full rounded-lg border bg-[#070d0a] px-3 py-2 font-mono text-[13px] outline-none'

export function NodePlacementForm({ node }: { node: NodeRow }) {
  const [name, setName] = useState(node.name ?? '')
  const [lat, setLat] = useState(node.lat != null ? String(node.lat) : '')
  const [lng, setLng] = useState(node.lng != null ? String(node.lng) : '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  async function save(e: FormEvent) {
    e.preventDefault()
    const pos = parsePosition(lat, lng)
    if (pos === 'invalid') {
      setMessage({ ok: false, text: 'Enter both latitude and longitude as decimal degrees, e.g. 10.0612, 76.6331.' })
      return
    }
    setBusy(true)
    setMessage(null)
    const { data, error } = await supabase
      .from('nodes')
      .update({ name: name.trim() || null, lat: pos?.lat ?? null, lng: pos?.lng ?? null })
      .eq('id', node.id)
      .select('id')
    setBusy(false)
    // RLS turns a refused update into zero rows, not an error - check both.
    if (error || !data?.length) {
      setMessage({ ok: false, text: error?.message ?? 'Not saved - only admins can change a node.' })
      return
    }
    setMessage({ ok: true, text: 'Saved.' })
  }

  return (
    <form onSubmit={save} className="border-brand-fg/8 mt-4 border-t pt-3.5">
      <p className="text-brand-fg/45 m-0 mb-2 font-mono text-[10.5px] font-semibold tracking-[0.08em]">
        NAME AND LOCATION
      </p>
      <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
        <label className="flex flex-col gap-1">
          <span className="text-brand-fg/55 font-mono text-[10.5px]">Name</span>
          <input className={INPUT} value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-brand-fg/55 font-mono text-[10.5px]">Latitude</span>
          <input className={INPUT} value={lat} onChange={(e) => setLat(e.target.value)} inputMode="decimal" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-brand-fg/55 font-mono text-[10.5px]">Longitude</span>
          <input className={INPUT} value={lng} onChange={(e) => setLng(e.target.value)} inputMode="decimal" />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="bg-brand-gold hover:bg-brand-gold-hover rounded-full px-4 py-2 font-mono text-[11px] font-bold tracking-[0.08em] text-[#0b140e] disabled:opacity-50"
        >
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        {message && (
          <span className={`font-mono text-[11.5px] ${message.ok ? 'text-brand-green' : 'text-brand-red'}`}>
            {message.text}
          </span>
        )}
      </div>
    </form>
  )
}
