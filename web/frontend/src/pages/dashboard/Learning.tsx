import { useEffect, useMemo, useState } from 'react'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LearningTrendChart } from '@/components/dashboard/LearningTrendChart'
import { buildTrendModel, type TrendSeries } from '@/lib/learning'
import type { EventRow } from '@/lib/dashboard'

function trend(s: TrendSeries): { arrow: string; color: string } {
  if (s.current == null || s.previous == null) return { arrow: '', color: 'rgba(233,237,230,0.5)' }
  const d = s.current - s.previous
  if (d > 0.005) return { arrow: '↑', color: '#5fa97c' }
  if (d < -0.005) return { arrow: '↓', color: '#e25b4a' }
  return { arrow: '→', color: 'rgba(233,237,230,0.5)' }
}

// Per-pattern effectiveness bar; width animates from 0 on mount (design line 905).
function PatternBar({ s }: { s: TrendSeries }) {
  const [w, setW] = useState(0)
  const target = s.current ?? 0
  useEffect(() => {
    const id = requestAnimationFrame(() => setW(target))
    return () => cancelAnimationFrame(id)
  }, [target])
  const t = trend(s)
  return (
    <div>
      <div className="mb-1.75 flex items-center justify-between gap-2.5">
        <span className="font-sans text-[13.5px] font-semibold">{s.action}</span>
        <span className="font-mono text-[12.5px] font-semibold tabular-nums" style={{ color: t.color }}>
          {s.current == null ? '—' : `${Math.round(s.current * 100)}%`} {t.arrow}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-[rgba(233,237,230,0.07)]">
        <div
          className="h-full rounded-full"
          style={{ width: `${w * 100}%`, background: s.color, transition: 'width 1s ease' }}
        />
      </div>
    </div>
  )
}

export function Learning() {
  const { rows: eventRows, loading } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 600,
  })

  const model = useMemo(() => buildTrendModel([...eventRows.values()]), [eventRows])
  const hasData = model.series.length > 0 && model.weeks.length > 0

  return (
    <div className="flex max-w-[880px] flex-col gap-4">
      <div>
        <h1 className="m-0 mb-1 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">AI learning</h1>
        <p className="text-brand-fg/60 m-0 max-w-[70ch] font-sans text-sm leading-relaxed">
          Deterrent effectiveness per pattern at this site. The node verifies whether the animal actually left, and
          shifts to what works.
        </p>
      </div>

      {loading ? (
        <div className="border-brand-fg/10 text-brand-fg/40 grid h-64 place-items-center rounded-2xl border bg-[#0B0D0B] font-mono text-[12px]">
          Loading outcomes…
        </div>
      ) : !hasData ? (
        <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-8 text-center">
          <p className="text-brand-fg/50 m-0 font-sans text-sm">No scored deterrence outcomes recorded yet.</p>
        </div>
      ) : (
        <>
          <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-5 sm:p-6">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h3 className="m-0 font-sans text-sm font-semibold">Retreated rate over time</h3>
              <span className="text-brand-fg/40 font-mono text-[11px]">{model.sampleCount} encounters</span>
            </div>
            <LearningTrendChart weeks={model.weeks} series={model.series} />
          </div>

          <div className="border-brand-fg/10 flex flex-col gap-4.5 rounded-2xl border bg-[#0B0D0B] p-6">
            <h3 className="m-0 font-sans text-sm font-semibold">Current effectiveness by pattern</h3>
            {model.series.map((s) => (
              <PatternBar key={s.action} s={s} />
            ))}
          </div>

          <div className="border-brand-gold/30 rounded-2xl border bg-[rgba(226,161,60,0.05)] p-5">
            <p className="text-brand-fg/75 m-0 font-sans text-[13.5px] leading-relaxed">
              Pattern rotation is randomised per encounter, the sequence never repeats, so habituation stays near zero
              even after months of exposure.
            </p>
          </div>
        </>
      )}
    </div>
  )
}
