// Public-facing area risk, derived from the public_area_risk view.
//
// That view is deliberately aggregate-only — `day` and a count of high-priority
// detections, nothing else. Species, node id, and coordinates are withheld from
// the public role on purpose (see schema.sql), so anything shown to a resident
// has to be built from these two columns. Resist the temptation to enrich this
// with per-event detail: the detail belongs in the alert message sent to the
// resident, not in a screen any signed-up account can read.
//
// The view buckets on date_trunc('day', ts), which Postgres evaluates in the
// session timezone (UTC on Supabase). Buckets are therefore UTC days, not IST
// days — a detection at 02:00 IST lands in the previous UTC bucket. We compare
// against UTC days here so the arithmetic matches the data rather than silently
// disagreeing with it by 5.5 hours; the copy says "recent activity" instead of
// naming a precise local day so the wording stays true either way.

export interface AreaRiskRow {
  day: string
  detections: number
}

export type RiskLevel = 'clear' | 'low' | 'elevated' | 'high'

export interface AreaRisk {
  level: RiskLevel
  today: number
  week: number
}

export interface RiskDisplay {
  dot: string
  label: string
  color: string
  border: string
  background: string
}

const WEEK_DAYS = 7

// Two same-day detections is the point where a resident's behaviour should
// actually change (avoid the boundary paths after dark) rather than merely be
// informed; three or more is a sustained, active presence.
const ELEVATED_TODAY = 1
const HIGH_TODAY = 3

function utcDayKey(d: Date): string {
  return d.toISOString().slice(0, 10)
}

export function deriveAreaRisk(rows: AreaRiskRow[], now: Date = new Date()): AreaRisk {
  const todayKey = utcDayKey(now)
  const cutoff = new Date(now.getTime() - WEEK_DAYS * 24 * 60 * 60 * 1000)

  let today = 0
  let week = 0

  for (const row of rows) {
    const key = utcDayKey(new Date(row.day))
    if (key === todayKey) today += row.detections
    if (new Date(row.day) >= cutoff) week += row.detections
  }

  let level: RiskLevel = 'clear'
  if (today >= HIGH_TODAY) level = 'high'
  else if (today >= ELEVATED_TODAY) level = 'elevated'
  else if (week > 0) level = 'low'

  return { level, today, week }
}

export function riskDisplay(risk: AreaRisk): RiskDisplay {
  switch (risk.level) {
    case 'high':
      return {
        dot: '🔴',
        label: 'High · wildlife active near villages today',
        color: 'text-brand-red',
        border: 'border-brand-red/40',
        background: 'rgba(226,91,74,0.08)',
      }
    case 'elevated':
      return {
        dot: '🟠',
        label: 'Elevated · a detection near villages today',
        color: 'text-brand-gold',
        border: 'border-brand-gold/40',
        background: 'rgba(226,161,60,0.07)',
      }
    case 'low':
      return {
        dot: '🟡',
        label: 'Low · recent activity, none today',
        color: 'text-brand-gold',
        border: 'border-brand-gold/30',
        background: 'rgba(226,161,60,0.05)',
      }
    default:
      return {
        dot: '🟢',
        label: 'Low · no recent detections near villages',
        color: 'text-brand-green',
        border: 'border-brand-green/35',
        background: 'rgba(95,169,124,0.07)',
      }
  }
}

// Day-bucket rows into the short activity list a resident sees. Deliberately
// carries no species or location — see the note at the top of this file.
export interface ActivityLine {
  day: string
  detections: number
  label: string
}

export function recentActivity(rows: AreaRiskRow[], limit = 5): ActivityLine[] {
  return [...rows]
    .sort((a, b) => new Date(b.day).getTime() - new Date(a.day).getTime())
    .slice(0, limit)
    .map((row) => ({
      day: row.day,
      detections: row.detections,
      label: new Date(row.day).toLocaleDateString('en-IN', {
        weekday: 'short',
        day: 'numeric',
        month: 'short',
        timeZone: 'UTC',
      }),
    }))
}
