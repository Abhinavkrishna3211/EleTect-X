import { describe, expect, it } from 'vitest'
import type { EventRow, MapPoint } from './dashboard'
import { herdAt, incidentPath, latestActivation, latestCluster, ms, sortByTs } from './incident'

const T0 = Date.parse('2026-07-12T18:00:00.000Z')

function ev(over: Partial<EventRow> & { ts: string }): EventRow {
  return {
    id: 1,
    node_id: 'S7-01',
    species: 'elephant',
    confidence: 0.9,
    ts: over.ts,
    ...(over as object),
  } as EventRow
}

function at(minutes: number): string {
  return new Date(T0 + minutes * 60_000).toISOString()
}

const POINTS = new Map<string, MapPoint>([
  ['S7-01', { left: 0, top: 0 }],
  ['S7-02', { left: 10, top: 20 }],
  ['S7-03', { left: 30, top: 40 }],
])

describe('sortByTs', () => {
  it('orders ascending without mutating the caller’s array', () => {
    const input = [ev({ ts: at(10) }), ev({ ts: at(0) })]
    const sorted = sortByTs(input)
    expect(sorted.map((e) => e.ts)).toEqual([at(0), at(10)])
    expect(input[0].ts).toBe(at(10)) // original untouched
  })
})

describe('latestCluster', () => {
  it('is empty for no events', () => {
    expect(latestCluster([])).toEqual([])
  })

  it('groups events with no gap larger than the window, ascending', () => {
    const events = [ev({ ts: at(0) }), ev({ ts: at(30) }), ev({ ts: at(60) })]
    expect(latestCluster(events, 90).map((e) => e.ts)).toEqual([at(0), at(30), at(60)])
  })

  it('cuts the cluster at a gap wider than the window, keeping only the latest run', () => {
    // 200 minutes of silence splits the old pair off from the recent pair.
    const events = [ev({ ts: at(0) }), ev({ ts: at(10) }), ev({ ts: at(210) }), ev({ ts: at(220) })]
    expect(latestCluster(events, 90).map((e) => e.ts)).toEqual([at(210), at(220)])
  })

  it('treats a gap exactly equal to the window as contiguous', () => {
    const events = [ev({ ts: at(0) }), ev({ ts: at(90) })]
    expect(latestCluster(events, 90)).toHaveLength(2)
  })

  it('treats a gap one minute past the window as a break', () => {
    const events = [ev({ ts: at(0) }), ev({ ts: at(91) })]
    expect(latestCluster(events, 90).map((e) => e.ts)).toEqual([at(91)])
  })
})

describe('latestActivation', () => {
  it('is empty when nothing is corridor-tagged', () => {
    expect(latestActivation([ev({ ts: at(0) })])).toEqual([])
  })

  it('picks the most recent activation group and orders it by handoff sequence', () => {
    const events = [
      ev({ ts: at(0), corridor: { activation: 'old', seq: 1 } } as Partial<EventRow> & { ts: string }),
      ev({ ts: at(100), corridor: { activation: 'new', seq: 2 } } as Partial<EventRow> & { ts: string }),
      ev({ ts: at(90), corridor: { activation: 'new', seq: 1 } } as Partial<EventRow> & { ts: string }),
    ]
    const got = latestActivation(events)
    expect(got.map((e) => e.corridor!.activation)).toEqual(['new', 'new'])
    expect(got.map((e) => e.corridor!.seq)).toEqual([1, 2])
  })
})

describe('incidentPath', () => {
  it('maps events to node positions in order', () => {
    const path = incidentPath([ev({ ts: at(0), node_id: 'S7-01' }), ev({ ts: at(1), node_id: 'S7-02' })], POINTS)
    expect(path).toEqual([
      { left: 0, top: 0 },
      { left: 10, top: 20 },
    ])
  })

  it('collapses consecutive repeats of the same node', () => {
    const path = incidentPath(
      [
        ev({ ts: at(0), node_id: 'S7-01' }),
        ev({ ts: at(1), node_id: 'S7-01' }),
        ev({ ts: at(2), node_id: 'S7-02' }),
      ],
      POINTS,
    )
    expect(path).toHaveLength(2)
  })

  it('drops events whose node has no fix rather than inventing a coordinate', () => {
    const path = incidentPath(
      [ev({ ts: at(0), node_id: 'S7-01' }), ev({ ts: at(1), node_id: 'UNKNOWN' }), ev({ ts: at(2), node_id: null })],
      POINTS,
    )
    expect(path).toEqual([{ left: 0, top: 0 }])
  })
})

describe('herdAt', () => {
  const incident = [
    ev({ ts: at(0), node_id: 'S7-01' }),
    ev({ ts: at(10), node_id: 'S7-02' }),
  ]

  it('is null when no event has a located node', () => {
    expect(herdAt([ev({ ts: at(0), node_id: 'NOWHERE' })], POINTS, T0)).toBeNull()
  })

  it('interpolates halfway between the bracketing nodes', () => {
    const p = herdAt(incident, POINTS, ms(at(5)))
    expect(p).toEqual({ left: 5, top: 10 })
  })

  it('clamps to the first node before the incident starts', () => {
    expect(herdAt(incident, POINTS, ms(at(-100)))).toEqual({ left: 0, top: 0 })
  })

  it('clamps to the last node after the incident ends', () => {
    expect(herdAt(incident, POINTS, ms(at(100)))).toEqual({ left: 10, top: 20 })
  })

  it('does not divide by zero when two events share a timestamp', () => {
    const same = [ev({ ts: at(0), node_id: 'S7-01' }), ev({ ts: at(0), node_id: 'S7-02' })]
    const p = herdAt(same, POINTS, ms(at(0)))
    expect(p).not.toBeNull()
    expect(Number.isFinite(p!.left)).toBe(true)
  })
})
