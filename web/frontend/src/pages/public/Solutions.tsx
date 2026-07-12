import { SectorMapIllustration } from '@/components/SectorMapIllustration'
import { corridorSteps, otherWildlife, solutionsData } from '@/lib/content'

export function Solutions() {
  return (
    <>
      {/* HERO */}
      <section className="mx-auto max-w-6xl px-4 pt-14 pb-5 sm:px-6 md:pt-24 lg:px-8">
        <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">SOLUTIONS</p>
        <h1 className="mb-4.5 max-w-[16ch] font-serif text-[clamp(36px,5.5vw,64px)] leading-[1.05] font-normal">
          One system. Many jobs.
        </h1>
        <p className="text-brand-fg/72 max-w-[60ch] font-sans text-[17px] leading-relaxed">
          The same networked intelligence that stops a night raid on a paddy field can hold a herd off a highway,
          hear a chainsaw, or smell a fire coming.
        </p>
      </section>

      {/* SOLUTION CARDS */}
      <section className="mx-auto flex max-w-6xl flex-col gap-4.5 px-4 py-8 sm:px-6 md:py-12 lg:px-8">
        {solutionsData.map((s) => (
          <div
            key={s.title}
            className="border-brand-fg/9 grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] overflow-hidden rounded-2xl border bg-[#0B0D0B]"
          >
            <div
              className="bg-brand-panel min-h-60 bg-cover bg-center"
              style={{
                backgroundImage: `linear-gradient(120deg, rgba(7,13,10,0.2), rgba(7,13,10,0.75)), url('${s.img}')`,
              }}
            />
            <div className="p-6 sm:p-8 md:p-9">
              <h2 className="mb-4.5 font-serif text-[clamp(24px,2.8vw,32px)] leading-[1.15] font-normal">
                {s.title}
              </h2>
              <p className="text-brand-red mb-1.5 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                THE PROBLEM
              </p>
              <p className="text-brand-fg/70 mb-4 font-sans text-[14.5px] leading-relaxed">{s.problem}</p>
              <p className="text-brand-green mb-1.5 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                HOW ELETECT SOLVES IT
              </p>
              <p className="text-brand-fg/70 mb-4 font-sans text-[14.5px] leading-relaxed">{s.solution}</p>
              <p className="text-brand-gold mb-1.5 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                WHY IT'S BETTER
              </p>
              <p className="text-brand-fg/70 font-sans text-[14.5px] leading-relaxed">{s.why}</p>
            </div>
          </div>
        ))}
      </section>

      {/* OTHER WILDLIFE DETERRENCE */}
      <section className="mx-auto max-w-6xl px-4 pt-8 pb-14 sm:px-6 md:pb-24 lg:px-8">
        <p className="text-brand-green mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
          OTHER WILDLIFE DETERRENCE
        </p>
        <h2 className="mb-4 max-w-[24ch] font-serif text-[clamp(26px,3.4vw,38px)] leading-[1.15] font-normal">
          Elephants aren't the only raiders farmers deal with.
        </h2>
        <p className="text-brand-fg/68 mb-8 max-w-[64ch] font-sans text-[15.5px] leading-relaxed">
          The same sensing and adaptive deterrence protects crops from smaller, faster, and more frequent visitors,
          safely, without harming any animal.
        </p>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-3.5" data-reveal-stagger>
          {otherWildlife.map((w) => (
            <div
              key={w.name}
              className="border-brand-fg/9 hover:border-brand-gold/40 rounded-2xl border bg-[linear-gradient(160deg,rgba(15,29,20,0.5),rgba(11,13,11,0.2))] p-5.5 transition-all hover:-translate-y-1"
            >
              <div className="mb-3 text-2xl">{w.icon}</div>
              <h3 className="mb-2 font-sans text-base font-semibold">{w.name}</h3>
              <p className="text-brand-fg/65 font-sans text-sm leading-snug">{w.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* COORDINATED INTELLIGENCE / PHYSICAL AI */}
      <section className="bg-brand-bg-alt border-brand-fg/6 border-t">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24 lg:px-8">
          <p className="text-brand-gold mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
            COORDINATED INTELLIGENCE · PHYSICAL AI
          </p>
          <h2 className="mb-4 max-w-[22ch] font-serif text-[clamp(26px,3.6vw,42px)] leading-[1.15] font-normal">
            Nodes don't just detect, they cooperate.
          </h2>
          <p className="text-brand-fg/70 mb-9 max-w-[66ch] font-sans text-[15.5px] leading-relaxed">
            This is Physical AI in the field: neighbouring nodes share what they sense and jointly decide how to
            respond, quiet on the escape path, active behind the herd, so the animal is steered through a safe
            corridor back to the forest instead of just being scared in place.
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(460px,100%),1fr))] items-start gap-5">
            <div className="h-[clamp(280px,36vw,380px)]">
              <SectorMapIllustration label="COORDINATED CORRIDOR · LIVE DEMO" />
            </div>
            <div className="flex flex-col gap-2.5">
              {corridorSteps.map((c) => (
                <div
                  key={c.node}
                  className="border-brand-fg/9 bg-brand-panel/35 rounded-xl border px-4.5 py-4 transition-colors hover:border-brand-gold/40"
                >
                  <p className="text-brand-gold mb-1 font-mono text-xs font-bold tracking-[0.08em]">{c.node}</p>
                  <p className="text-brand-fg/70 font-sans text-sm leading-relaxed">{c.action}</p>
                </div>
              ))}
            </div>
          </div>
          <p className="text-brand-fg/40 mt-4 font-mono text-xs">
            Illustrative sector view. Exact node locations withheld for wildlife protection.
          </p>
        </div>
      </section>
    </>
  )
}
