// A compact trend line for a roster card — no axes, no labels, just the shape of
// the last two weeks. Same SVG idiom as LearningTrendChart (viewBox space,
// null-aware segments) scaled down. Gaps break the line rather than interpolating.

interface SparklineProps {
  values: (number | null)[]
  color: string
  // Fixed y-range so cards are comparable; defaults suit a 0-100 battery series.
  min?: number
  max?: number
  height?: number
}

const VBW = 100

export function Sparkline({ values, color, min = 0, max = 100, height = 26 }: SparklineProps) {
  const n = values.length
  const span = max - min || 1
  const xFor = (i: number) => (n <= 1 ? VBW / 2 : (i / (n - 1)) * VBW)
  const yFor = (v: number) => height - ((v - min) / span) * height

  // Break into continuous segments on null buckets.
  const segments: string[] = []
  let cur: string[] = []
  values.forEach((v, i) => {
    if (v == null) {
      if (cur.length) segments.push(cur.join(' '))
      cur = []
    } else {
      cur.push(`${xFor(i).toFixed(1)},${yFor(v).toFixed(1)}`)
    }
  })
  if (cur.length) segments.push(cur.join(' '))

  const last = [...values].reverse().find((v) => v != null) ?? null
  const lastIdx = last != null ? values.lastIndexOf(last) : -1

  return (
    <svg
      viewBox={`0 0 ${VBW} ${height}`}
      preserveAspectRatio="none"
      className="h-6.5 w-full overflow-visible"
      aria-hidden="true"
    >
      {segments.map((pts, i) => (
        <polyline
          key={i}
          points={pts}
          fill="none"
          stroke={color}
          strokeWidth={1.6}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      ))}
      {lastIdx >= 0 && last != null && (
        <circle cx={xFor(lastIdx)} cy={yFor(last)} r={1.8} fill={color} vectorEffect="non-scaling-stroke" />
      )}
    </svg>
  )
}
