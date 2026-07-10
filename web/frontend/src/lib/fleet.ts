// Fleet-health derivations for /dashboard/fleet: daily-mean sparkline series from
// the `health` history, and the predictive-maintenance threshold rules that turn
// telemetry into actionable candidates. Pure functions, no I/O — the page fetches
// the rows and this decides what they mean.
//
// The rules run client-side here because that is honest about what this repo can
// do today: there is no background job, and the durable home for this evaluation
// is the web/ingest bridge, which already sees every health row as it lands. A
// page view never writes — an officer confirms a candidate before it becomes a
// `maintenance` row (see Fleet.tsx). CONTEXT.md §6/§7: predictive, explainable.

import type { HealthRow, NodeRow } from './dashboard'

const DAY_MS = 24 * 60 * 60 * 1000

// ---------- sparklines ----------

export interface DailyPoint {
  day: number // days ago, 0 = today (oldest first once sorted)
  battery: number | null
  solar: number | null
}

// Mean battery/solar per calendar-day bucket for one node, oldest → newest, over
// the trailing `days` window. A day with no telemetry is a null (gap, not zero).
export function dailyMeans(health: HealthRow[], days = 14): DailyPoint[] {
  const now = Date.now()
  const buckets = new Map<number, { bSum: number; bN: number; sSum: number; sN: number }>()
  for (const h of health) {
    const ago = Math.floor((now - new Date(h.ts).getTime()) / DAY_MS)
    if (ago < 0 || ago >= days) continue
    const b = buckets.get(ago) ?? { bSum: 0, bN: 0, sSum: 0, sN: 0 }
    if (h.battery_pct != null) {
      b.bSum += h.battery_pct
      b.bN += 1
    }
    if (h.solar_w != null) {
      b.sSum += h.solar_w
      b.sN += 1
    }
    buckets.set(ago, b)
  }
  const out: DailyPoint[] = []
  for (let d = days - 1; d >= 0; d--) {
    const b = buckets.get(d)
    out.push({
      day: d,
      battery: b && b.bN > 0 ? b.bSum / b.bN : null,
      solar: b && b.sN > 0 ? b.sSum / b.sN : null,
    })
  }
  return out
}

// Least-squares slope (units per day) over daily points, ignoring gaps. Null when
// fewer than two populated days — a slope from one point is not a trend.
export function slopePerDay(points: DailyPoint[], key: 'battery' | 'solar'): number | null {
  const pts = points
    .map((p) => ({ x: p.day, y: p[key] }))
    .filter((p): p is { x: number; y: number } => p.y != null)
  if (pts.length < 2) return null
  const n = pts.length
  const sx = pts.reduce((s, p) => s + p.x, 0)
  const sy = pts.reduce((s, p) => s + p.y, 0)
  const sxx = pts.reduce((s, p) => s + p.x * p.x, 0)
  const sxy = pts.reduce((s, p) => s + p.x * p.y, 0)
  const denom = n * sxx - sx * sx
  if (denom === 0) return null
  // x is "days ago" (decreasing toward now), so negate to get change per forward day.
  return -(n * sxy - sx * sy) / denom
}

function meanSolarBetween(points: DailyPoint[], loDay: number, hiDay: number): number | null {
  const vals = points.filter((p) => p.day >= loDay && p.day <= hiDay && p.solar != null).map((p) => p.solar!)
  if (vals.length === 0) return null
  return vals.reduce((s, v) => s + v, 0) / vals.length
}

// ---------- maintenance rules ----------

// One row of the `maintenance` table (schema.sql §6). `source` is 'rule' for a
// staff-confirmed threshold flag, 'demo' for a Demo Mode scenario.
export interface MaintenanceRow {
  id: number
  node_id: string | null
  flag: string | null
  reason: string | null
  resolved: boolean
  source: string | null
  created_at: string
}

export type MaintenanceFlag =
  | 'offline'
  | 'stale'
  | 'battery_critical'
  | 'battery_low'
  | 'battery_drain'
  | 'solar_degraded'
  | 'firmware_outdated'

export interface MaintenanceCandidate {
  node_id: string
  flag: MaintenanceFlag
  reason: string
  severity: 'critical' | 'warn' | 'info'
}

const STALE_MS = 60 * 60 * 1000

// Shared staleness check (roster card badge and the `stale` rule both use it,
// so the threshold only lives in one place). Reads the clock itself rather than
// taking `now` as a prop, so callers never call Date.now() from render.
export function isStale(lastSeen: string | null): boolean {
  return lastSeen != null && Date.now() - new Date(lastSeen).getTime() > STALE_MS
}

// Compare dotted version strings ("v1.4.2") numerically. Non-numeric parts sort
// as 0 so a malformed version never counts as newest.
export function compareVersions(a: string, b: string): number {
  const pa = a.replace(/^v/i, '').split('.').map((x) => parseInt(x, 10) || 0)
  const pb = b.replace(/^v/i, '').split('.').map((x) => parseInt(x, 10) || 0)
  const len = Math.max(pa.length, pb.length)
  for (let i = 0; i < len; i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0)
    if (d !== 0) return d > 0 ? 1 : -1
  }
  return 0
}

export function fleetFirmwareMax(nodes: NodeRow[]): string | null {
  let max: string | null = null
  for (const n of nodes) {
    if (!n.firmware) continue
    if (max == null || compareVersions(n.firmware, max) > 0) max = n.firmware
  }
  return max
}

// Evaluate every rule against the current node vitals and its health history.
// `healthByNode` holds each node's rows (any window; the rules slice what they
// need). Returns the conditions currently true, most severe first.
export function evaluateRules(
  nodes: NodeRow[],
  healthByNode: Map<string, HealthRow[]>,
): MaintenanceCandidate[] {
  const firmwareMax = fleetFirmwareMax(nodes)
  const out: MaintenanceCandidate[] = []

  for (const n of nodes) {
    const push = (flag: MaintenanceFlag, reason: string, severity: MaintenanceCandidate['severity']) =>
      out.push({ node_id: n.id, flag, reason, severity })

    if (n.status === 'offline') {
      push('offline', 'Node is offline and not reporting.', 'critical')
    }

    if (isStale(n.last_seen)) {
      push('stale', 'No telemetry received in over an hour.', 'warn')
    }

    if (n.battery_pct != null && n.battery_pct < 20) {
      push('battery_critical', `Battery at ${n.battery_pct}%, below the 20% critical floor.`, 'critical')
    } else if (n.battery_pct != null && n.battery_pct < 40) {
      push('battery_low', `Battery at ${n.battery_pct}%, below the 40% service threshold.`, 'warn')
    }

    const points = dailyMeans(healthByNode.get(n.id) ?? [], 14)
    const battSlope = slopePerDay(points.slice(-7), 'battery')
    if (battSlope != null && battSlope < -2) {
      push('battery_drain', `Battery trending down ${battSlope.toFixed(1)}%/day over the last week.`, 'warn')
    }

    // Recent 3-day solar mean against the 9-12-day-ago baseline. A sustained
    // shortfall means a fouled or shaded panel, caught before the battery does.
    const recent = meanSolarBetween(points, 0, 2)
    const baseline = meanSolarBetween(points, 9, 12)
    if (recent != null && baseline != null && baseline > 0.5 && recent < 0.88 * baseline) {
      const drop = Math.round((1 - recent / baseline) * 100)
      push('solar_degraded', `Solar intake down ${drop}% versus its two-week baseline. Panel service due.`, 'info')
    }

    if (firmwareMax && n.firmware && compareVersions(n.firmware, firmwareMax) < 0) {
      push('firmware_outdated', `Firmware ${n.firmware} is behind the fleet (${firmwareMax}).`, 'info')
    }
  }

  const rank = { critical: 0, warn: 1, info: 2 }
  return out.sort((a, b) => rank[a.severity] - rank[b.severity])
}

// ---------- roster helpers ----------

export function operationalPct(nodes: NodeRow[]): number {
  if (nodes.length === 0) return 0
  const up = nodes.filter((n) => n.status === 'online' || n.status === 'alert').length
  return Math.round((up / nodes.length) * 100)
}

const FLAG_LABEL: Record<string, string> = {
  offline: 'Offline',
  stale: 'Stale telemetry',
  battery_critical: 'Battery critical',
  battery_low: 'Battery low',
  battery_drain: 'Battery draining',
  solar_degraded: 'Solar degraded',
  firmware_outdated: 'Firmware outdated',
}

export function flagLabel(flag: string): string {
  return FLAG_LABEL[flag] ?? flag
}
