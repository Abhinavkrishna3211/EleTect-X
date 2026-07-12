import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fusedConfidence,
  geoPoints,
  modalityLabel,
  relativeTime,
  sigmoid,
  statusDisplay,
  toLatLng,
  type EventRow,
  type NodeRow,
} from './dashboard'

const NOW = new Date('2026-07-12T12:00:00.000Z')

describe('sigmoid', () => {
  // This is P = sigma(L) from the frozen fusion design (CONTEXT.md §4, ADR 0001
  // §6). The UI headlines the number it produces, so it is worth pinning rather
  // than assuming.
  it('maps zero log-odds to even odds', () => {
    expect(sigmoid(0)).toBe(0.5)
  })

  it('is monotonic and bounded in (0, 1)', () => {
    expect(sigmoid(-10)).toBeGreaterThan(0)
    expect(sigmoid(-10)).toBeLessThan(sigmoid(0))
    expect(sigmoid(0)).toBeLessThan(sigmoid(10))
    expect(sigmoid(10)).toBeLessThan(1)
  })

  it('is symmetric about zero: sigma(-x) === 1 - sigma(x)', () => {
    expect(sigmoid(-2)).toBeCloseTo(1 - sigmoid(2), 12)
  })

  it('matches the closed form at a known point', () => {
    expect(sigmoid(2)).toBeCloseTo(1 / (1 + Math.exp(-2)), 12)
  })
})

describe('fusedConfidence', () => {
  it('prefers the stored scalar when the event carries one', () => {
    const e = { confidence: 0.85, fusion: { logodds: 5 } } as EventRow
    expect(fusedConfidence(e)).toBe(0.85)
  })

  it('derives from the fusion log-odds when no scalar is stored', () => {
    const e = { confidence: null, fusion: { logodds: 0 } } as unknown as EventRow
    expect(fusedConfidence(e)).toBe(0.5)
  })

  it('is null when the event carries neither — never a fabricated 0', () => {
    // Rendering 0% confidence for "we do not know" would be a lie on the
    // decision card, so null has to survive all the way out.
    const e = { confidence: null, fusion: null } as unknown as EventRow
    expect(fusedConfidence(e)).toBeNull()
  })
})

describe('statusDisplay', () => {
  it('maps each node status to its legend bucket', () => {
    expect(statusDisplay('online').label).toBe('HEALTHY')
    expect(statusDisplay('maintenance').label).toBe('ATTENTION')
    expect(statusDisplay('alert').label).toBe('ALERT')
    expect(statusDisplay('offline').label).toBe('OFFLINE')
  })

  it('falls back to OFFLINE for an unknown status rather than rendering undefined', () => {
    expect(statusDisplay('bogus' as never).label).toBe('OFFLINE')
  })
})

describe('modalityLabel', () => {
  it('names the three fusion modalities', () => {
    expect(modalityLabel('seismic')).toBe('Ground vibration')
    expect(modalityLabel('acoustic')).toBe('Audio')
    expect(modalityLabel('vision')).toBe('Vision')
  })
})

describe('geoPoints / toLatLng', () => {
  it('keys located nodes by id, carrying lng as left and lat as top', () => {
    const nodes = [{ id: 'S7-01', lat: 10.058, lng: 76.628 }] as NodeRow[]
    const pts = geoPoints(nodes)
    expect(pts.get('S7-01')).toEqual({ left: 76.628, top: 10.058 })
  })

  it('drops nodes with no fix rather than inventing coordinates', () => {
    const nodes = [
      { id: 'a', lat: null, lng: 76.6 },
      { id: 'b', lat: 10.0, lng: null },
    ] as NodeRow[]
    expect(geoPoints(nodes).size).toBe(0)
  })

  it('round-trips a point back to a Leaflet [lat, lng] pair', () => {
    expect(toLatLng({ left: 76.628, top: 10.058 })).toEqual([10.058, 76.628])
  })
})

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString()

  it('says "never" for a missing timestamp', () => {
    expect(relativeTime(null)).toBe('never')
  })

  it('says "unknown" for an unparseable timestamp', () => {
    expect(relativeTime('not-a-date')).toBe('unknown')
  })

  it('steps through seconds, minutes, hours and days', () => {
    expect(relativeTime(ago(40 * 1000))).toBe('40 s ago')
    expect(relativeTime(ago(12 * 60_000))).toBe('12 m ago')
    expect(relativeTime(ago(3 * 3_600_000))).toBe('3 h ago')
    expect(relativeTime(ago(2 * 86_400_000))).toBe('2 d ago')
  })

  it('clamps a future timestamp to "just now" rather than showing negative time', () => {
    expect(relativeTime(new Date(NOW.getTime() + 60_000).toISOString())).toBe('just now')
  })
})
