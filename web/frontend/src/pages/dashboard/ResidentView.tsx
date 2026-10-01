import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { useAlertsOptIn } from '@/hooks/useAlertsOptIn'
import { useBrowserPosition } from '@/hooks/useBrowserPosition'
import { deriveAreaRisk, recentActivity, riskDisplay, type AreaRiskRow } from '@/lib/risk'

type LoadState = 'loading' | 'ready' | 'error'

export function ResidentView() {
  // Same opt-in write the Stay Safe page uses — one path to alerts_enabled.
  const {
    enabled: alertsOn,
    located,
    saving,
    error: saveError,
    setEnabled,
    setLocation,
    clearLocation,
  } = useAlertsOptIn()
  const { locating, error: fixError, setError: setFixError, request } = useBrowserPosition()

  function captureLocation() {
    setFixError(null)
    request((fix) => void setLocation(fix.lat, fix.lng))
  }
  const [rows, setRows] = useState<AreaRiskRow[]>([])
  const [state, setState] = useState<LoadState>('loading')

  useEffect(() => {
    let cancelled = false
    // public_area_risk is the only detection data a resident's role can read —
    // aggregate counts per day, no species or location. See lib/risk.ts.
    supabase
      .from('public_area_risk')
      .select('day, detections')
      .then(({ data, error }) => {
        if (cancelled) return
        if (error) {
          setState('error')
          return
        }
        setRows((data ?? []) as AreaRiskRow[])
        setState('ready')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const risk = deriveAreaRisk(rows)
  const display = riskDisplay(risk)
  const activity = recentActivity(rows)

  return (
    <div className="mx-auto flex max-w-170 flex-col gap-4">
      <h1 className="m-0 mt-2 font-serif text-[clamp(26px,4vw,36px)] font-normal">Your area</h1>

      {state === 'loading' ? (
        <div className="border-brand-fg/10 rounded-[18px] border bg-[#0B0D0B] p-6.5">
          <p className="text-brand-fg/45 m-0 font-mono text-[12.5px]">Checking your area…</p>
        </div>
      ) : state === 'error' ? (
        <div className="border-brand-red/35 rounded-[18px] border bg-[rgba(226,91,74,0.06)] p-6.5">
          <p className="text-brand-fg/75 m-0 font-sans text-sm leading-relaxed">
            Area status is unavailable right now. This screen is informational only — your alerts are unaffected
            and will still reach you.
          </p>
        </div>
      ) : (
        <div
          className={`flex flex-wrap items-center gap-4.5 rounded-[18px] border p-6.5 ${display.border}`}
          style={{ background: display.background }}
        >
          <div className="border-brand-fg/20 grid h-14 w-14 place-items-center rounded-full border-2 text-2xl">
            {display.dot}
          </div>
          <div className="min-w-50 flex-1">
            <p className="text-brand-fg/50 m-0 mb-1 font-mono text-[11.5px] font-semibold tracking-[0.12em]">
              KOTHAMANGALAM SECTOR · RISK LEVEL
            </p>
            <p className={`m-0 font-sans text-xl font-semibold ${display.color}`}>{display.label}</p>
          </div>
        </div>
      )}

      <div className="border-brand-fg/10 rounded-[18px] border bg-[#0B0D0B] p-6">
        <h2 className="m-0 mb-4 font-sans text-base font-semibold">Recent activity near you</h2>
        {state === 'ready' && activity.length === 0 ? (
          <p className="text-brand-fg/45 m-0 font-mono text-[12.5px]">
            No detections recorded near villages recently.
          </p>
        ) : state === 'ready' ? (
          <div className="flex flex-col gap-3">
            {activity.map((a, i) => (
              <div
                key={a.day}
                className={`flex items-start gap-3 ${
                  i < activity.length - 1 ? 'border-brand-fg/6 border-b pb-3' : ''
                }`}
              >
                <span
                  aria-hidden="true"
                  className="bg-brand-gold/70 mt-1.75 h-2 w-2 shrink-0 rounded-full"
                />
                <div className="flex-1">
                  <p className="m-0 font-sans text-sm font-semibold">
                    {a.detections} {a.detections === 1 ? 'detection' : 'detections'} near villages
                  </p>
                  <p className="text-brand-fg/45 m-0.5 mt-0.5 font-mono text-[12.5px]">{a.label}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-brand-fg/45 m-0 font-mono text-[12.5px]">—</p>
        )}
        <p className="text-brand-fg/40 m-0 mt-4 font-sans text-[12.5px] leading-relaxed">
          Counts only. Exact location and direction are sent to you directly in an alert, never shown here.
        </p>
      </div>

      <div className="border-brand-fg/10 rounded-[18px] border bg-[#0B0D0B] p-6">
        <button
          onClick={() => setEnabled(!alertsOn)}
          disabled={saving}
          aria-pressed={alertsOn}
          className="flex min-h-11 w-full items-center justify-between gap-3.5 bg-transparent p-0 disabled:opacity-60"
        >
          <span className="text-left">
            <span className="block font-sans text-[15px] font-semibold">Safety alerts</span>
            <span className="text-brand-fg/50 mt-0.5 block font-sans text-[13px]">
              {!alertsOn
                ? 'Off · turn on to be alerted about wildlife near you'
                : located
                  ? 'On · you will be alerted when wildlife is detected near you'
                  : 'On · but no alert can reach you until you set your location below'}
            </span>
          </span>
          <span
            className={`relative h-7 w-12.5 shrink-0 rounded-full transition-colors ${
              alertsOn ? 'bg-brand-green' : 'bg-brand-fg/15'
            }`}
          >
            <span
              className={`bg-brand-fg absolute top-0.75 h-5.5 w-5.5 rounded-full transition-all ${
                alertsOn ? 'left-6.5' : 'left-0.75'
              }`}
            />
          </span>
        </button>
        {saveError && <p className="text-brand-red m-0 mt-3 font-sans text-[13px] font-medium">{saveError}</p>}

        {/* An alert is matched to a resident by distance: send-alert sends to
            opted-in residents within 3 km of the node that detected something.
            Without a location there is no distance to measure and the resident
            is skipped, so this is not an optional extra on the toggle above -
            it is the other half of it. */}
        <div className="border-brand-fg/10 mt-5 border-t pt-5">
          <p className="m-0 font-sans text-[14.5px] font-semibold">Your location</p>
          <p className="text-brand-fg/50 m-0 mt-1 font-sans text-[13px] leading-relaxed">
            {located
              ? 'Set. You will be alerted about detections within 3 km of here.'
              : 'Not set. Alerts are matched to within 3 km of where you are, so no alert can be sent until this is saved.'}
          </p>
          <p className="text-brand-fg/40 m-0 mt-1.5 font-sans text-[12.5px] leading-relaxed">
            Set this at home, not while you are away — it is the place you will be alerted about. The Forest
            Department can see it; it is used only to decide which alerts reach you, and you can remove it
            here at any time.
          </p>
          <div className="mt-3.5 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={captureLocation}
              disabled={locating || saving}
              className="border-brand-fg/20 hover:border-brand-gold text-brand-fg min-h-11 rounded-xl border bg-[#0B0D0B] px-4 font-sans text-[13.5px] font-semibold disabled:opacity-60"
            >
              {locating ? 'Finding you…' : located ? 'Update my location' : 'Use my current location'}
            </button>
            {located && (
              <button
                type="button"
                onClick={() => void clearLocation()}
                disabled={locating || saving}
                className="text-brand-fg/55 hover:text-brand-fg min-h-11 bg-transparent px-1 font-sans text-[13px] underline underline-offset-2 disabled:opacity-60"
              >
                Remove
              </button>
            )}
          </div>
          {fixError && <p className="text-brand-red m-0 mt-3 font-sans text-[13px] font-medium">{fixError}</p>}
        </div>
      </div>

      <p className="text-brand-fg/40 m-0 font-sans text-[12.5px] leading-relaxed">
        Emergency? Call the Forest Department control room: 1926. This dashboard shows safety information only.
      </p>
    </div>
  )
}
