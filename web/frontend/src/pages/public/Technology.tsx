import { Plus } from 'lucide-react'

import { IMG, products, techPillars } from '@/lib/content'

export function Technology() {
  return (
    <>
      {/* HERO */}
      <section className="bg-brand-bg-alt border-brand-fg/6 relative overflow-hidden border-b">
        <div
          className="absolute inset-0 bg-cover bg-center brightness-[0.3]"
          style={{ backgroundImage: `url('${IMG.techHero}')` }}
        />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(7,13,10,0.5)_0%,#070D0A_95%)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-24 sm:px-6 md:py-32 lg:px-8">
          <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">TECHNOLOGY</p>
          <h1 className="mb-4.5 max-w-[18ch] font-serif text-[clamp(36px,5.5vw,64px)] leading-[1.05] font-normal">
            Physical AI that earns its place in the forest.
          </h1>
          <p className="text-brand-fg/72 max-w-[58ch] font-sans text-[17px] leading-relaxed">
            EleTect doesn't just detect, it reasons across three senses, explains every decision, and learns what
            works at each site.
          </p>
        </div>
      </section>

      {/* PILLARS */}
      <section className="bg-brand-bg">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 md:py-24 lg:px-8">
          <div className="mb-15 grid grid-cols-[repeat(auto-fit,minmax(290px,1fr))] gap-3.5" data-reveal-stagger>
            {techPillars.map((t) => (
              <div
                key={t.title}
                className="border-brand-fg/9 rounded-2xl border bg-[linear-gradient(160deg,rgba(15,29,20,0.5),rgba(11,13,11,0.2))] p-6.5 transition-all hover:border-brand-gold/40 hover:-translate-y-1"
              >
                <div className="border-brand-gold/25 text-brand-gold mb-3.5 grid h-11 w-11 place-items-center rounded-xl border bg-[rgba(226,161,60,0.08)]">
                  <t.icon size={20} strokeWidth={1.75} aria-hidden />
                </div>
                <h3 className="mb-2.5 font-sans text-lg font-semibold">{t.title}</h3>
                <p className="text-brand-fg/65 font-sans text-[14.5px] leading-relaxed">{t.body}</p>
              </div>
            ))}
          </div>

          {/* PRODUCT LINE */}
          <p className="text-brand-green mb-2 font-mono text-xs font-semibold tracking-[0.18em]">PRODUCT LINE</p>
          <h2 className="mb-7 max-w-[22ch] font-serif text-[clamp(26px,3.4vw,40px)] leading-[1.15] font-normal">
            One platform, purpose-built hardware.
          </h2>
          <div className="mb-16 grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4" data-reveal-stagger>
            {products.map((p) =>
              p.placeholder ? (
                <div
                  key={p.id}
                  className="border-brand-fg/20 bg-brand-fg/1.5 flex min-h-70 flex-col items-start justify-center gap-2.5 rounded-[18px] border-[1.5px] border-dashed p-7"
                >
                  <Plus className="text-brand-fg opacity-60" size={24} strokeWidth={1.75} aria-hidden />
                  <p className="text-brand-fg/40 font-mono text-[11.5px] font-semibold tracking-[0.14em]">{p.tag}</p>
                  <h3 className="text-brand-fg/55 font-serif text-[22px] leading-none font-normal">{p.name}</h3>
                  <p className="text-brand-fg/45 font-sans text-sm leading-relaxed">{p.body}</p>
                </div>
              ) : (
                <div
                  key={p.id}
                  className="border-brand-fg/9 hover:border-brand-gold/40 overflow-hidden rounded-[18px] border bg-[#0B0D0B] transition-all hover:-translate-y-1"
                >
                  <div
                    className="h-42.5 bg-cover bg-center"
                    style={{
                      backgroundImage: `linear-gradient(180deg, rgba(7,13,10,0) 40%, rgba(7,13,10,0.9)), url('${p.img}')`,
                    }}
                  />
                  <div className="p-5.5">
                    <p className="text-brand-gold mb-1.5 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                      {p.tag}
                    </p>
                    <h3 className="mb-2.5 font-serif text-2xl leading-none font-normal">{p.name}</h3>
                    <p className="text-brand-fg/65 mb-3.5 font-sans text-sm leading-relaxed">{p.body}</p>
                    <ul className="flex flex-col gap-1.5 pl-4.5">
                      {p.specs.map((sp) => (
                        <li key={sp} className="text-brand-fg/55 list-disc font-sans text-[13px] leading-relaxed">
                          {sp}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ),
            )}
          </div>

          {/* EXPLAINABLE AI */}
          <p className="text-brand-gold mb-2 font-mono text-xs font-semibold tracking-[0.18em]">
            EXPLAINABLE BY DESIGN
          </p>
          <h2 className="mb-7 max-w-[24ch] font-serif text-[clamp(26px,3.4vw,40px)] leading-[1.15] font-normal">
            Every decision shows its reasoning.
          </h2>
          <div className="border-brand-fg/12 max-w-160 overflow-hidden rounded-2xl border bg-[#0B0D0B]">
            <div className="border-brand-fg/8 flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3.5">
              <span className="text-brand-fg/60 font-mono text-xs font-semibold tracking-wide">
                EVENT E-2231 · NODE S7-04 · 21:47 IST
              </span>
              <span className="bg-brand-green rounded-full px-2.5 py-1 font-mono text-[11px] font-bold text-[#0B140E]">
                RESOLVED
              </span>
            </div>
            <div className="flex flex-col gap-3 p-5">
              <div className="flex items-center gap-3">
                <span className="text-brand-green font-bold">✔</span>
                <span className="font-sans text-[14.5px] font-medium">Ground vibration: heavy footstep pattern</span>
                <span className="text-brand-green ml-auto font-mono text-[13px] font-semibold">97%</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-brand-green font-bold">✔</span>
                <span className="font-sans text-[14.5px] font-medium">Audio: elephant rumble signature</span>
                <span className="text-brand-green ml-auto font-mono text-[13px] font-semibold">91%</span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-brand-green font-bold">✔</span>
                <span className="font-sans text-[14.5px] font-medium">Vision: elephant confirmed (night-capable)</span>
                <span className="text-brand-green ml-auto font-mono text-[13px] font-semibold">94%</span>
              </div>
              <div className="border-brand-fg/15 flex flex-col gap-1.5 border-t border-dashed pt-3.5">
                <span className="text-brand-gold font-sans text-[14.5px] font-semibold">
                  → Decision: adaptive deterrent activated
                </span>
                <span className="text-brand-fg/65 font-sans text-sm font-medium">
                  Outcome: herd retreated toward forest · verified by observation
                </span>
              </div>
            </div>
          </div>
          <p className="text-brand-fg/55 mt-4 max-w-[64ch] font-sans text-[13.5px] leading-relaxed">
            Three sensing modalities, ground, audio, vision, are fused into one confidence score. Officers see{' '}
            <em className="not-italic font-semibold">why</em> the system acted, not just that it did.
          </p>
        </div>
      </section>
    </>
  )
}
