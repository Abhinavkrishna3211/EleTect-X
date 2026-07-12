import { researchCards } from '@/lib/content'

export function Research() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">RESEARCH</p>
      <h1 className="mb-4.5 max-w-[18ch] font-serif text-[clamp(36px,5.5vw,64px)] leading-[1.05] font-normal">
        A long-term memory for the forest.
      </h1>
      <p className="text-brand-fg/72 mb-13 max-w-[60ch] font-sans text-[17px] leading-relaxed">
        Every detection, movement pattern, and deterrence outcome becomes structured data, a growing behavioural
        record for scientists and the Forest Department.
      </p>

      <div className="mb-13 grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3.5" data-reveal-stagger>
        {researchCards.map((r) => (
          <div
            key={r.title}
            className="border-brand-fg/9 rounded-2xl border bg-[linear-gradient(160deg,rgba(15,29,20,0.5),rgba(11,13,11,0.2))] p-6.5 transition-all hover:border-brand-gold/40 hover:-translate-y-1"
          >
            <h3 className="mb-2.5 font-sans text-lg font-semibold">{r.title}</h3>
            <p className="text-brand-fg/65 font-sans text-[14.5px] leading-relaxed">{r.body}</p>
          </div>
        ))}
      </div>

      <div className="border-brand-gold/30 rounded-2xl border bg-[rgba(226,161,60,0.05)] p-7">
        <h3 className="mb-2.5 font-serif text-[22px] leading-none font-normal">Data ethics</h3>
        <p className="text-brand-fg/70 max-w-[75ch] font-sans text-[14.5px] leading-relaxed">
          Exact node and animal locations are shared only with the Forest Department. Public alerts carry direction
          and area, never coordinates that could aid poaching. Resident data is opt-in, minimal, and never sold.
        </p>
      </div>
    </section>
  )
}
