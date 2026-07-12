import { useState } from 'react'

export function Contact() {
  const [sent, setSent] = useState(false)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')

  return (
    <section className="mx-auto max-w-xl px-4 py-14 sm:px-6 md:py-24 lg:px-8">
      <p className="text-brand-green mb-2.5 font-mono text-xs font-semibold tracking-[0.18em]">CONTACT</p>
      <h1 className="mb-3.5 font-serif text-[clamp(34px,5vw,56px)] leading-[1.08] font-normal">
        For Forest Departments, farmers, researchers and partners.
      </h1>
      <p className="text-brand-fg/70 mb-9 font-sans text-base leading-relaxed">
        Tell us about your site, we'll respond within two working days.
      </p>

      {!sent ? (
        <form
          className="flex flex-col gap-3.5"
          onSubmit={(e) => {
            e.preventDefault()
            setSent(true)
          }}
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            required
            className="border-brand-fg/15 text-brand-fg placeholder:text-brand-fg/40 min-h-11 rounded-xl border bg-[#0B0D0B] px-4 py-3.5 text-[15px]"
          />
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            type="email"
            required
            className="border-brand-fg/15 text-brand-fg placeholder:text-brand-fg/40 min-h-11 rounded-xl border bg-[#0B0D0B] px-4 py-3.5 text-[15px]"
          />
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Your site, your problem, your timeline…"
            rows={5}
            required
            className="border-brand-fg/15 text-brand-fg placeholder:text-brand-fg/40 resize-y rounded-xl border bg-[#0B0D0B] px-4 py-3.5 text-[15px]"
          />
          <button
            type="submit"
            className="bg-brand-gold hover:bg-brand-gold-hover min-h-12 rounded-full py-4 font-sans text-[15px] font-semibold text-[#0B140E]"
          >
            Send message
          </button>
          <p className="text-brand-fg/45 font-sans text-[13px]">
            Or write to{' '}
            <a href="mailto:hello@eletect.in" className="underline">
              hello@eletect.in
            </a>
          </p>
        </form>
      ) : (
        <div className="border-brand-green/40 rounded-2xl border bg-[rgba(95,169,124,0.08)] p-8 text-center">
          <div className="mb-3 text-3xl">🌿</div>
          <h3 className="mb-2 font-serif text-2xl leading-none font-normal">Message received.</h3>
          <p className="text-brand-fg/65 font-sans text-[14.5px]">
            We'll get back to you within two working days.
          </p>
        </div>
      )}
    </section>
  )
}
