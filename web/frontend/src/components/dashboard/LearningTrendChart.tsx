import { useRef, useState } from 'react'
import type { TrendSeries } from '@/lib/learning'

// Animated multi-series line chart of deterrent retreated-rate over time. Follows
// the dataviz method: validated categorical palette (identity, fixed order), one
// y-axis, recessive grid, a legend for identity, and a crosshair+tooltip hover.
// Lines draw in on mount via the et-draw keyframe (paths carry pathLength="1").

const VBW = 680
const VBH = 280
const M = { left: 40, right: 78, top: 16, bottom: 30 }
const X0 = M.left
const X1 = VBW - M.right
const Y0 = M.top // rate = 1
const Y1 = VBH - M.bottom // rate = 0

const INK_MUTED = '#898781'
const GRID = '#2c2c2a'
const SURFACE = '#0B0D0B'

interface Props {
  weeks: string[]
  series: TrendSeries[]
}

function xFor(i: number, n: number): number {
  if (n <= 1) return (X0 + X1) / 2
  return X0 + (i / (n - 1)) * (X1 - X0)
}
function yFor(rate: number): number {
  return Y1 - rate * (Y1 - Y0)
}

// Split a series into continuous segments, breaking on null buckets, so gaps in
// data leave gaps in the line rather than interpolating across them.
function segments(points: (number | null)[], n: number): string[] {
  const segs: string[] = []
  let cur: string[] = []
  points.forEach((p, i) => {
    if (p == null) {
      if (cur.length > 1) segs.push(cur.join(' '))
      cur = []
    } else {
      cur.push(`${xFor(i, n).toFixed(1)},${yFor(p).toFixed(1)}`)
    }
  })
  if (cur.length > 1) segs.push(cur.join(' '))
  else if (cur.length === 1) segs.push(cur[0]) // lone point → marker still drawn below
  return segs
}

// Place the end-of-line labels so they never sit on top of each other. Two series
// that converge to the same rate (78% and 78%) resolve to the identical y, which is
// exactly where a direct label is most useful and was least readable. Walk them in y
// order and push each one down until it clears the previous by LABEL_GAP, then, if
// the stack has run past the bottom of the plot, shift the whole run back up so it
// stays inside the chart rather than spilling under the x-axis.
const LABEL_GAP = 11

interface EndLabel {
  action: string
  color: string
  v: number
  y: number
}

function layoutEndLabels(labels: EndLabel[]): EndLabel[] {
  const sorted = [...labels].sort((a, b) => a.y - b.y)
  for (let i = 1; i < sorted.length; i++) {
    const gap = sorted[i].y - sorted[i - 1].y
    if (gap < LABEL_GAP) sorted[i].y = sorted[i - 1].y + LABEL_GAP
  }
  const overflow = sorted.length > 0 ? sorted[sorted.length - 1].y - Y1 : 0
  if (overflow > 0) for (const l of sorted) l.y = Math.max(Y0, l.y - overflow)
  return sorted
}

function lastValid(points: (number | null)[]): { i: number; v: number } | null {
  for (let i = points.length - 1; i >= 0; i--) {
    const v = points[i]
    if (v != null) return { i, v }
  }
  return null
}

export function LearningTrendChart({ weeks, series }: Props) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [hover, setHover] = useState<{ index: number; px: number; width: number } | null>(null)
  const n = weeks.length

  const endLabels = layoutEndLabels(
    series.flatMap((s) => {
      const lv = lastValid(s.points)
      return lv ? [{ action: s.action, color: s.color, v: lv.v, y: yFor(lv.v) }] : []
    }),
  )

  function onMove(e: React.MouseEvent) {
    const svg = svgRef.current
    if (!svg || n === 0) return
    const rect = svg.getBoundingClientRect()
    const svgX = ((e.clientX - rect.left) / rect.width) * VBW
    let idx = 0
    let best = Infinity
    for (let i = 0; i < n; i++) {
      const d = Math.abs(xFor(i, n) - svgX)
      if (d < best) {
        best = d
        idx = i
      }
    }
    setHover({ index: idx, px: (xFor(idx, n) / VBW) * rect.width, width: rect.width })
  }

  const gridRates = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div className="relative">
      {/* legend — identity is never colour-alone */}
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {series.map((s) => (
          <span key={s.action} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
            <span className="text-brand-fg/70 font-mono text-[11px] font-medium">{s.action}</span>
          </span>
        ))}
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${VBW} ${VBH}`}
        className="w-full"
        role="img"
        aria-label="Deterrent retreated-rate trend by pattern"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* gridlines + y labels */}
        {gridRates.map((r) => (
          <g key={r}>
            <line x1={X0} x2={X1} y1={yFor(r)} y2={yFor(r)} stroke={GRID} strokeWidth={1} />
            <text x={X0 - 8} y={yFor(r) + 3.5} textAnchor="end" fontFamily="'IBM Plex Mono',monospace" fontSize={10} fill={INK_MUTED}>
              {Math.round(r * 100)}%
            </text>
          </g>
        ))}

        {/* x labels */}
        {weeks.map((w, i) => (
          <text key={i} x={xFor(i, n)} y={VBH - 10} textAnchor="middle" fontFamily="'IBM Plex Mono',monospace" fontSize={10} fill={INK_MUTED}>
            {w}
          </text>
        ))}

        {/* crosshair */}
        {hover && (
          <line x1={xFor(hover.index, n)} x2={xFor(hover.index, n)} y1={Y0} y2={Y1} stroke="rgba(233,237,230,0.28)" strokeWidth={1} strokeDasharray="3 3" />
        )}

        {/* series lines (draw-in on mount) */}
        {series.map((s, si) =>
          segments(s.points, n).map((pts, k) => (
            <polyline
              key={`${s.action}-${k}`}
              points={pts}
              fill="none"
              stroke={s.color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
              pathLength={1}
              style={{ strokeDasharray: 1, animation: `et-draw 1.1s ease ${0.15 * si}s both` }}
            />
          )),
        )}

        {/* End-of-line direct labels. Two things were wrong when series converge:
            the labels sat at yFor(value), so equal final values (78% and 78%)
            printed on top of each other; and they were all muted ink, which relies
            on "identity via proximity" — exactly what stops working when the lines
            meet. Labels now take their series colour, and are nudged apart to keep a
            minimum vertical gap. */}
        {endLabels.map((l) => (
          <text
            key={`lbl-${l.action}`}
            x={X1 + 6}
            y={l.y + 3.5}
            fontFamily="'IBM Plex Mono',monospace"
            fontSize={10}
            fontWeight={600}
            fill={l.color}
          >
            {Math.round(l.v * 100)}%
          </text>
        ))}

        {/* hovered-bucket markers (surface ring separates overlaps) */}
        {hover &&
          series.map((s) => {
            const v = s.points[hover.index]
            if (v == null) return null
            return (
              <circle
                key={`dot-${s.action}`}
                cx={xFor(hover.index, n)}
                cy={yFor(v)}
                r={4}
                fill={s.color}
                stroke={SURFACE}
                strokeWidth={2}
              />
            )
          })}
      </svg>

      {/* tooltip */}
      {hover && (
        <div
          className="border-brand-fg/12 pointer-events-none absolute top-8 z-10 rounded-lg border bg-[rgba(7,13,10,0.94)] px-3 py-2 backdrop-blur-sm"
          style={{ left: Math.min(Math.max(hover.px, 8), hover.width - 140), transform: 'translateX(-50%)' }}
        >
          <p className="text-brand-fg/55 m-0 mb-1 font-mono text-[10px] font-semibold tracking-[0.06em]">{weeks[hover.index]}</p>
          <div className="flex flex-col gap-0.75">
            {series.map((s) => {
              const v = s.points[hover.index]
              return (
                <div key={s.action} className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-1.5">
                    <span className="h-2 w-2 rounded-full" style={{ background: s.color }} />
                    <span className="text-brand-fg/70 font-mono text-[10.5px]">{s.action}</span>
                  </span>
                  <span className="text-brand-fg font-mono text-[10.5px] font-semibold tabular-nums">
                    {v == null ? '—' : `${Math.round(v * 100)}%`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
