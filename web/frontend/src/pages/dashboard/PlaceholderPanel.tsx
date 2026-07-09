export function PlaceholderPanel({ title }: { title: string }) {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">{title}</h1>
      <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-8 text-center">
        <p className="text-brand-fg/50 m-0 font-sans text-sm">This module lands in the next build phase.</p>
      </div>
    </div>
  )
}
