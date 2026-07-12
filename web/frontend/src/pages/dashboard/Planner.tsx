import { useMemo, useState } from 'react'
import { useRealtimeTable } from '@/hooks/useRealtimeTable'
import { LiveMap, type PlannedNode } from '@/components/dashboard/LiveMap'
import type { NodeRow } from '@/lib/dashboard'
import {
  fmtDistance,
  planDeployment,
  pointAtArc,
  projectToRing,
  SPACING_MAX,
  type LatLng,
} from '@/lib/planner'

type Mode = 'draw' | 'cross' | 'idle'

// Preset boundaries around the Sector-7 pilot area, so a judge can get a real
// estimate in one click without drawing. Rough rings, deliberately not the exact
// node layout — the planner derives its own.
const PRESETS: { label: string; ring: LatLng[] }[] = [
  {
    label: 'Village boundary',
    ring: [
      [10.048, 76.612],
      [10.05, 76.624],
      [10.045, 76.63],
      [10.038, 76.622],
      [10.041, 76.612],
    ],
  },
  {
    label: 'Forest edge',
    ring: [
      [10.05, 76.61],
      [10.062, 76.62],
      [10.07, 76.638],
      [10.066, 76.655],
      [10.052, 76.652],
      [10.044, 76.632],
    ],
  },
  {
    label: 'Full sector',
    ring: [
      [10.04, 76.6],
      [10.058, 76.606],
      [10.078, 76.628],
      [10.082, 76.652],
      [10.07, 76.672],
      [10.048, 76.666],
      [10.033, 76.64],
      [10.03, 76.616],
    ],
  },
]

// Close the ring when the drawing click lands near the first vertex.
const CLOSE_SNAP_M = 90

function Tile({
  value,
  label,
  hint,
  color = '#E9EDE6',
  border = 'rgba(233,237,230,0.12)',
  bg,
}: {
  value: string
  label: string
  hint?: string
  color?: string
  border?: string
  bg?: string
}) {
  return (
    <div className="rounded-2xl border p-4.5" style={{ borderColor: border, background: bg }}>
      <p className="m-0 font-serif text-[34px] leading-none" style={{ color }}>
        {value}
      </p>
      <p className="text-brand-fg/55 mt-2 font-mono text-[11px] font-semibold tracking-[0.1em]">{label}</p>
      {hint && <p className="text-brand-fg/40 m-0 mt-1 font-mono text-[10.5px]">{hint}</p>}
    </div>
  )
}

export function Planner() {
  const { rows: nodeRows } = useRealtimeTable<NodeRow>('nodes', 'id', {
    orderBy: { column: 'id', ascending: true },
  })
  const nodes = useMemo(() => [...nodeRows.values()], [nodeRows])

  const [mode, setMode] = useState<Mode>('draw')
  const [points, setPoints] = useState<LatLng[]>([])
  const [closed, setClosed] = useState(false)
  const [crossings, setCrossings] = useState<LatLng[]>([])
  const [fitKey, setFitKey] = useState<LatLng[] | null>(null)

  function handleClick(lat: number, lng: number) {
    if (mode === 'draw' && !closed) {
      if (points.length >= 3) {
        const dLat = (lat - points[0][0]) * 111_320
        const dLng = (lng - points[0][1]) * 111_320 * Math.cos(points[0][0] * (Math.PI / 180))
        if (Math.hypot(dLat, dLng) < CLOSE_SNAP_M) {
          setClosed(true)
          setMode('cross')
          return
        }
      }
      setPoints((p) => [...p, [lat, lng]])
    } else if (mode === 'cross' && closed && points.length >= 3) {
      // Snap the crossing onto the boundary so it truly anchors a GUARD there.
      const arc = projectToRing(points, [lat, lng])
      setCrossings((c) => [...c, pointAtArc(points, arc)])
    }
  }

  function undo() {
    if (mode === 'cross' && crossings.length > 0) {
      setCrossings((c) => c.slice(0, -1))
    } else if (closed) {
      setClosed(false)
      setMode('draw')
    } else {
      setPoints((p) => p.slice(0, -1))
    }
  }

  function clearAll() {
    setPoints([])
    setCrossings([])
    setClosed(false)
    setMode('draw')
    setFitKey(null)
  }

  function loadPreset(ring: LatLng[]) {
    setPoints(ring)
    setClosed(true)
    setCrossings([])
    setMode('cross')
    setFitKey(ring)
  }

  const crossingArcs = useMemo(
    () => (closed && points.length >= 3 ? crossings.map((c) => projectToRing(points, c)) : []),
    [closed, points, crossings],
  )
  const estimate = useMemo(
    () => (closed && points.length >= 3 ? planDeployment(points, crossingArcs) : null),
    [closed, points, crossingArcs],
  )

  const plannedNodes: PlannedNode[] = useMemo(
    () => estimate?.nodes.map((n) => ({ lat: n.lat, lng: n.lng, kind: n.kind })) ?? [],
    [estimate],
  )

  const boundary = points.length > 0 ? { points, closed } : null
  const cursor = mode === 'idle' ? undefined : 'crosshair'
  const gapOk = estimate ? estimate.maxGapM <= SPACING_MAX : true

  return (
    <div className="flex max-w-5xl flex-col gap-4">
      <div>
        <h1 className="m-0 mb-1 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Deployment planner</h1>
        <p className="text-brand-fg/60 m-0 max-w-[70ch] font-sans text-sm leading-relaxed">
          Draw a boundary on the sector map. The planner spaces nodes along it by the field rule, GUARD at the
          crossings you mark and WATCH between them, and derives the count, gateways, and coverage from the drawn
          geometry.
        </p>
      </div>

      {/* Toolbar. Two labelled groups, boxed. It used to be one flat row of eight
          pills split by a thin "·", so "Village boundary" (load a preset shape) sat
          beside "Clear" (destroy your work) with nothing to say they were different
          kinds of action. */}
      <div className="flex flex-wrap items-stretch gap-2.5">
        <div className="border-brand-fg/10 flex flex-wrap items-center gap-2 rounded-xl border bg-[#0B0D0B] px-3 py-2.5">
          <span className="text-brand-fg/35 mr-0.5 font-mono text-[9.5px] font-semibold tracking-[0.1em]">
            DRAWING
          </span>
          <button
            onClick={() => setMode('draw')}
            disabled={closed}
            className={`rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors disabled:opacity-40 ${
              mode === 'draw'
                ? 'border-brand-gold text-brand-gold bg-[rgba(226,161,60,0.1)]'
                : 'border-brand-fg/15 text-brand-fg/60 hover:text-brand-fg'
            }`}
          >
            Draw boundary
          </button>
          <button
            onClick={() => setMode('cross')}
            disabled={!closed}
            className={`rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors disabled:opacity-40 ${
              mode === 'cross'
                ? 'border-brand-red text-brand-red bg-[rgba(226,91,74,0.1)]'
                : 'border-brand-fg/15 text-brand-fg/60 hover:text-brand-fg'
            }`}
          >
            Mark crossings
          </button>
          {mode === 'draw' && !closed && points.length >= 3 && (
            <button
              onClick={() => {
                setClosed(true)
                setMode('cross')
              }}
              className="border-brand-green text-brand-green rounded-full border bg-[rgba(95,169,124,0.1)] px-3.5 py-1.5 font-sans text-[12.5px] font-semibold"
            >
              Close boundary
            </button>
          )}
          <button
            onClick={undo}
            className="border-brand-fg/15 text-brand-fg/60 hover:text-brand-fg rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors"
          >
            Undo
          </button>
          {/* Destructive, so it reads red rather than sitting in the row looking like
              every other pill. */}
          <button
            onClick={clearAll}
            className="border-brand-red/30 text-brand-red/80 hover:border-brand-red hover:text-brand-red rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors"
          >
            Clear
          </button>
        </div>

        <div className="border-brand-fg/10 flex flex-wrap items-center gap-2 rounded-xl border bg-[#0B0D0B] px-3 py-2.5">
          <span className="text-brand-fg/35 mr-0.5 font-mono text-[9.5px] font-semibold tracking-[0.1em]">
            PRESET SHAPE
          </span>
          {PRESETS.map((p) => (
            <button
              key={p.label}
              onClick={() => loadPreset(p.ring)}
              className="border-brand-fg/15 text-brand-fg/60 hover:text-brand-fg rounded-full border px-3.5 py-1.5 font-sans text-[12.5px] font-semibold transition-colors"
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="h-[clamp(320px,46vw,460px)]">
        <LiveMap
          nodes={nodes}
          onMapClick={handleClick}
          boundary={boundary}
          plannedNodes={plannedNodes}
          crossings={crossings}
          fitPoints={fitKey}
          cursor={cursor}
          label={mode === 'cross' ? 'CLICK TO MARK CROSSINGS' : closed ? 'BOUNDARY CLOSED' : 'CLICK TO DRAW BOUNDARY'}
        />
      </div>

      {!estimate ? (
        <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-8 text-center">
          <p className="text-brand-fg/50 m-0 font-sans text-sm">
            Draw at least three points and close the boundary, or load a preset, to see the estimate.
          </p>
        </div>
      ) : (
        <>
          <div className="grid gap-2.5 [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
            <Tile
              value={String(estimate.nodes.length)}
              label="NODES REQUIRED"
              hint={`range ${estimate.nodeRange[0]}–${estimate.nodeRange[1]}`}
              color="#E2A13C"
              border="rgba(226,161,60,0.3)"
              bg="rgba(226,161,60,0.05)"
            />
            {/* Separator is a slash, not a middot: "0 · 40" at tile size reads as the
                decimal 0.40, which is exactly how it was being misread. */}
            <Tile
              value={`${estimate.guardCount} / ${estimate.watchCount}`}
              label="GUARD / WATCH"
              hint={estimate.hasCrossings ? 'guard at crossings' : 'mark crossings for guard'}
              color="#5FA97C"
              border="rgba(95,169,124,0.3)"
              bg="rgba(95,169,124,0.05)"
            />
            <Tile
              value={String(estimate.gateways)}
              label="GATEWAYS"
              hint={`range ${estimate.gatewayRange[0]}–${estimate.gatewayRange[1]}`}
            />
            <Tile
              value={fmtDistance(estimate.maxGapM)}
              label="MAX GAP"
              hint={gapOk ? `within ${SPACING_MAX} m rule` : `exceeds ${SPACING_MAX} m`}
              color={gapOk ? '#5FA97C' : '#E25B4A'}
              border={gapOk ? 'rgba(233,237,230,0.12)' : 'rgba(226,91,74,0.4)'}
            />
          </div>

          {/* Show-your-math */}
          <div className="border-brand-fg/10 rounded-2xl border bg-[#0B0D0B] p-5">
            <h3 className="m-0 mb-3 font-sans text-sm font-semibold">How this is derived</h3>
            <div className="text-brand-fg/70 flex flex-col gap-1.5 font-mono text-[12px] leading-relaxed">
              <p className="m-0">
                Perimeter, summed over the boundary ={' '}
                <span className="text-brand-fg">{fmtDistance(estimate.perimeterM)}</span>
                {' · '}enclosed area <span className="text-brand-fg">{estimate.areaSqkm.toFixed(2)} km²</span>
              </p>
              <p className="m-0">
                Nodes: spacing 120–150 m ⇒ ⌈{Math.round(estimate.perimeterM)} / 150⌉ to ⌈
                {Math.round(estimate.perimeterM)} / 120⌉ ={' '}
                <span className="text-brand-fg">
                  {estimate.nodeRange[0]}–{estimate.nodeRange[1]}
                </span>
                ; placed <span className="text-brand-fg">{estimate.nodes.length}</span> at{' '}
                <span className="text-brand-fg">{Math.round(estimate.spacingM)} m</span> apart
                {estimate.denserThanMin ? ' (denser than the 120 m minimum — short boundary)' : ''}
              </p>
              <p className="m-0">
                {estimate.hasCrossings
                  ? `Roles: 1 GUARD per marked crossing (${estimate.guardCount}), WATCH filling each arc so no span exceeds 150 m`
                  : 'Roles: all WATCH until crossings are surveyed — GUARD anchors need a marked crossing'}
              </p>
              <p className="m-0">
                Gateways: 1 per 8–15 km ⇒ ⌈{(estimate.perimeterM / 1000).toFixed(2)} / 12⌉ ={' '}
                <span className="text-brand-fg">{estimate.gateways}</span>
              </p>
              <p className="m-0">
                Max span between adjacent nodes ={' '}
                <span style={{ color: gapOk ? '#5FA97C' : '#E25B4A' }}>{fmtDistance(estimate.maxGapM)}</span>
                {' · '}install ≈ <span className="text-brand-fg">{estimate.installMinutes} min</span> with 3-person
                teams
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
