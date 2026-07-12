import { Link } from 'react-router-dom'
import { IMG, awards, compareRows, solutionCards, stats, steps } from '@/lib/content'

export function Home() {
  return (
    <>
      {/* HERO */}
      <section className="relative flex min-h-svh flex-col justify-end overflow-hidden bg-brand-bg">
        <div
          className="absolute inset-0 bg-cover bg-position-[center_40%] brightness-[0.42] saturate-[0.85]"
          style={{ backgroundImage: `url('${IMG.hero}')` }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,13,10,0.55)_0%,rgba(7,13,10,0.15)_40%,rgba(7,13,10,0.92)_88%,#070D0A_100%)]" />
        <div className="relative mx-auto w-full max-w-6xl px-4 pt-32 pb-12 sm:px-6 md:pb-24 lg:px-8">
          <div className="border-brand-green/40 bg-[#0F1D14]/60 mb-5 inline-flex items-center gap-2 rounded-full border px-3.5 py-1.5">
            <span className="bg-brand-green h-1.5 w-1.5 animate-pulse rounded-full" />
            <span className="text-[#9DC7AC] font-mono text-[11.5px] font-semibold tracking-[0.14em]">
              FIELD-TESTED WITH THE KERALA FOREST DEPARTMENT
            </span>
          </div>
          <h1 className="mb-5 max-w-[13ch] font-serif text-[clamp(44px,7.5vw,92px)] leading-[1.02] font-normal tracking-tight">
            The forest warns you <em className="text-brand-gold not-italic">first</em>.
          </h1>
          <p className="text-brand-fg/75 mb-8 max-w-[56ch] font-sans text-[clamp(16px,1.6vw,19px)] leading-relaxed">
            EleTect is an autonomous, solar-powered AI system that detects wildlife early, warns people instantly,
            and deters animals safely, day and night, even without the internet.
          </p>
          <div className="flex flex-wrap gap-3.5">
            <Link
              to="/technology"
              className="bg-brand-gold hover:bg-brand-gold-hover inline-flex min-h-11 items-center rounded-full px-7 py-3.5 font-sans text-[15px] font-semibold text-[#0B140E]"
            >
              Explore the platform
            </Link>
            <Link
              to="/dashboard"
              className="border-brand-fg/28 text-brand-fg hover:border-brand-fg inline-flex min-h-11 items-center rounded-full border px-7 py-3.5 font-sans text-[15px] font-semibold"
            >
              See it live →
            </Link>
          </div>
        </div>
      </section>

      {/* STATS BAND */}
      <section className="border-brand-fg/6 bg-brand-bg-alt border-y">
        <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-20 lg:px-8">
          <p className="text-brand-gold mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
            THE CRISIS, BY THE NUMBERS
          </p>
          <h2 className="mb-10 max-w-[24ch] font-serif text-[clamp(28px,3.6vw,44px)] leading-[1.15] font-normal">
            Human-wildlife conflict is now an official disaster in Kerala.
          </h2>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,220px),1fr))] gap-3" data-reveal-stagger>
            {stats.map((s) => (
              <div
                key={s.label}
                className="border-brand-fg/10 hover:border-brand-gold/40 bg-brand-bg-alt rounded-2xl border p-6 transition-all hover:-translate-y-1"
              >
                <div className="font-serif text-[clamp(38px,4.5vw,56px)] leading-none">{s.value}</div>
                <div className="text-brand-fg/62 mt-2.5 font-sans text-[13.5px] leading-snug font-medium">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
          <p className="text-brand-fg/40 mt-4.5 font-mono text-xs">
            Government and published figures, 2019-2024. Most fatal encounters happen at night, when people never
            see the animal coming.
          </p>
        </div>
      </section>

      {/* HOW IT WORKS */}
      <section className="bg-brand-bg">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24 lg:px-8">
          <p className="text-brand-green mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
            ONE SYSTEM, SEVEN INSTINCTS
          </p>
          <h2 className="mb-4 max-w-[20ch] font-serif text-[clamp(30px,4vw,48px)] leading-[1.1] font-normal">
            It senses, decides, and acts, like a ranger who never sleeps.
          </h2>
          <p className="text-brand-fg/68 mb-11 max-w-[60ch] font-sans text-base leading-relaxed">
            Every node runs fully offline on solar power. No internet is needed to detect, decide, or deter.
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3.5" data-reveal-stagger>
            {steps.map((st) => (
              <div
                key={st.n}
                className="border-brand-fg/9 hover:border-brand-gold/45 rounded-2xl border bg-[linear-gradient(160deg,rgba(15,29,20,0.55),rgba(11,13,11,0.3))] p-6 transition-all hover:-translate-y-1"
              >
                <div className="mb-2.5 flex items-baseline gap-2.5">
                  <span className="text-brand-gold font-mono text-xs font-semibold">{st.n}</span>
                  <h3 className="font-sans text-[17px] font-semibold tracking-wide">{st.title}</h3>
                </div>
                <p className="text-brand-fg/65 font-sans text-sm leading-relaxed">{st.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* IMAGE INTERLUDE */}
      <section className="relative min-h-[52vh] overflow-hidden bg-[#0F1D14]">
        <div
          className="absolute inset-0 bg-cover bg-position-[center_60%] brightness-[0.55] saturate-90"
          style={{ backgroundImage: `url('${IMG.interlude}')` }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,#070D0A_0%,rgba(7,13,10,0.1)_30%,rgba(7,13,10,0.1)_70%,#070D0A_100%)]" />
        <div className="relative mx-auto flex min-h-[52vh] max-w-6xl items-center px-4 py-24 sm:px-6 lg:px-8">
          <blockquote className="max-w-[26ch] font-serif text-[clamp(22px,3vw,34px)] leading-[1.35] font-normal italic [text-shadow:0_2px_24px_rgba(0,0,0,0.6)]">
            "Deterrence that never repeats itself, so animals never learn to ignore it."
          </blockquote>
        </div>
      </section>

      {/* COMPARISON */}
      <section className="border-brand-fg/6 bg-brand-bg-alt border-t">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24 lg:px-8">
          <p className="text-brand-gold mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
            WHY EXISTING TOOLS FAIL
          </p>
          <h2 className="mb-10 max-w-[26ch] font-serif text-[clamp(28px,3.6vw,44px)] leading-[1.15] font-normal">
            Alarms get ignored. Fences get bypassed. EleTect adapts.
          </h2>
          <div className="border-brand-fg/9 overflow-x-auto rounded-2xl border">
            <div className="min-w-160">
              <div className="bg-[#0F1D14]/60 border-brand-fg/9 grid grid-cols-[2fr_1fr_1fr_1fr_1fr] border-b">
                <div className="text-brand-fg/55 px-4.5 py-3.5 font-mono text-xs font-semibold tracking-wide">
                  CAPABILITY
                </div>
                <div className="text-brand-gold px-3 py-3.5 text-center font-mono text-[12.5px] font-bold tracking-wide">
                  ELETECT
                </div>
                <div className="text-brand-fg/50 px-3 py-3.5 text-center font-mono text-xs font-semibold tracking-wide">
                  FIXED ALARMS
                </div>
                <div className="text-brand-fg/50 px-3 py-3.5 text-center font-mono text-xs font-semibold tracking-wide">
                  FENCES
                </div>
                <div className="text-brand-fg/50 px-3 py-3.5 text-center font-mono text-xs font-semibold tracking-wide">
                  CAMERA TRAPS
                </div>
              </div>
              {compareRows.map((r) => (
                <div
                  key={r.cap}
                  className="border-brand-fg/6 grid grid-cols-[2fr_1fr_1fr_1fr_1fr] border-b last:border-b-0"
                >
                  <div className="text-brand-fg/85 px-4.5 py-4 font-sans text-sm font-medium">{r.cap}</div>
                  <div className="text-brand-green bg-brand-green/6 px-3 py-4 text-center font-sans text-sm font-semibold">
                    {r.us}
                  </div>
                  <div className="text-brand-fg/45 px-3 py-4 text-center font-sans text-sm font-medium">
                    {r.alarm}
                  </div>
                  <div className="text-brand-fg/45 px-3 py-4 text-center font-sans text-sm font-medium">
                    {r.fence}
                  </div>
                  <div className="text-brand-fg/45 px-3 py-4 text-center font-sans text-sm font-medium">{r.cam}</div>
                </div>
              ))}
            </div>
          </div>
          <p className="text-brand-fg/55 mt-4.5 max-w-[70ch] font-sans text-[13.5px] leading-relaxed">
            Electric and rail fences cost lakhs per kilometre and harm other wildlife. EleTect protects the same
            boundary at roughly <strong className="text-brand-gold font-semibold">1/10th the cost</strong>, and
            scales to thousands of nodes.
          </p>
        </div>
      </section>

      {/* SOLUTIONS PREVIEW */}
      <section className="bg-brand-bg">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24 lg:px-8">
          <div className="mb-10 flex flex-wrap items-end justify-between gap-5">
            <div>
              <p className="text-brand-green mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
                ONE PLATFORM, MANY JOBS
              </p>
              <h2 className="font-serif text-[clamp(28px,3.6vw,44px)] leading-[1.15] font-normal">
                What EleTect protects
              </h2>
            </div>
            <Link to="/solutions" className="text-brand-gold font-sans text-sm font-semibold">
              All solutions →
            </Link>
          </div>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-3.5" data-reveal-stagger>
            {solutionCards.map((s) => (
              <Link
                key={s.title}
                to="/solutions"
                className="border-brand-fg/9 hover:border-brand-gold/50 bg-brand-bg-alt text-brand-fg block overflow-hidden rounded-2xl border transition-all hover:-translate-y-1"
              >
                <div
                  className="h-37.5 bg-cover bg-center bg-[#0F1D14]"
                  style={{
                    backgroundImage: `linear-gradient(180deg, rgba(7,13,10,0) 40%, rgba(7,13,10,0.85)), url('${s.img}')`,
                  }}
                />
                <div className="px-5.5 pt-5 pb-6">
                  <h3 className="mb-2 font-sans text-[17px] font-semibold">{s.title}</h3>
                  <p className="text-brand-fg/60 font-sans text-sm leading-relaxed">{s.tease}</p>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* AWARDS */}
      <section className="border-brand-fg/6 border-t bg-[#0F1D14]">
        <div className="mx-auto grid max-w-6xl grid-cols-[repeat(auto-fit,minmax(260px,1fr))] items-center gap-6 px-4 py-12 sm:px-6 md:py-16 lg:px-8">
          <div>
            <p className="text-brand-gold mb-1.5 font-mono text-xs font-semibold tracking-[0.18em]">RECOGNITION</p>
            <h2 className="font-serif text-[clamp(24px,3vw,34px)] leading-[1.2] font-normal">
              Awarded for humanitarian technology
            </h2>
          </div>
          <div className="flex flex-col gap-3" data-reveal-stagger>
            {awards.map((a) => (
              <div
                key={a.label}
                className="border-brand-fg/12 bg-brand-bg/40 flex items-center gap-3 rounded-xl border px-4.5 py-4 transition-all hover:border-brand-gold/40 hover:-translate-y-1"
              >
                <span className="border-brand-gold/25 text-brand-gold grid h-9 w-9 shrink-0 place-items-center rounded-lg border bg-[rgba(226,161,60,0.08)]">
                  <a.icon size={17} strokeWidth={1.75} aria-hidden />
                </span>
                <span className="font-sans text-[14.5px] font-semibold">{a.label}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-brand-bg">
        <div className="mx-auto max-w-3xl px-4 py-20 text-center sm:px-6 md:py-32 lg:px-8">
          <h2 className="mb-4.5 font-serif text-[clamp(32px,4.6vw,56px)] leading-[1.1] font-normal">
            Protecting farms, forests,
            <br />
            and the <em className="text-brand-gold not-italic">future</em>.
          </h2>
          <p className="text-brand-fg/65 mb-8 font-sans text-base leading-relaxed">
            For Forest Departments, farmers, researchers and partners.
          </p>
          <div className="flex flex-wrap justify-center gap-3.5">
            <Link
              to="/contact"
              className="bg-brand-gold hover:bg-brand-gold-hover rounded-full px-7.5 py-3.5 font-sans text-[15px] font-semibold text-[#0B140E]"
            >
              Talk to us
            </Link>
            <Link
              to="/stay-safe"
              className="border-brand-fg/28 hover:border-brand-fg rounded-full border px-7.5 py-3.5 font-sans text-[15px] font-semibold"
            >
              Get safety alerts
            </Link>
          </div>
        </div>
      </section>
    </>
  )
}
