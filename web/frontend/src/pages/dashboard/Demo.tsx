import { useMemo, useRef, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LiveMap } from '@/components/dashboard/LiveMap'
import { DecisionCard } from '@/components/dashboard/DecisionCard'
import { ConfidenceRadar } from '@/components/dashboard/ConfidenceRadar'
import type { EventRow, NodeRow } from '@/lib/dashboard'
import { SCENARIOS, STEP_DELAY_MS, type ScenarioId, type ScenarioLogLine, type ScenarioStepResult } from '@/lib/demo'

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function Demo() {
  const { rows: nodeRows } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const { rows: eventRows } = useRealtimeTable<EventRow>('events', 'id', {
    orderBy: { column: 'ts', ascending: false },
    limit: 50,
  })

  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])
  const events = useMemo(
    () => [...eventRows.values()].sort((a, b) => b.ts.localeCompare(a.ts)),
    [eventRows],
  )
  const demoEvents = useMemo(() => events.filter((e) => e.media_url === 'demo'), [events])
  const decisionEvent = useMemo(() => demoEvents.find((e) => e.fusion) ?? null, [demoEvents])
  const hasDemoData = demoEvents.length > 0

  const [running, setRunning] = useState<ScenarioId | null>(null)
  const [log, setLog] = useState<ScenarioLogLine[]>([])
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)
  // Guards a run against a reset (or a second scenario) firing mid-sequence.
  const runToken = useRef(0)

  async function runScenario(id: ScenarioId) {
    if (running) return
    const token = ++runToken.current
    const def = SCENARIOS.find((s) => s.id === id)
    if (!def) return
    setRunning(id)
    setLog([])

    for (let step = 1; step <= def.totalSteps; step++) {
      if (runToken.current !== token) return
      setFocusNodeId(def.focusNodes[Math.min(step - 1, def.focusNodes.length - 1)] ?? null)
      const { data, error } = await supabase.rpc('run_demo_scenario', { p_scenario: id, p_step: step })
      if (runToken.current !== token) return
      if (error) {
        setLog((l) => [...l, { time: '', dot: '#e25b4a', text: `Scenario error: ${error.message}` }])
        break
      }
      const result = data as ScenarioStepResult
      setLog((l) => [...l, ...result.log])
      if (step < def.totalSteps) await sleep(STEP_DELAY_MS)
    }
    if (runToken.current === token) setRunning(null)
  }

  async function resetDemo() {
    runToken.current++
    setRunning(null)
    setResetting(true)
    setResetError(null)
    const { error } = await supabase.rpc('reset_demo_data')
    setResetting(false)
    if (error) {
      setResetError(error.message)
      return
    }
    setLog([])
    setFocusNodeId(null)
  }

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="m-0 mb-1 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Demo mode</h1>
        <p className="text-brand-fg/60 m-0 max-w-[70ch] font-sans text-sm leading-relaxed">
          One-click end-to-end scenario replays. Pick one, the map and log animate the full incident through the
          same realtime pipeline a live node uses.
        </p>
      </div>

      {hasDemoData && (
        <div className="border-brand-gold/30 flex flex-wrap items-center justify-between gap-3 rounded-2xl border bg-[rgba(226,161,60,0.06)] px-4.5 py-3">
          <p className="text-brand-gold m-0 font-mono text-[12px] font-semibold">
            DEMO DATA IN PLACE — this sector shows scenario rows, not field data.
          </p>
          <button
            onClick={resetDemo}
            disabled={resetting}
            className="border-brand-red text-brand-red rounded-full border bg-[rgba(226,91,74,0.1)] px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors hover:bg-[rgba(226,91,74,0.2)] disabled:opacity-40"
          >
            {resetting ? 'Resetting…' : 'Reset demo data'}
          </button>
          {resetError && (
            <p className="text-brand-red m-0 w-full font-mono text-[11.5px] font-semibold">
              Reset failed: {resetError}
            </p>
          )}
        </div>
      )}

      <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
        {SCENARIOS.map((s) => {
          const active = running === s.id
          return (
            <button
              key={s.id}
              onClick={() => runScenario(s.id)}
              disabled={running != null}
              className={`rounded-[14px] border p-4.5 text-left transition-colors disabled:cursor-not-allowed ${
                active
                  ? 'border-brand-gold bg-[rgba(226,161,60,0.1)]'
                  : 'border-brand-fg/10 bg-[#0B0D0B] hover:border-brand-fg/25'
              }`}
              style={{ minHeight: 44 }}
            >
              <div
                className={`mb-2.5 grid h-10 w-10 place-items-center rounded-xl border ${
                  active
                    ? 'border-brand-gold/40 text-brand-gold bg-[rgba(226,161,60,0.12)]'
                    : 'border-brand-fg/12 text-brand-fg/70 bg-brand-fg/4'
                }`}
              >
                <s.icon size={19} strokeWidth={1.75} aria-hidden />
              </div>
              <p className="text-brand-fg m-0 font-sans text-[14px] font-semibold">{s.label}</p>
              <p className="text-brand-fg/45 m-0 mt-1 font-mono text-[11.5px] font-medium">
                {active ? 'Running…' : s.dur}
              </p>
            </button>
          )
        })}
      </div>

      <div className="h-[clamp(300px,42vw,420px)]">
        <LiveMap nodes={nodes} selectedNodeId={focusNodeId} onSelect={setFocusNodeId} />
      </div>

      <div className="border-brand-fg/10 flex min-h-[120px] flex-col gap-2.5 rounded-2xl border bg-[#0B0D0B] p-5">
        {log.length === 0 ? (
          <p className="text-brand-fg/40 m-0 font-sans text-[13.5px] font-medium">
            Select a scenario above to begin the replay.
          </p>
        ) : (
          log.map((line, i) => (
            <div key={i} className="flex items-start gap-3">
              <span className="text-brand-gold min-w-11 font-mono text-[12px] font-semibold">{line.time}</span>
              <span
                className="mt-1 h-2 w-2 shrink-0 rounded-full"
                style={{ background: line.dot }}
              />
              <span className="text-brand-fg/85 font-sans text-[13.5px] leading-relaxed">{line.text}</span>
            </div>
          ))
        )}
      </div>

      <DecisionCard
        event={decisionEvent}
        radar={decisionEvent?.fusion ? <ConfidenceRadar modalities={decisionEvent.fusion.modalities} /> : undefined}
      />
    </div>
  )
}
