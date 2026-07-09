import { deployPhases } from '@/lib/content'

export function Deployments() {
  return (
    <section className="mx-auto max-w-6xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">DEPLOYMENTS</p>
      <h1 className="mb-4.5 max-w-[18ch] font-serif text-[clamp(36px,5.5vw,64px)] leading-[1.05] font-normal">
        Proving it where it matters most.
      </h1>
      <p className="text-brand-fg/72 mb-10 max-w-[60ch] font-sans text-[17px] leading-relaxed">
        EleTect is in field deployment with the Kerala Forest Department around Kothamangalam and the Kuttampuzha
        forest range, in the conflict hotspots where the state declared human–wildlife conflict a disaster in 2024.
      </p>

      <div className="border-brand-fg/10 relative h-[clamp(320px,50vw,460px)] overflow-hidden rounded-2xl border bg-[#0B0D0B]">
        <div className="absolute inset-0 grid place-items-center">
          <div className="text-center">
            <p className="text-brand-fg/30 font-mono text-[11px] tracking-[0.14em]">
              KOTHAMANGALAM PILOT · LIVE VIEW
            </p>
            <p className="text-brand-fg/45 mt-2 font-sans text-sm">Sector map view, live in the dashboard.</p>
          </div>
        </div>
      </div>
      <p className="text-brand-fg/40 mt-3 mb-12 font-mono text-xs">
        Illustrative sector view. Exact node locations withheld for wildlife protection.
      </p>

      <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-3.5">
        {deployPhases.map((d) => (
          <div
            key={d.title}
            className="border-brand-fg/9 rounded-2xl border p-6"
            style={{ background: d.bg }}
          >
            <p
              className="mb-2 font-mono text-[11.5px] font-semibold tracking-[0.14em]"
              style={{ color: d.tagColor }}
            >
              {d.tag}
            </p>
            <h3 className="mb-2.5 font-sans text-[17px] font-semibold">{d.title}</h3>
            <p className="text-brand-fg/65 font-sans text-[14.5px] leading-relaxed">{d.body}</p>
          </div>
        ))}
      </div>
    </section>
  )
}
