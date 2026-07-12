import { describe, expect, it } from 'vitest'
import type { EventRow } from './dashboard'
import { buildTrendModel } from './learning'

const T0 = Date.parse('2026-07-12T12:00:00.000Z')
const WEEK_MS = 7 * 24 * 60 * 60 * 1000

function ev(weeksAgo: number, action: string, outcome: string): EventRow {
  return {
    id: Math.random(),
    node_id: 'S7-01',
    species: 'elephant',
    action,
    outcome,
    ts: new Date(T0 - weeksAgo * WEEK_MS).toISOString(),
  } as EventRow
}

// MIN_SAMPLES is 3: a bucket with fewer encounters reads as a gap, not a point.
function bucket(weeksAgo: number, action: string, retreated: number, total: number): EventRow[] {
  return Array.from({ length: total }, (_, i) =>
    ev(weeksAgo, action, i < retreated ? 'retreated' : 'no-response'),
  )
}

describe('buildTrendModel', () => {
  it('is empty when no event has both an action and an outcome', () => {
    const model = buildTrendModel([{ id: 1, ts: new Date(T0).toISOString() } as EventRow])
    expect(model).toEqual({ weeks: [], series: [], sampleCount: 0 })
  })

  it('ignores events missing an outcome — an unverified deterrent is not evidence', () => {
    const model = buildTrendModel([
      ...bucket(0, 'Horn', 2, 3),
      { id: 99, action: 'Horn', outcome: null, ts: new Date(T0).toISOString() } as unknown as EventRow,
    ])
    expect(model.sampleCount).toBe(3)
  })

  it('computes the retreated rate per action per bucket', () => {
    const model = buildTrendModel(bucket(0, 'Horn', 3, 4))
    const horn = model.series.find((s) => s.action === 'Horn')!
    expect(horn.current).toBeCloseTo(0.75, 6)
  })

  it('treats a bucket below the sample minimum as a gap, not a 100% spike', () => {
    // One lucky retreat out of one encounter is not a 100% effective deterrent.
    // The sparse bucket sits *between* two populated ones on purpose: an empty
    // bucket at either edge is trimmed off the axis entirely, so only an
    // interior one proves the rate was suppressed rather than merely cropped.
    const model = buildTrendModel([
      ...bucket(2, 'Horn', 2, 4),
      ...bucket(1, 'Horn', 1, 1), // a lone encounter — must not plot as 100%
      ...bucket(0, 'Horn', 3, 4),
    ])
    const horn = model.series.find((s) => s.action === 'Horn')!
    expect(horn.points).toHaveLength(3)
    expect(horn.points[1]).toBeNull()
    expect(horn.points[0]).toBeCloseTo(0.5, 6)
    expect(horn.current).toBeCloseTo(0.75, 6)
    // previous skips the gap rather than treating null as a data point.
    expect(horn.previous).toBeCloseTo(0.5, 6)
  })

  it('exposes current and previous buckets so the trend arrow has something to compare', () => {
    const model = buildTrendModel([...bucket(1, 'Horn', 1, 4), ...bucket(0, 'Horn', 3, 4)])
    const horn = model.series.find((s) => s.action === 'Horn')!
    expect(horn.previous).toBeCloseTo(0.25, 6)
    expect(horn.current).toBeCloseTo(0.75, 6)
  })

  it('counts every scored event in sampleCount', () => {
    const model = buildTrendModel([...bucket(0, 'Horn', 2, 3), ...bucket(0, 'Blue strobe', 1, 3)])
    expect(model.sampleCount).toBe(6)
  })

  it('pins "Blue strobe" to its fixed hue so the colour never floats between builds', () => {
    const model = buildTrendModel([...bucket(0, 'Blue strobe', 2, 3), ...bucket(0, 'Horn', 1, 5)])
    const strobe = model.series.find((s) => s.action === 'Blue strobe')!
    expect(strobe.color).toBe('#3987e5')
    // And nothing else may collide with the pinned slot.
    const others = model.series.filter((s) => s.action !== 'Blue strobe')
    expect(others.every((s) => s.color !== '#3987e5')).toBe(true)
  })

  it('folds actions past the palette into a single muted "Other" series', () => {
    const actions = ['A', 'B', 'C', 'D', 'E', 'F']
    const model = buildTrendModel(actions.flatMap((a, i) => bucket(0, a, 1, 6 - i)))
    const other = model.series.find((s) => s.action === 'Other')
    expect(other).toBeDefined()
    expect(other!.color).toBe('#898781')
    // Four palette slots plus the Other bucket.
    expect(model.series).toHaveLength(5)
  })

  it('gives every series the same number of points as there are week labels', () => {
    const model = buildTrendModel([...bucket(2, 'Horn', 1, 3), ...bucket(0, 'Horn', 3, 3)])
    for (const s of model.series) {
      expect(s.points).toHaveLength(model.weeks.length)
    }
  })
})
