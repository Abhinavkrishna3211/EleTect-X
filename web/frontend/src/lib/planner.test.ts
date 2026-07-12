import { describe, expect, it } from 'vitest'
import {
  GATEWAY_MAX_KM,
  GATEWAY_MIN_KM,
  SPACING_MAX,
  SPACING_MIN,
  areaSqm,
  closedRing,
  fmtDistance,
  haversine,
  perimeter,
  planDeployment,
  pointAtArc,
  projectToRing,
  type LatLng,
} from './planner'

// A ~1 km square near Kothamangalam, so the numbers stay in the range the
// planner actually operates on rather than at degenerate scales.
const ORIGIN: LatLng = [10.058, 76.628]
// 0.009 deg latitude ~= 1 km; the longitude delta is scaled by cos(lat) so the
// square is genuinely square on the ground rather than only in degrees.
const DLAT = 0.009
const DLNG = 0.009 / Math.cos(ORIGIN[0] * (Math.PI / 180))
const SQUARE: LatLng[] = [
  ORIGIN,
  [ORIGIN[0], ORIGIN[1] + DLNG],
  [ORIGIN[0] + DLAT, ORIGIN[1] + DLNG],
  [ORIGIN[0] + DLAT, ORIGIN[1]],
]

describe('haversine', () => {
  it('is zero for a point against itself', () => {
    expect(haversine(ORIGIN, ORIGIN)).toBe(0)
  })

  it('measures a known meridian arc: 0.009 deg latitude is ~1 km', () => {
    const d = haversine(ORIGIN, [ORIGIN[0] + DLAT, ORIGIN[1]])
    expect(d).toBeGreaterThan(995)
    expect(d).toBeLessThan(1005)
  })

  it('is symmetric', () => {
    const a: LatLng = [10.0, 76.6]
    const b: LatLng = [10.1, 76.7]
    expect(haversine(a, b)).toBeCloseTo(haversine(b, a), 6)
  })
})

describe('closedRing / perimeter', () => {
  it('repeats the first vertex to close the ring', () => {
    const ring = closedRing(SQUARE)
    expect(ring).toHaveLength(SQUARE.length + 1)
    expect(ring[ring.length - 1]).toEqual(SQUARE[0])
  })

  it('leaves a degenerate ring alone rather than duplicating a single point', () => {
    expect(closedRing([ORIGIN])).toEqual([ORIGIN])
  })

  it('sums all four sides of a ~1 km square to a ~4 km perimeter', () => {
    const p = perimeter(SQUARE)
    expect(p).toBeGreaterThan(3980)
    expect(p).toBeLessThan(4020)
  })
})

describe('areaSqm', () => {
  it('measures a ~1 km square as ~1e6 m2', () => {
    const a = areaSqm(SQUARE)
    expect(a).toBeGreaterThan(0.99e6)
    expect(a).toBeLessThan(1.01e6)
  })

  it('is zero for anything that is not a polygon', () => {
    expect(areaSqm([ORIGIN, [ORIGIN[0] + DLAT, ORIGIN[1]]])).toBe(0)
  })
})

describe('pointAtArc', () => {
  it('returns the first vertex at arc 0', () => {
    expect(pointAtArc(SQUARE, 0)).toEqual(SQUARE[0])
  })

  it('wraps a full lap back to the start', () => {
    const P = perimeter(SQUARE)
    const [lat, lng] = pointAtArc(SQUARE, P)
    expect(lat).toBeCloseTo(SQUARE[0][0], 6)
    expect(lng).toBeCloseTo(SQUARE[0][1], 6)
  })

  it('wraps a negative arc to the equivalent forward position', () => {
    const P = perimeter(SQUARE)
    const back = pointAtArc(SQUARE, -P / 4)
    const fwd = pointAtArc(SQUARE, (3 * P) / 4)
    expect(back[0]).toBeCloseTo(fwd[0], 6)
    expect(back[1]).toBeCloseTo(fwd[1], 6)
  })
})

describe('projectToRing', () => {
  it('snaps a point already on the boundary to its own arc position', () => {
    const P = perimeter(SQUARE)
    const onEdge = pointAtArc(SQUARE, P / 8)
    expect(projectToRing(SQUARE, onEdge)).toBeCloseTo(P / 8, 0)
  })

  it('snaps an off-boundary point to the nearest boundary position', () => {
    // Just outside the middle of the southern edge — should land near arc P/8
    // (halfway along the first side), not at a corner.
    const P = perimeter(SQUARE)
    const outside: LatLng = [ORIGIN[0] - 0.002, ORIGIN[1] + DLNG / 2]
    const arc = projectToRing(SQUARE, outside)
    expect(arc).toBeCloseTo(P / 8, -1)
  })
})

describe('planDeployment', () => {
  it('returns null for anything that is not a polygon', () => {
    expect(planDeployment([], [])).toBeNull()
    expect(planDeployment([ORIGIN, [ORIGIN[0] + DLAT, ORIGIN[1]]], [])).toBeNull()
  })

  // The load-bearing rule from CONTEXT.md §6: nodes every 120-150 m. Whatever
  // the boundary, no two adjacent nodes may end up further apart than the
  // maximum — that is a coverage hole in the field, not a rounding detail.
  it('never leaves a gap wider than the 150 m spacing maximum (no crossings)', () => {
    const plan = planDeployment(SQUARE, [])!
    expect(plan.maxGapM).toBeLessThanOrEqual(SPACING_MAX + 1e-6)
  })

  it('never leaves a gap wider than the maximum with crossings anchoring the layout', () => {
    const P = perimeter(SQUARE)
    const plan = planDeployment(SQUARE, [0, P / 3, (2 * P) / 3])!
    expect(plan.maxGapM).toBeLessThanOrEqual(SPACING_MAX + 1e-6)
  })

  it('places one GUARD per marked crossing and WATCH everywhere else', () => {
    const P = perimeter(SQUARE)
    const plan = planDeployment(SQUARE, [0, P / 2])!
    expect(plan.guardCount).toBe(2)
    expect(plan.watchCount).toBe(plan.nodes.length - 2)
    expect(plan.hasCrossings).toBe(true)
    expect(plan.nodes.filter((n) => n.kind === 'guard')).toHaveLength(2)
  })

  it('places only WATCH nodes when no crossing is marked', () => {
    const plan = planDeployment(SQUARE, [])!
    expect(plan.guardCount).toBe(0)
    expect(plan.hasCrossings).toBe(false)
    expect(plan.nodes.every((n) => n.kind === 'watch')).toBe(true)
  })

  it('brackets the node count by the spacing envelope', () => {
    const plan = planDeployment(SQUARE, [])!
    const [lo, hi] = plan.nodeRange
    expect(lo).toBe(Math.ceil(plan.perimeterM / SPACING_MAX))
    expect(hi).toBe(Math.ceil(plan.perimeterM / SPACING_MIN))
    expect(lo).toBeLessThanOrEqual(hi)
  })

  it('brackets gateways by the 8-15 km span and always plans at least one', () => {
    const plan = planDeployment(SQUARE, [])!
    const km = plan.perimeterM / 1000
    expect(plan.gatewayRange[0]).toBe(Math.max(1, Math.ceil(km / GATEWAY_MAX_KM)))
    expect(plan.gatewayRange[1]).toBe(Math.max(1, Math.ceil(km / GATEWAY_MIN_KM)))
    // A 4 km boundary is well under a single gateway's 8-15 km span.
    expect(plan.gateways).toBe(1)
  })

  it('keeps arcs sorted and inside [0, perimeter)', () => {
    const plan = planDeployment(SQUARE, [])!
    const arcs = plan.nodes.map((n) => n.arc)
    expect([...arcs].sort((a, b) => a - b)).toEqual(arcs)
    for (const a of arcs) {
      expect(a).toBeGreaterThanOrEqual(0)
      expect(a).toBeLessThan(plan.perimeterM)
    }
  })

  // Crossings closer together than the minimum spacing force nodes denser than
  // the 120 m floor. The planner honours the crossings (a GUARD must sit on a
  // real crossing) and flags the violation rather than silently dropping one.
  it('flags denserThanMin when crossings force spacing below the 120 m floor', () => {
    const P = perimeter(SQUARE)
    const tight = Array.from({ length: 40 }, (_, i) => (i * P) / 40)
    const plan = planDeployment(SQUARE, tight)!
    expect(plan.spacingM).toBeLessThan(SPACING_MIN)
    expect(plan.denserThanMin).toBe(true)
  })

  it('does not flag denserThanMin for a normally spaced layout', () => {
    const plan = planDeployment(SQUARE, [])!
    expect(plan.spacingM).toBeGreaterThanOrEqual(SPACING_MIN)
    expect(plan.denserThanMin).toBe(false)
  })

  it('derives install time from a 3-person team at 20 min per node', () => {
    const plan = planDeployment(SQUARE, [])!
    expect(plan.installMinutes).toBe(Math.ceil((plan.nodes.length * 20) / 3))
  })
})

describe('fmtDistance', () => {
  it('uses metres below a kilometre', () => {
    expect(fmtDistance(820)).toBe('820 m')
    expect(fmtDistance(999.4)).toBe('999 m')
  })

  it('switches to kilometres at exactly 1000 m', () => {
    expect(fmtDistance(1000)).toBe('1.00 km')
    expect(fmtDistance(1440)).toBe('1.44 km')
  })
})
