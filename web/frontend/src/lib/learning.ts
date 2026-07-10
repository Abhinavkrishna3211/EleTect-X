// Derives deterrent effectiveness over time from `events` for the Learning view:
// for each deterrent `action`, the fraction of encounters where the animal
// actually retreated (outcome verification, CONTEXT.md §4), bucketed weekly so the
// trend — not a single number — is what the chart shows.

import type { EventRow } from './dashboard'

// Validated categorical palette for the dark ops surface (#0B0D0B). Fixed order —
// colour follows the action entity, never its rank. See scripts/validate_palette.
const SERIES_COLORS = ['#3987e5', '#199e70', '#c98500', '#e66767']
const OTHER_COLOR = '#898781'
// A few actions read wrong if their hue floats: "Blue strobe" in green confuses
// more than it distinguishes. Pin those to a fixed slot; every other action keeps
// filling the remaining slots in volume-rank order.
const PINNED_COLORS: Record<string, string> = { 'Blue strobe': '#3987e5' }
const WEEK_MS = 7 * 24 * 60 * 60 * 1000
const MAX_SERIES = SERIES_COLORS.length
// A rate from too few encounters is noise, not a trend — such a bucket reads as a
// gap rather than a misleading point (keeps sparse edge buckets from spiking).
const MIN_SAMPLES = 3

export interface TrendSeries {
  action: string
  color: string
  points: (number | null)[] // retreated-rate 0..1 per week bucket; null = no data
  current: number | null // latest bucket with data
  previous: number | null // prior bucket with data (for the trend arrow)
}

export interface TrendModel {
  weeks: string[] // bucket labels, oldest → newest
  series: TrendSeries[]
  sampleCount: number
}

const WK_LABEL = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  day: 'numeric',
  month: 'short',
})

function retreated(e: EventRow): boolean {
  return (e.outcome ?? '').toLowerCase().includes('retreat')
}

export function buildTrendModel(events: EventRow[]): TrendModel {
  const scored = events.filter((e) => e.action && e.outcome)
  if (scored.length === 0) return { weeks: [], series: [], sampleCount: 0 }

  const times = scored.map((e) => new Date(e.ts).getTime())
  const end = Math.max(...times)
  const start = Math.min(...times)
  const span = end - start
  const nBuckets = Math.min(8, Math.max(4, Math.ceil(span / WEEK_MS) + 1))
  const first = end - (nBuckets - 1) * WEEK_MS

  const weeks = Array.from({ length: nBuckets }, (_, i) => WK_LABEL.format(new Date(first + i * WEEK_MS)))
  const bucketOf = (ms: number) => Math.min(nBuckets - 1, Math.max(0, Math.floor((ms - first) / WEEK_MS)))

  // Rank actions by volume so the busiest patterns get the fixed colour slots;
  // anything past the palette folds into a single muted "Other".
  const totals = new Map<string, number>()
  for (const e of scored) totals.set(e.action as string, (totals.get(e.action as string) ?? 0) + 1)
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([a]) => a)
  const primary = ranked.slice(0, MAX_SERIES)
  const hasOther = ranked.length > MAX_SERIES
  const labelFor = (action: string) => (primary.includes(action) ? action : 'Other')
  const seriesNames = hasOther ? [...primary, 'Other'] : primary

  // tally[name][bucket] = { retreated, total }
  const tally = new Map<string, { r: number; n: number }[]>()
  for (const name of seriesNames) tally.set(name, weeks.map(() => ({ r: 0, n: 0 })))
  for (const e of scored) {
    const cell = tally.get(labelFor(e.action as string))![bucketOf(new Date(e.ts).getTime())]
    cell.n += 1
    if (retreated(e)) cell.r += 1
  }

  const rawPoints = seriesNames.map((name) => tally.get(name)!.map((c) => (c.n >= MIN_SAMPLES ? c.r / c.n : null)))

  // Trim leading/trailing buckets that no series populates (e.g. a lone recent
  // incident event) so the x-axis has no dangling empty columns.
  let lo = weeks.length
  let hi = -1
  for (const pts of rawPoints) {
    pts.forEach((p, i) => {
      if (p != null) {
        if (i < lo) lo = i
        if (i > hi) hi = i
      }
    })
  }
  if (hi < 0) return { weeks: [], series: [], sampleCount: scored.length }

  // Assign hues: honour pinned actions first, then hand the remaining palette
  // slots to the rest in volume-rank order so nothing collides with a pin.
  const colorFor = new Map<string, string>()
  for (const name of seriesNames) {
    if (name !== 'Other' && PINNED_COLORS[name]) colorFor.set(name, PINNED_COLORS[name])
  }
  const freeSlots = SERIES_COLORS.filter((c) => ![...colorFor.values()].includes(c))
  let slot = 0
  for (const name of seriesNames) {
    if (name === 'Other' || colorFor.has(name)) continue
    colorFor.set(name, freeSlots[slot++] ?? OTHER_COLOR)
  }

  const series: TrendSeries[] = seriesNames.map((name, i) => {
    const points = rawPoints[i].slice(lo, hi + 1)
    const valid = points.filter((p): p is number => p != null)
    return {
      action: name,
      color: name === 'Other' ? OTHER_COLOR : colorFor.get(name)!,
      points,
      current: valid.length > 0 ? valid[valid.length - 1] : null,
      previous: valid.length > 1 ? valid[valid.length - 2] : null,
    }
  })

  return { weeks: weeks.slice(lo, hi + 1), series, sampleCount: scored.length }
}
