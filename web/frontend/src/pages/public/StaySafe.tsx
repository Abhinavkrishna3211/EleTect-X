import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { supabase } from '@/lib/supabase'
import { useAlertsOptIn } from '@/hooks/useAlertsOptIn'
import { deriveAreaRisk, riskDisplay, type AreaRiskRow } from '@/lib/risk'

// The channel is whatever send-alert has enabled — email today, SMS once DLT
// registration clears. The copy stays channel-neutral rather than promising SMS
// the backend does not currently send.
const howItWorks = [
  { n: '1 · Detection', body: 'The network senses and confirms an animal near your area.' },
  { n: '2 · Alert in seconds', body: 'You are alerted with direction and simple safety guidance.' },
  { n: '3 · All clear', body: "When the animal returns to the forest, you're told it's safe." },
]

export function StaySafe() {
  const { signedIn, enabled, saving, error, setEnabled } = useAlertsOptIn()
  const [riskRows, setRiskRows] = useState<AreaRiskRow[] | null>(null)

  // public_area_risk is granted to anon precisely so this page can show a real
  // figure to a resident who has not signed in. Aggregate counts only.
  useEffect(() => {
    let cancelled = false
    supabase
      .from('public_area_risk')
      .select('day, detections')
      .then(({ data, error }) => {
        if (!cancelled && !error) setRiskRows((data ?? []) as AreaRiskRow[])
      })
    return () => {
      cancelled = true
    }
  }, [])

  const display = riskRows ? riskDisplay(deriveAreaRisk(riskRows)) : null

  return (
    <section className="mx-auto max-w-2xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">STAY SAFE</p>
      <h1 className="mb-3.5 font-serif text-[clamp(34px,5vw,56px)] leading-[1.08] font-normal">
        Know before you step outside.
      </h1>
      <p className="text-brand-fg/70 mb-9 font-sans text-base leading-relaxed">
        If EleTect detects a wild animal near a village, opted-in residents are alerted within seconds —
        direction, distance band, and what to do.
      </p>

      <div className="border-brand-fg/10 mb-4 flex flex-wrap items-center gap-4.5 rounded-2xl border bg-[#0B0D0B] p-6">
        <div
          className={`grid h-14.5 w-14.5 shrink-0 place-items-center rounded-full border-2 text-2xl ${
            display ? display.border : 'border-brand-fg/20'
          }`}
          style={{ background: display?.background }}
        >
          {display ? display.dot : '⋯'}
        </div>
        <div className="min-w-50 flex-1">
          <p className="text-brand-fg/55 mb-1 font-mono text-xs font-semibold tracking-[0.12em]">
            CURRENT AREA RISK · KOTHAMANGALAM SECTOR
          </p>
          <p
            className={`font-sans text-[19px] font-semibold ${display ? display.color : 'text-brand-fg/45'}`}
          >
            {display ? display.label : 'Checking current area status…'}
          </p>
        </div>
      </div>

      <div className="mb-9 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3" data-reveal-stagger>
        {howItWorks.map((s) => (
          <div key={s.n} className="border-brand-fg/9 rounded-xl border bg-brand-panel/35 p-5 transition-all hover:border-brand-gold/40 hover:-translate-y-1">
            <p className="mb-1.5 font-sans text-[15px] font-semibold">{s.n}</p>
            <p className="text-brand-fg/60 font-sans text-[13.5px] leading-snug">{s.body}</p>
          </div>
        ))}
      </div>

      {/* Signed out: send them to signup rather than collecting a phone number
          here. There is no anonymous opt-in store, and a form that accepts
          contact details and drops them tells the resident they are covered when
          nothing was recorded. Signup + email confirmation is the consent record. */}
      {!signedIn ? (
        <div className="border-brand-gold/35 rounded-[18px] border bg-[rgba(226,161,60,0.05)] p-7">
          <h2 className="mb-1.5 font-serif text-[26px] font-normal">Get safety alerts</h2>
          <p className="text-brand-fg/65 mb-5.5 font-sans text-sm leading-relaxed">
            Free for residents of covered areas. Create an account and turn alerts on — that is all it takes.
          </p>
          <Link
            to="/signup"
            className="bg-brand-gold hover:bg-brand-gold-hover flex min-h-12 items-center justify-center rounded-full px-6 py-4 font-sans text-[15px] font-semibold text-[#0B140E]"
          >
            Create an account
          </Link>
          <p className="text-brand-fg/45 mt-3.5 font-sans text-[12.5px] leading-relaxed">
            Already have one?{' '}
            <Link to="/login" className="text-brand-gold underline underline-offset-2">
              Sign in
            </Link>{' '}
            and turn on alerts. Your contact details and location are used only to alert you, never shared or
            sold, and you can turn alerts off at any time.
          </p>
        </div>
      ) : (
        <div className="border-brand-gold/35 rounded-[18px] border bg-[rgba(226,161,60,0.05)] p-7">
          <h2 className="mb-1.5 font-serif text-[26px] font-normal">Your safety alerts</h2>
          <p className="text-brand-fg/65 mb-5.5 font-sans text-sm leading-relaxed">
            {enabled
              ? 'On — you will be alerted when wildlife is detected near you.'
              : 'Off — turn them on to be alerted about wildlife near you.'}
          </p>
          <button
            type="button"
            onClick={() => setEnabled(!enabled)}
            disabled={saving}
            aria-pressed={enabled}
            className="border-brand-fg/15 flex min-h-13 w-full items-center justify-between gap-3.5 rounded-xl border bg-[#0B0D0B] px-4 py-3.5 disabled:opacity-60"
          >
            <span className="text-brand-fg text-left font-sans text-[14.5px] font-semibold">
              Alerts for detections near me
            </span>
            <span
              className={`relative h-6.5 w-11.5 shrink-0 rounded-full transition-colors ${
                enabled ? 'bg-brand-green' : 'bg-brand-fg/20'
              }`}
            >
              <span
                className={`bg-brand-fg absolute top-0.75 h-5 w-5 rounded-full transition-all ${
                  enabled ? 'left-6' : 'left-0.75'
                }`}
              />
            </span>
          </button>
          {error && <p className="text-brand-red mt-3 font-sans text-[13px] font-medium">{error}</p>}
          <p className="text-brand-fg/45 mt-3.5 font-sans text-[12.5px] leading-relaxed">
            Your contact details and location are used only to alert you, never shared or sold. Turn alerts off
            here at any time.
          </p>
        </div>
      )}
    </section>
  )
}
