import { BatteryLow, CloudRain, Crosshair, Network, ShieldOff, Siren, type LucideIcon } from 'lucide-react'

// Demo Mode scenario catalog — client-side metadata only. The log text and every
// written row come back from run_demo_scenario() (web/backend/schema.sql); this
// file only knows the fixed whitelist, step counts, and which node to focus the
// map on, so the driver loop and the scenario grid don't have to guess at either.

export type ScenarioId =
  | 'confirmed_elephant'
  | 'sensor_dropout'
  | 'corridor_handoff'
  | 'declined_livestock'
  | 'fleet_degradation'
  | 'poaching_acoustic'

export interface ScenarioDef {
  id: ScenarioId
  label: string
  dur: string
  icon: LucideIcon
  // Total steps — must match the `v_total` case in run_demo_scenario exactly.
  totalSteps: number
  // Node(s) the map should frame while this scenario runs, in step order.
  focusNodes: string[]
}

export const SCENARIOS: ScenarioDef[] = [
  {
    id: 'confirmed_elephant',
    label: 'Confirmed elephant · deterrent fires',
    dur: '3 steps · ~9 s',
    icon: Siren,
    totalSteps: 3,
    focusNodes: ['S7-06'],
  },
  {
    id: 'sensor_dropout',
    label: 'Camera blinded by rain · holds',
    dur: '2 steps · ~6 s',
    icon: CloudRain,
    totalSteps: 2,
    focusNodes: ['S7-05'],
  },
  {
    id: 'corridor_handoff',
    label: 'Coordinated corridor handoff',
    dur: '5 steps · ~15 s',
    icon: Network,
    totalSteps: 5,
    focusNodes: ['S7-12', 'S7-06', 'S7-07', 'S7-05', 'S7-09'],
  },
  {
    id: 'declined_livestock',
    label: 'Cattle, not elephant · declines to act',
    dur: '2 steps · ~6 s',
    icon: ShieldOff,
    totalSteps: 2,
    focusNodes: ['S7-02'],
  },
  {
    id: 'fleet_degradation',
    label: 'Solar decline · maintenance raised',
    dur: '3 steps · ~9 s',
    icon: BatteryLow,
    totalSteps: 3,
    focusNodes: ['S7-11'],
  },
  {
    id: 'poaching_acoustic',
    label: 'Gunshot signature · silent alert',
    dur: '3 steps · ~9 s',
    icon: Crosshair,
    totalSteps: 3,
    focusNodes: ['S7-09'],
  },
]

export function scenarioDef(id: ScenarioId): ScenarioDef {
  const def = SCENARIOS.find((s) => s.id === id)
  if (!def) throw new Error(`unknown scenario ${id}`)
  return def
}

// One log line as returned by run_demo_scenario()'s jsonb 'log' array.
export interface ScenarioLogLine {
  time: string
  dot: string
  text: string
}

export interface ScenarioStepResult {
  scenario: ScenarioId
  step: number
  total: number
  done: boolean
  log: ScenarioLogLine[]
}

// Client pacing between steps — long enough to read the log line and watch the
// map react before the next INSERT lands, short enough that six scenarios stay
// a one-sitting demo.
export const STEP_DELAY_MS = 3000
