import { useState, type FormEvent } from 'react'
import { supabase } from '@/lib/supabase'
import { useBrowserPosition } from '@/hooks/useBrowserPosition'
import type { NodeRow } from '@/lib/dashboard'
import { parsePosition, positionSanity } from '@/lib/fleet'

// A node that joins over LoRa registers itself with only its DevEUI: no name an
// officer would recognise and no position. web/ingest's touchNode() creates that
// row on the first uplink, so there is nothing to create here - what is missing
// is the position. Without one the node is absent from every map, and
// send-alert cannot find the residents within 3 km of it, so placing a node is
// part of commissioning it and is done here by an admin. The write is still
// gated by RLS (n_admin_all); this form is only shown to admins as a
// convenience, not as the access control.
//
// Two ways in, because commissioning happens in two places. An officer standing
// at the pole reads the position off the device they are holding; someone back
// at the office types it from the install record. The browser fix is the
// accurate one and is offered first, but it is a fill of the same two fields
// rather than a separate mode - whatever it returns can still be corrected by
// hand before saving.

const INPUT =
  'border-brand-fg/15 focus:border-brand-gold w-full rounded-lg border bg-[#070d0a] px-3 py-2 font-mono text-[13px] outline-none'

// Six decimals is ~0.11 m at the equator - far finer than any phone fix, and
// short enough to read back against an install record.
const DP = 6

export function NodePlacementForm({ node }: { node: NodeRow }) {
  const [name, setName] = useState(node.name ?? '')
  const [lat, setLat] = useState(node.lat != null ? String(node.lat) : '')
  const [lng, setLng] = useState(node.lng != null ? String(node.lng) : '')
  const [busy, setBusy] = useState(false)
  const [accuracy, setAccuracy] = useState<number | null>(null)
  const { locating, error: fixError, setError: setFixError, request } = useBrowserPosition()
  // A sanity warning is advice, not a refusal, so saving past it takes a second
  // deliberate click. Any edit to the coordinates clears the confirmation -
  // otherwise one acknowledged warning would wave through every later value.
  const [confirmed, setConfirmed] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)

  function setCoord(which: 'lat' | 'lng', value: string) {
    ;(which === 'lat' ? setLat : setLng)(value)
    setConfirmed(false)
    setAccuracy(null)
    setFixError(null)
    setMessage(null)
  }

  function useBrowserFix() {
    setMessage(null)
    request((fix) => {
      setLat(fix.lat.toFixed(DP))
      setLng(fix.lng.toFixed(DP))
      setAccuracy(fix.accuracy)
      setConfirmed(false)
    })
  }

  async function save(e: FormEvent) {
    e.preventDefault()
    const pos = parsePosition(lat, lng)
    if (pos === 'invalid') {
      setMessage({ ok: false, text: 'Enter both latitude and longitude as decimal degrees, e.g. 10.0612, 76.6331.' })
      return
    }
    const warning = pos && positionSanity(pos)
    if (warning && !confirmed) {
      setConfirmed(true)
      setMessage({ ok: false, text: `${warning} Press save again to use it anyway.` })
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
    setConfirmed(false)
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
          <input
            className={INPUT}
            value={lat}
            onChange={(e) => setCoord('lat', e.target.value)}
            inputMode="decimal"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-brand-fg/55 font-mono text-[10.5px]">Longitude</span>
          <input
            className={INPUT}
            value={lng}
            onChange={(e) => setCoord('lng', e.target.value)}
            inputMode="decimal"
          />
        </label>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={busy}
          className="bg-brand-gold hover:bg-brand-gold-hover min-h-10 rounded-full px-4 py-2 font-mono text-[11px] font-bold tracking-[0.08em] text-[#0b140e] disabled:opacity-50"
        >
          {busy ? 'SAVING…' : confirmed ? 'SAVE ANYWAY' : 'SAVE'}
        </button>
        <button
          type="button"
          onClick={useBrowserFix}
          disabled={locating || busy}
          className="border-brand-fg/20 hover:border-brand-gold text-brand-fg/75 min-h-10 rounded-full border px-4 py-2 font-mono text-[11px] font-bold tracking-[0.08em] disabled:opacity-50"
        >
          {locating ? 'LOCATING…' : 'USE MY LOCATION'}
        </button>
        {accuracy != null && (
          <span className="text-brand-fg/45 font-mono text-[11.5px]">
            Fix ±{Math.round(accuracy)} m
          </span>
        )}
        {(message || fixError) && (
          <span
            className={`font-mono text-[11.5px] ${message?.ok ? 'text-brand-green' : 'text-brand-red'}`}
          >
            {message?.text ?? fixError}
          </span>
        )}
      </div>
    </form>
  )
}
