import { team } from '@/lib/content'

const recognition = [
  'IEEE IAS CMD Humanitarian Award 2025',
  'Amarnath Raja Humanitarian Technology Award 2025',
  'Field deployment in progress with the Kerala Forest Department',
]

export function About() {
  return (
    <section className="mx-auto max-w-3xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">ABOUT</p>
      <h1 className="mb-5.5 font-serif text-[clamp(36px,5.5vw,64px)] leading-[1.05] font-normal">
        Built where the conflict lives.
      </h1>
      <p className="text-brand-fg/75 mb-4 font-sans text-[17px] leading-relaxed">
        EleTect began in Kothamangalam, Kerala, where roughly 500 people are killed every year in India in
        human–elephant conflict, and around 100 elephants die from electrocution, collisions, poisoning, and
        retaliation. We believe both numbers can go to zero, without a single harmed animal.
      </p>
      <p className="text-brand-fg/75 mb-13 font-sans text-[17px] leading-relaxed">
        Our mission: protect farms, forests, and the future, with technology that respects the wild.
      </p>

      <h2 className="mb-6 font-serif text-[clamp(24px,3vw,34px)] font-normal">Team</h2>
      <div className="mb-13 grid grid-cols-[repeat(auto-fit,minmax(240px,1fr))] gap-3.5" data-reveal-stagger>
        {team.map((m) => (
          <div key={m.name} className="border-brand-fg/9 rounded-2xl border bg-[#0B0D0B] p-6.5 transition-all hover:border-brand-gold/40 hover:-translate-y-1">
            <div className="mb-4 grid h-16 w-16 place-items-center rounded-full bg-[linear-gradient(140deg,#2F5E3F,#0F1D14)]">
              <span className="text-brand-gold font-serif text-2xl font-normal">{m.initials}</span>
            </div>
            <h3 className="mb-1 font-sans text-[17px] font-semibold">{m.name}</h3>
            <p className="text-brand-fg/50 font-mono text-[13px] font-medium">{m.role}</p>
          </div>
        ))}
      </div>

      <h2 className="mb-5 font-serif text-[clamp(24px,3vw,34px)] font-normal">Recognition</h2>
      <ul className="flex flex-col gap-2.5">
        {recognition.map((r) => (
          <li
            key={r}
            className="border-brand-fg/10 rounded-xl border bg-brand-panel/40 px-4.5 py-4 font-sans text-[14.5px] font-semibold transition-colors hover:border-brand-gold/40"
          >
            {r}
          </li>
        ))}
      </ul>
    </section>
  )
}
