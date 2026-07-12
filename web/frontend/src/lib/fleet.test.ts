import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { HealthRow, NodeRow } from './dashboard'
import {
  compareVersions,
  dailyMeans,
  evaluateRules,
  fleetFirmwareMax,
  flagLabel,
  isStale,
  operationalPct,
  slopePerDay,
} from './fleet'

const NOW = new Date('2026-07-12T12:00:00.000Z')
const DAY_MS = 24 * 60 * 60 * 1000

// These functions read the clock directly (see the note on isStale), so the
// clock has to be pinned or the assertions drift with wall time.
beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(NOW)
})
afterEach(() => {
  vi.useRealTimers()
})

function node(over: Partial<NodeRow> = {}): NodeRow {
  return {
    id: 'S7-01',
    status: 'online',
    battery_pct: 90,
    solar_w: 12,
    firmware: 'v1.4.2',
    last_seen: NOW.toISOString(),
    lat: 10.058,
    lng: 76.628,
    ...(over as object),
  } as NodeRow
}

function health(daysAgo: number, battery: number | null, solar: number | null): HealthRow {
  return {
    node_id: 'S7-01',
    ts: new Date(NOW.getTime() - daysAgo * DAY_MS).toISOString(),
    battery_pct: battery,
    solar_w: solar,
  } as HealthRow
}

describe('compareVersions', () => {
  it('orders by numeric component, not lexically ("v1.10.0" > "v1.9.0")', () => {
    // The classic string-compare trap: "10" < "9" as text.
    expect(compareVersions('v1.10.0', 'v1.9.0')).toBe(1)
  })

  it('treats equal versions as equal, with or without the v prefix', () => {
    expect(compareVersions('v1.4.2', '1.4.2')).toBe(0)
    expect(compareVersions('v1.4.2', 'v1.4.2')).toBe(0)
  })

  it('treats a missing trailing component as zero ("v1.4" === "v1.4.0")', () => {
    expect(compareVersions('v1.4', 'v1.4.0')).toBe(0)
    expect(compareVersions('v1.4.1', 'v1.4')).toBe(1)
  })

  it('never lets a malformed version sort as newest', () => {
    expect(compareVersions('garbage', 'v1.0.0')).toBe(-1)
  })
})

describe('fleetFirmwareMax', () => {
  it('picks the highest version across the fleet', () => {
    const nodes = [
      node({ id: 'a', firmware: 'v1.4.2' }),
      node({ id: 'b', firmware: 'v1.10.0' }),
      node({ id: 'c', firmware: 'v1.9.9' }),
    ]
    expect(fleetFirmwareMax(nodes)).toBe('v1.10.0')
  })

  it('ignores nodes with no firmware reported, and returns null when none have it', () => {
    expect(fleetFirmwareMax([node({ firmware: null })])).toBeNull()
    expect(fleetFirmwareMax([node({ id: 'a', firmware: null }), node({ id: 'b', firmware: 'v2.0.0' })])).toBe(
      'v2.0.0',
    )
  })
})

describe('isStale', () => {
  it('is false for telemetry inside the one-hour window', () => {
    expect(isStale(new Date(NOW.getTime() - 59 * 60_000).toISOString())).toBe(false)
  })

  it('is true past an hour of silence', () => {
    expect(isStale(new Date(NOW.getTime() - 61 * 60_000).toISOString())).toBe(true)
  })

  it('is false — not true — for a node that has never reported', () => {
    // A null last_seen is "no data", which the offline rule owns. Reporting it
    // as stale as well would double-flag the same node.
    expect(isStale(null)).toBe(false)
  })
})

describe('dailyMeans', () => {
  it('averages multiple readings within the same day bucket', () => {
    const points = dailyMeans([health(0, 80, 10), health(0, 90, 20)], 14)
    const today = points[points.length - 1]
    expect(today.day).toBe(0)
    expect(today.battery).toBe(85)
    expect(today.solar).toBe(15)
  })

  it('returns oldest-first over the requested window', () => {
    const points = dailyMeans([health(0, 50, 5)], 14)
    expect(points).toHaveLength(14)
    expect(points[0].day).toBe(13)
    expect(points[points.length - 1].day).toBe(0)
  })

  it('reports a day with no telemetry as a gap (null), never as zero', () => {
    // Zero would read as "the battery is flat", which is a very different claim
    // from "the node did not report".
    const points = dailyMeans([health(0, 80, 10)], 14)
    expect(points[0].battery).toBeNull()
    expect(points[0].solar).toBeNull()
  })

  it('drops readings older than the window', () => {
    const points = dailyMeans([health(30, 80, 10)], 14)
    expect(points.every((p) => p.battery === null)).toBe(true)
  })

  it('handles a partially-reported row (battery only, no solar)', () => {
    const points = dailyMeans([health(0, 70, null)], 14)
    const today = points[points.length - 1]
    expect(today.battery).toBe(70)
    expect(today.solar).toBeNull()
  })
})

describe('slopePerDay', () => {
  it('reports a falling battery as a negative slope per forward day', () => {
    // 3 days ago 90, 2 -> 80, 1 -> 70, today 60: losing 10 %/day.
    const points = dailyMeans([health(3, 90, 5), health(2, 80, 5), health(1, 70, 5), health(0, 60, 5)], 14)
    expect(slopePerDay(points, 'battery')).toBeCloseTo(-10, 5)
  })

  it('reports a rising series as a positive slope', () => {
    const points = dailyMeans([health(2, 60, 5), health(1, 70, 5), health(0, 80, 5)], 14)
    expect(slopePerDay(points, 'battery')).toBeCloseTo(10, 5)
  })

  it('is null with fewer than two populated days — one point is not a trend', () => {
    const points = dailyMeans([health(0, 60, 5)], 14)
    expect(slopePerDay(points, 'battery')).toBeNull()
  })

  it('is null when nothing is populated at all', () => {
    expect(slopePerDay(dailyMeans([], 14), 'battery')).toBeNull()
  })
})

describe('evaluateRules', () => {
  const noHealth = new Map<string, HealthRow[]>()

  it('flags an offline node as critical', () => {
    const found = evaluateRules([node({ status: 'offline' })], noHealth)
    expect(found.map((f) => f.flag)).toContain('offline')
    expect(found.find((f) => f.flag === 'offline')!.severity).toBe('critical')
  })

  it('flags battery below the 20% floor as critical, not merely low', () => {
    const found = evaluateRules([node({ battery_pct: 15 })], noHealth)
    const flags = found.map((f) => f.flag)
    expect(flags).toContain('battery_critical')
    expect(flags).not.toContain('battery_low')
  })

  it('flags battery between 20% and 40% as low', () => {
    const flags = evaluateRules([node({ battery_pct: 35 })], noHealth).map((f) => f.flag)
    expect(flags).toContain('battery_low')
    expect(flags).not.toContain('battery_critical')
  })

  it('leaves a healthy battery alone at the 40% boundary', () => {
    const flags = evaluateRules([node({ battery_pct: 40 })], noHealth).map((f) => f.flag)
    expect(flags).not.toContain('battery_low')
    expect(flags).not.toContain('battery_critical')
  })

  it('flags stale telemetry', () => {
    const stale = node({ last_seen: new Date(NOW.getTime() - 2 * 60 * 60_000).toISOString() })
    expect(evaluateRules([stale], noHealth).map((f) => f.flag)).toContain('stale')
  })

  it('flags a battery draining faster than 2%/day over the last week', () => {
    const rows = [0, 1, 2, 3, 4, 5, 6].map((d) => health(d, 60 + d * 5, 10)) // -5 %/day forward
    const found = evaluateRules([node()], new Map([['S7-01', rows]]))
    expect(found.map((f) => f.flag)).toContain('battery_drain')
  })

  it('does not flag drain for a gentle, in-tolerance decline', () => {
    const rows = [0, 1, 2, 3, 4, 5, 6].map((d) => health(d, 80 + d, 10)) // -1 %/day
    const found = evaluateRules([node()], new Map([['S7-01', rows]]))
    expect(found.map((f) => f.flag)).not.toContain('battery_drain')
  })

  it('flags solar degraded when recent intake falls well below the two-week baseline', () => {
    const rows = [
      ...[0, 1, 2].map((d) => health(d, 90, 4)), // recent: 4 W
      ...[9, 10, 11, 12].map((d) => health(d, 90, 12)), // baseline: 12 W
    ]
    const found = evaluateRules([node()], new Map([['S7-01', rows]]))
    const solar = found.find((f) => f.flag === 'solar_degraded')
    expect(solar).toBeDefined()
    expect(solar!.reason).toContain('67%') // 1 - 4/12
  })

  it('does not flag solar within the 12% tolerance band', () => {
    const rows = [
      ...[0, 1, 2].map((d) => health(d, 90, 11)),
      ...[9, 10, 11, 12].map((d) => health(d, 90, 12)),
    ]
    const found = evaluateRules([node()], new Map([['S7-01', rows]]))
    expect(found.map((f) => f.flag)).not.toContain('solar_degraded')
  })

  it('flags a node behind the fleet firmware', () => {
    const nodes = [node({ id: 'a', firmware: 'v1.4.2' }), node({ id: 'b', firmware: 'v1.10.0' })]
    const found = evaluateRules(nodes, noHealth)
    const fw = found.find((f) => f.flag === 'firmware_outdated')
    expect(fw).toBeDefined()
    expect(fw!.node_id).toBe('a')
  })

  it('does not flag firmware when the whole fleet is level', () => {
    const nodes = [node({ id: 'a', firmware: 'v1.4.2' }), node({ id: 'b', firmware: 'v1.4.2' })]
    expect(evaluateRules(nodes, noHealth).map((f) => f.flag)).not.toContain('firmware_outdated')
  })

  it('returns nothing for a perfectly healthy fleet', () => {
    expect(evaluateRules([node()], noHealth)).toEqual([])
  })

  it('orders findings most severe first', () => {
    const bad = node({ status: 'offline', battery_pct: 10, firmware: 'v1.0.0' })
    const newer = node({ id: 'S7-02', firmware: 'v2.0.0' })
    const found = evaluateRules([bad, newer], noHealth)
    const rank = { critical: 0, warn: 1, info: 2 } as const
    const ranks = found.map((f) => rank[f.severity])
    expect([...ranks].sort((a, b) => a - b)).toEqual(ranks)
  })
})

describe('operationalPct', () => {
  it('counts online and alert nodes as operational — an alerting node is working', () => {
    const nodes = [
      node({ id: 'a', status: 'online' }),
      node({ id: 'b', status: 'alert' }),
      node({ id: 'c', status: 'offline' }),
      node({ id: 'd', status: 'maintenance' }),
    ]
    expect(operationalPct(nodes)).toBe(50)
  })

  it('is 0 for an empty fleet rather than dividing by zero', () => {
    expect(operationalPct([])).toBe(0)
  })

  it('is 100 when every node is up', () => {
    expect(operationalPct([node(), node({ id: 'b' })])).toBe(100)
  })
})

describe('flagLabel', () => {
  it('gives a human label for a known flag', () => {
    expect(flagLabel('battery_critical')).toBe('Battery critical')
  })

  it('falls back to the raw flag rather than rendering undefined', () => {
    expect(flagLabel('something_new')).toBe('something_new')
  })
})
