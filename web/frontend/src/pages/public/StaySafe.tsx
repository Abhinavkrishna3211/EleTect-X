import { useState } from 'react'

const howItWorks = [
  { n: '1 · Detection', body: 'The network senses and confirms an animal near your area.' },
  { n: '2 · Alert in seconds', body: 'You get an SMS with direction and simple safety guidance.' },
  { n: '3 · All clear', body: "When the animal returns to the forest, you're told it's safe." },
]

export function StaySafe() {
  const [optedIn, setOptedIn] = useState(false)
  const [smsEnabled, setSmsEnabled] = useState(false)
  const [phone, setPhone] = useState('')
  const [village, setVillage] = useState('')
  const [error, setError] = useState('')

  return (
    <section className="mx-auto max-w-2xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">STAY SAFE</p>
      <h1 className="mb-3.5 font-serif text-[clamp(34px,5vw,56px)] leading-[1.08] font-normal">
        Know before you step outside.
      </h1>
      <p className="text-brand-fg/70 mb-9 font-sans text-base leading-relaxed">
        If EleTect detects a wild animal near a village, opted-in residents get an SMS within seconds, direction,
        distance band, and what to do. No app needed.
      </p>

      <div className="border-brand-fg/10 mb-4 flex flex-wrap items-center gap-4.5 rounded-2xl border bg-[#0B0D0B] p-6">
        <div className="border-brand-green grid h-14.5 w-14.5 flex-shrink-0 place-items-center rounded-full border-2 bg-[rgba(95,169,124,0.12)] text-2xl">
          🟢
        </div>
        <div className="min-w-50 flex-1">
          <p className="text-brand-fg/55 mb-1 font-mono text-xs font-semibold tracking-[0.12em]">
            CURRENT AREA RISK · KOTHAMANGALAM SECTOR
          </p>
          <p className="text-brand-green font-sans text-[19px] font-semibold">Low · No wildlife detected near villages</p>
        </div>
        <span className="text-brand-fg/40 font-mono text-[11.5px] font-medium">Updated 2 min ago</span>
      </div>

      <div className="mb-9 grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
        {howItWorks.map((s) => (
          <div key={s.n} className="border-brand-fg/9 rounded-xl border bg-brand-panel/35 p-5">
            <p className="mb-1.5 font-sans text-[15px] font-semibold">{s.n}</p>
            <p className="text-brand-fg/60 font-sans text-[13.5px] leading-snug">{s.body}</p>
          </div>
        ))}
      </div>

      {!optedIn ? (
        <div className="border-brand-gold/35 rounded-[18px] border bg-[rgba(226,161,60,0.05)] p-7">
          <h2 className="mb-1.5 font-serif text-[26px] font-normal">Enable SMS alerts</h2>
          <p className="text-brand-fg/65 mb-5.5 font-sans text-sm leading-relaxed">
            Free for residents of covered areas.
          </p>
          <form
            className="flex flex-col gap-3.5"
            onSubmit={(e) => {
              e.preventDefault()
              if (!phone.trim()) {
                setError('Enter a phone number to continue.')
                return
              }
              setError('')
              setOptedIn(true)
            }}
          >
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone number (+91…)"
              type="tel"
              className="border-brand-fg/15 text-brand-fg placeholder:text-brand-fg/40 min-h-11 rounded-xl border bg-[#0B0D0B] px-4 py-3.5 text-[15px]"
            />
            <input
              value={village}
              onChange={(e) => setVillage(e.target.value)}
              placeholder="Village / panchayat (optional)"
              className="border-brand-fg/15 text-brand-fg placeholder:text-brand-fg/40 min-h-11 rounded-xl border bg-[#0B0D0B] px-4 py-3.5 text-[15px]"
            />
            <button
              type="button"
              onClick={() => setSmsEnabled((v) => !v)}
              className="border-brand-fg/15 flex min-h-13 items-center justify-between gap-3.5 rounded-xl border bg-[#0B0D0B] px-4 py-3.5"
            >
              <span className="text-brand-fg text-left font-sans text-[14.5px] font-semibold">
                SMS alerts for detections near me
              </span>
              <span
                className={`relative h-6.5 w-11.5 flex-shrink-0 rounded-full transition-colors ${smsEnabled ? 'bg-brand-green' : 'bg-brand-fg/20'}`}
              >
                <span
                  className={`bg-brand-fg absolute top-0.75 h-5 w-5 rounded-full transition-all ${smsEnabled ? 'left-6' : 'left-0.75'}`}
                />
              </span>
            </button>
            {error && <p className="text-brand-red font-sans text-[13px] font-medium">{error}</p>}
            <button
              type="submit"
              className="bg-brand-gold hover:bg-brand-gold-hover min-h-12 rounded-full py-4 font-sans text-[15px] font-semibold text-[#0B140E]"
            >
              Sign me up
            </button>
            <p className="text-brand-fg/45 font-sans text-[12.5px] leading-relaxed">
              By signing up you consent to receive safety SMS from EleTect. Your number and location are used only
              for alerts, never shared or sold. Opt out anytime by replying STOP.
            </p>
          </form>
        </div>
      ) : (
        <div className="border-brand-green/40 rounded-[18px] border bg-[rgba(95,169,124,0.08)] p-8 text-center">
          <div className="mb-3 text-3xl">✅</div>
          <h3 className="mb-2 font-serif text-2xl leading-none font-normal">You're covered.</h3>
          <p className="text-brand-fg/65 font-sans text-[14.5px] leading-relaxed">
            Safety alerts enabled for {phone}. Reply STOP to any message to opt out.
          </p>
        </div>
      )}
    </section>
  )
}
