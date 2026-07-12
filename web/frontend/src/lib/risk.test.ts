import { describe, expect, it } from 'vitest'
import { deriveAreaRisk, recentActivity, riskDisplay, type AreaRiskRow } from './risk'

// Pinned so "today" is deterministic — the whole module is a function of the
// clock, and a drifting reference date would make these tests flake at midnight.
const NOW = new Date('2026-07-12T12:00:00.000Z')
const DAY_MS = 24 * 60 * 60 * 1000

function day(daysAgo: number, detections: number): AreaRiskRow {
  const d = new Date(NOW.getTime() - daysAgo * DAY_MS)
  return { day: `${d.toISOString().slice(0, 10)}T00:00:00+00:00`, detections }
}

describe('deriveAreaRisk', () => {
  it('is clear when nothing has been detected at all', () => {
    const risk = deriveAreaRisk([], NOW)
    expect(risk).toEqual({ level: 'clear', today: 0, week: 0 })
  })

  it('is low when there is recent activity but none today', () => {
    const risk = deriveAreaRisk([day(2, 4)], NOW)
    expect(risk.level).toBe('low')
    expect(risk.today).toBe(0)
    expect(risk.week).toBe(4)
  })

  it('is elevated on a single detection today', () => {
    const risk = deriveAreaRisk([day(0, 1)], NOW)
    expect(risk.level).toBe('elevated')
    expect(risk.today).toBe(1)
  })

  it('escalates to high at three detections today', () => {
    expect(deriveAreaRisk([day(0, 2)], NOW).level).toBe('elevated')
    expect(deriveAreaRisk([day(0, 3)], NOW).level).toBe('high')
  })

  it('sums multiple buckets into the weekly figure', () => {
    const risk = deriveAreaRisk([day(1, 2), day(3, 1), day(5, 4)], NOW)
    expect(risk.week).toBe(7)
    expect(risk.today).toBe(0)
  })

  it('excludes activity older than the seven-day window from the weekly figure', () => {
    const risk = deriveAreaRisk([day(30, 9)], NOW)
    expect(risk.week).toBe(0)
    // Stale activity must not keep the banner amber forever.
    expect(risk.level).toBe('clear')
  })

  it('lets today’s activity drive the level even when the week is otherwise quiet', () => {
    const risk = deriveAreaRisk([day(0, 5), day(20, 100)], NOW)
    expect(risk.level).toBe('high')
    expect(risk.today).toBe(5)
  })
})

describe('riskDisplay', () => {
  it('gives every level a distinct dot and label', () => {
    const levels = (['clear', 'low', 'elevated', 'high'] as const).map((level) =>
      riskDisplay({ level, today: 0, week: 0 }),
    )
    expect(new Set(levels.map((l) => l.dot)).size).toBe(4)
    expect(new Set(levels.map((l) => l.label)).size).toBe(4)
  })

  it('only says "no recent detections" when there genuinely are none', () => {
    expect(riskDisplay({ level: 'clear', today: 0, week: 0 }).label).toMatch(/no recent detections/i)
    // The bug this guards: a hardcoded all-clear shown to a resident while
    // wildlife is actually active nearby.
    expect(riskDisplay({ level: 'high', today: 4, week: 9 }).label).not.toMatch(/no recent/i)
  })
})

describe('recentActivity', () => {
  it('sorts newest first', () => {
    const lines = recentActivity([day(5, 1), day(1, 2), day(3, 3)])
    expect(lines.map((l) => l.detections)).toEqual([2, 3, 1])
  })

  it('caps the list at the requested limit', () => {
    const rows = [0, 1, 2, 3, 4, 5, 6, 7].map((d) => day(d, 1))
    expect(recentActivity(rows, 5)).toHaveLength(5)
    expect(recentActivity(rows, 2)).toHaveLength(2)
  })

  it('is empty for no rows', () => {
    expect(recentActivity([])).toEqual([])
  })

  it('labels each bucket with a readable day', () => {
    const [line] = recentActivity([day(0, 1)])
    expect(line.label).toMatch(/\d/)
    expect(line.detections).toBe(1)
  })
})
