// Deployment-planner geometry: turn a drawn boundary into a real node layout and
// derive every headline figure from it. The spacing rule is CONTEXT.md §6, not an
// invented number — nodes every 120-150 m along the boundary, GUARD at marked
// crossings and WATCH elsewhere, one gateway per 8-15 km. Nothing here fabricates
// a count: perimeter is summed from the ring, and the estimate follows the rule.

export type LatLng = [number, number]

const EARTH_R = 6_371_000 // metres
const RAD = Math.PI / 180

// CONTEXT.md §6 spacing envelope and gateway span.
export const SPACING_MIN = 120
export const SPACING_MAX = 150
export const SPACING_TARGET = 135 // used when no crossings anchor the layout
export const GATEWAY_MIN_KM = 8
export const GATEWAY_MAX_KM = 15
export const GATEWAY_TARGET_KM = 12
const INSTALL_MIN_PER_NODE = 20 // §6: 3-person install < 20 min per node
const INSTALL_TEAMS = 3

export function haversine(a: LatLng, b: LatLng): number {
  const dLat = (b[0] - a[0]) * RAD
  const dLng = (b[1] - a[1]) * RAD
  const lat1 = a[0] * RAD
  const lat2 = b[0] * RAD
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_R * Math.asin(Math.sqrt(h))
}

// The closed ring for a boundary: the vertices with the first repeated at the end.
export function closedRing(points: LatLng[]): LatLng[] {
  if (points.length < 2) return points
  return [...points, points[0]]
}

export function perimeter(points: LatLng[]): number {
  const ring = closedRing(points)
  let sum = 0
  for (let i = 0; i < ring.length - 1; i++) sum += haversine(ring[i], ring[i + 1])
  return sum
}

// Cumulative arc-length at each ring vertex, plus the total — the parameterization
// everything else indexes into.
function cumulative(ring: LatLng[]): { cum: number[]; total: number } {
  const cum = [0]
  for (let i = 0; i < ring.length - 1; i++) cum.push(cum[i] + haversine(ring[i], ring[i + 1]))
  return { cum, total: cum[cum.length - 1] }
}

// The lat/lng at arc-length `s` (wrapped into [0, total)) along the closed ring.
export function pointAtArc(points: LatLng[], s: number): LatLng {
  const ring = closedRing(points)
  const { cum, total } = cumulative(ring)
  if (total === 0) return ring[0]
  let d = ((s % total) + total) % total
  for (let i = 0; i < ring.length - 1; i++) {
    const segLen = cum[i + 1] - cum[i]
    if (d <= segLen || i === ring.length - 2) {
      const f = segLen === 0 ? 0 : d / segLen
      return [ring[i][0] + f * (ring[i + 1][0] - ring[i][0]), ring[i][1] + f * (ring[i + 1][1] - ring[i][1])]
    }
    d -= segLen
  }
  return ring[ring.length - 1]
}

// Local equirectangular metres about a reference latitude — accurate enough for
// point-to-segment projection at sector scale.
function toXY(p: LatLng, ref: LatLng): [number, number] {
  return [(p[1] - ref[1]) * RAD * EARTH_R * Math.cos(ref[0] * RAD), (p[0] - ref[0]) * RAD * EARTH_R]
}

// Arc-length position of the point on the boundary nearest `p` — used to snap a
// marked crossing onto the ring so it can anchor a GUARD.
export function projectToRing(points: LatLng[], p: LatLng): number {
  const ring = closedRing(points)
  const { cum } = cumulative(ring)
  const ref = ring[0]
  const pxy = toXY(p, ref)
  let bestDist = Infinity
  let bestArc = 0
  for (let i = 0; i < ring.length - 1; i++) {
    const a = toXY(ring[i], ref)
    const b = toXY(ring[i + 1], ref)
    const abx = b[0] - a[0]
    const aby = b[1] - a[1]
    const len2 = abx * abx + aby * aby
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((pxy[0] - a[0]) * abx + (pxy[1] - a[1]) * aby) / len2))
    const cx = a[0] + t * abx
    const cy = a[1] + t * aby
    const dist = Math.hypot(pxy[0] - cx, pxy[1] - cy)
    if (dist < bestDist) {
      bestDist = dist
      bestArc = cum[i] + t * (cum[i + 1] - cum[i])
    }
  }
  return bestArc
}

// Spherical-excess area of the polygon (m²), via the shoelace on the local plane —
// signed area magnitude, good to a fraction of a percent at these sizes.
export function areaSqm(points: LatLng[]): number {
  if (points.length < 3) return 0
  const ref = points[0]
  const xy = points.map((p) => toXY(p, ref))
  let a = 0
  for (let i = 0; i < xy.length; i++) {
    const j = (i + 1) % xy.length
    a += xy[i][0] * xy[j][1] - xy[j][0] * xy[i][1]
  }
  return Math.abs(a) / 2
}

export interface PlannedNodePlan {
  lat: number
  lng: number
  kind: 'guard' | 'watch'
  arc: number
}

export interface PlannerEstimate {
  perimeterM: number
  areaSqkm: number
  nodes: PlannedNodePlan[]
  guardCount: number
  watchCount: number
  gateways: number
  maxGapM: number
  spacingM: number // achieved even spacing when no crossings anchor the layout
  installMinutes: number
  // Honest brackets from the spacing envelope, shown beside the point estimates.
  nodeRange: [number, number]
  gatewayRange: [number, number]
  hasCrossings: boolean
  denserThanMin: boolean // P/n forces spacing below the 120 m minimum
}

// Place nodes along the boundary per CONTEXT.md §6 and derive every figure from
// the placement. `crossingArcs` are boundary arc-lengths (from projectToRing);
// each anchors a GUARD, and each arc between anchors is subdivided so no span
// exceeds SPACING_MAX.
export function planDeployment(points: LatLng[], crossingArcs: number[]): PlannerEstimate | null {
  if (points.length < 3) return null
  const P = perimeter(points)
  if (P === 0) return null
  const nodes: PlannedNodePlan[] = []

  const at = (arc: number, kind: 'guard' | 'watch'): PlannedNodePlan => {
    const [lat, lng] = pointAtArc(points, arc)
    return { lat, lng, kind, arc: ((arc % P) + P) % P }
  }

  const hasCrossings = crossingArcs.length > 0
  if (hasCrossings) {
    const anchors = [...crossingArcs.map((a) => ((a % P) + P) % P)].sort((x, y) => x - y)
    for (const a of anchors) nodes.push(at(a, 'guard'))
    // Subdivide each arc between consecutive anchors (wrapping the last→first).
    for (let i = 0; i < anchors.length; i++) {
      const cur = anchors[i]
      const next = i === anchors.length - 1 ? anchors[0] + P : anchors[i + 1]
      const L = next - cur
      const k = Math.max(0, Math.ceil(L / SPACING_MAX) - 1)
      for (let j = 1; j <= k; j++) nodes.push(at(cur + (j * L) / (k + 1), 'watch'))
    }
  } else {
    const n = Math.max(3, Math.ceil(P / SPACING_TARGET))
    for (let i = 0; i < n; i++) nodes.push(at((i * P) / n, 'watch'))
  }

  nodes.sort((a, b) => a.arc - b.arc)

  // Max gap between adjacent placed nodes (wrapping) — the coverage check.
  let maxGap = 0
  for (let i = 0; i < nodes.length; i++) {
    const a = nodes[i].arc
    const b = i === nodes.length - 1 ? nodes[0].arc + P : nodes[i + 1].arc
    maxGap = Math.max(maxGap, b - a)
  }

  const guardCount = nodes.filter((n) => n.kind === 'guard').length
  const watchCount = nodes.length - guardCount
  const Pkm = P / 1000
  const gateways = Math.max(1, Math.ceil(Pkm / GATEWAY_TARGET_KM))
  const installMinutes = Math.ceil((nodes.length * INSTALL_MIN_PER_NODE) / INSTALL_TEAMS)
  const spacing = nodes.length > 0 ? P / nodes.length : 0

  return {
    perimeterM: P,
    areaSqkm: areaSqm(points) / 1_000_000,
    nodes,
    guardCount,
    watchCount,
    gateways,
    maxGapM: maxGap,
    spacingM: spacing,
    installMinutes,
    nodeRange: [Math.ceil(P / SPACING_MAX), Math.ceil(P / SPACING_MIN)],
    gatewayRange: [Math.max(1, Math.ceil(Pkm / GATEWAY_MAX_KM)), Math.max(1, Math.ceil(Pkm / GATEWAY_MIN_KM))],
    hasCrossings,
    denserThanMin: spacing > 0 && spacing < SPACING_MIN,
  }
}

// Metres → a compact "1.4 km" / "820 m" label.
export function fmtDistance(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${Math.round(m)} m`
}
