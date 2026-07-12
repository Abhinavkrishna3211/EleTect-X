import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { statusDisplay, type NodeRow } from '@/lib/dashboard'

// Kothamangalam forest edge — the sector the pilot deployment covers. Used as
// the map centre and the fallback for nodes that have not reported a fix yet.
const SECTOR_CENTER: [number, number] = [10.06, 76.63]
const SECTOR_ZOOM = 13

// CARTO Voyager, rendered from OpenStreetMap data: road hierarchy, place names,
// natural colours — what an officer needs to see which road a herd is being
// steered away from. Free, no API key. The labels_under variant paints place
// labels beneath Leaflet's overlay panes, so pins, the corridor line and the
// herd marker are never crossed by a road name.
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'

const GOLD = '#E2A13C'
// Planner marker language, one colour+shape per meaning:
//   GUARD  — filled gold disc   (a node at a marked crossing)
//   WATCH  — hollow green ring  (a node filling the span between crossings)
//   VERTEX — small white dot    (a corner YOU drew, not a node)
//   CROSSING — red diamond      (a herd path you marked)
const PLANNER_GREEN = '#5FA97C'
const PLANNER_VERTEX = '#E9EDE6'

// fitBounds pads around a marker's anchor, but a pin is drawn well past it: the
// id pill hangs ~27px below and ~17px either side. Pad for the drawn pin, not
// the point, so an edge node's label is never clipped — and clear the label chip
// and legend that overlay the corners.
const PIN_PADDING: [number, number] = [56, 56]

// A node pin styled like SectorMap.dc.html: a glowing status dot with its id
// below, plus an animated ping ring while the node is alerting or is actively
// steering the herd. The id sits in a dark pill so it stays legible on the
// light basemap.
function pinHtml(node: NodeRow, selected: boolean, active: boolean): string {
  const { color } = statusDisplay(node.status)
  const ringing = active || node.status === 'alert'
  const ping = ringing
    ? `<span style="position:absolute;inset:0;border-radius:50%;border:1.5px solid ${color};animation:et-ping 1.4s ease-out infinite"></span>`
    : ''
  const glow = selected
    ? `box-shadow:0 0 0 3px rgba(226,161,60,0.9), 0 0 12px ${color}`
    : `box-shadow:0 0 10px ${color}${ringing ? 'ff' : '99'}`
  const pulse = active ? 'animation:et-pulse 1.4s ease-in-out infinite;' : ''
  return `
    <div style="position:relative;display:flex;flex-direction:column;align-items:center;gap:3px">
      <div style="position:relative;width:26px;height:26px;display:grid;place-items:center">
        ${ping}
        <span style="width:12px;height:12px;border-radius:50%;background:${color};border:1.5px solid rgba(7,13,10,0.85);${glow};${pulse}"></span>
      </div>
      <span style="font:600 8.5px 'IBM Plex Mono',monospace;color:rgba(233,237,230,0.9);letter-spacing:0.06em;white-space:nowrap;background:rgba(7,13,10,0.72);padding:1px 4px;border-radius:4px">${node.id}</span>
    </div>`
}

// The herd badge: a count in a gold disc under a ping ring, exactly as the
// abstract sector map drew it. Its position is animated by a CSS transition on
// the marker icon's transform (see .et-herd-marker in index.css).
function herdHtml(count: number, label: string): string {
  return `
    <div style="position:relative;display:flex;flex-direction:column;align-items:center;gap:4px">
      <div style="position:relative;width:34px;height:34px;display:grid;place-items:center">
        <span style="position:absolute;inset:0;border-radius:50%;border:1.5px solid ${GOLD};animation:et-ping 1.8s ease-out infinite"></span>
        <span style="width:18px;height:18px;border-radius:50%;background:${GOLD};color:#070D0A;display:grid;place-items:center;font:700 9px 'IBM Plex Mono',monospace">${count}</span>
      </div>
      <span style="font:700 8.5px 'IBM Plex Mono',monospace;letter-spacing:0.14em;color:${GOLD};background:rgba(7,13,10,0.78);padding:2px 5px;border-radius:4px;white-space:nowrap">${label}</span>
    </div>`
}

export interface HerdMarker {
  lat: number
  lng: number
  count: number
  label: string
}

// A node the planner proposes but has not deployed — rendered as a ghost pin.
export interface PlannedNode {
  lat: number
  lng: number
  kind: 'guard' | 'watch'
}

// The boundary the planner is drawing: ordered vertices, and whether the ring is
// closed. Rendered as a solid line distinct from the dashed corridor polyline.
export interface Boundary {
  points: [number, number][]
  closed: boolean
}

interface LiveMapProps {
  nodes: NodeRow[]
  // Pin selection is an Overview affordance; the incident views omit both.
  selectedNodeId?: string | null
  onSelect?: (id: string) => void
  // Nodes currently firing / steering the herd — they pulse regardless of status.
  activeNodeIds?: Set<string>
  // Interpolated herd position. Moves via a CSS transition, never a jump.
  herd?: HerdMarker | null
  herdTransitionMs?: number
  // Safe-herding corridor polyline, ordered [lat, lng] pairs.
  corridor?: [number, number][]
  // 'bounds' frames the located nodes; 'center' holds the fixed sector view.
  fit?: 'center' | 'bounds'
  // Header chip + status legend, as on the incident views.
  label?: string
  // ----- Deployment-planner drawing overlays (all optional; every existing
  // caller passes none, so the map renders exactly as before). -----
  // Fires with the clicked [lat, lng]; drives boundary/crossing placement.
  onMapClick?: (lat: number, lng: number) => void
  // Boundary being drawn (planner). Solid line + vertex dots.
  boundary?: Boundary | null
  // Proposed node layout (planner). Ghost pins: GUARD filled, WATCH hollow.
  plannedNodes?: PlannedNode[]
  // Marked boundary crossings (planner) as [lat, lng] pairs.
  crossings?: [number, number][]
  // Frame these points once when the signature changes (planner preset load).
  fitPoints?: [number, number][] | null
  // CSS cursor for the map surface (e.g. 'crosshair' while drawing).
  cursor?: string
}

export function LiveMap({
  nodes,
  selectedNodeId = null,
  onSelect,
  activeNodeIds,
  herd = null,
  herdTransitionMs = 0,
  corridor,
  fit = 'center',
  label,
  onMapClick,
  boundary = null,
  plannedNodes,
  crossings,
  fitPoints = null,
  cursor,
}: LiveMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // The planner is the only caller that passes a boundary or proposed nodes, so the
  // legend can switch itself rather than every call site passing a mode flag.
  const isPlanner = Boolean(boundary) || (plannedNodes?.length ?? 0) > 0 || (crossings?.length ?? 0) > 0

  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<Map<string, L.Marker>>(new Map())
  // Last rendered pin html per node. Re-setting an identical icon would swap the
  // DOM element and restart the ping animation on every tick of the replay head.
  const pinHtmlRef = useRef<Map<string, string>>(new Map())
  const herdRef = useRef<L.Marker | null>(null)
  const herdHtmlRef = useRef<string>('')
  const lineRef = useRef<L.Polyline | null>(null)
  const fittedRef = useRef<string>('')
  // Planner overlay layers, each a single group reconciled in place.
  const boundaryRef = useRef<L.LayerGroup | null>(null)
  const plannedRef = useRef<L.LayerGroup | null>(null)
  const crossingRef = useRef<L.LayerGroup | null>(null)
  const fitPointsRef = useRef<string>('')
  // Keep the latest onSelect without re-binding marker handlers each render.
  const onSelectRef = useRef(onSelect)
  useLayoutEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])
  // Same pattern for the map-click handler: keep it current without rebinding.
  const onMapClickRef = useRef(onMapClick)
  useLayoutEffect(() => {
    onMapClickRef.current = onMapClick
  }, [onMapClick])

  // Only nodes with a real fix get a pin — no inventing coordinates.
  const located = useMemo(() => nodes.filter((n) => n.lat != null && n.lng != null), [nodes])
  // Stable dep for a Set that is rebuilt on every parent render.
  const activeKey = activeNodeIds ? [...activeNodeIds].sort().join(',') : ''

  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    const map = L.map(containerRef.current, {
      center: SECTOR_CENTER,
      zoom: SECTOR_ZOOM,
      zoomControl: true,
      attributionControl: true,
    })
    L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 20, subdomains: 'abcd' }).addTo(map)

    // Leaflet rewrites marker transforms when the zoom settles. With a transition
    // on the herd icon that reposition would animate, sliding the marker off its
    // true position; suspend the transition for the duration of the zoom.
    const freeze = () => herdRef.current?.getElement()?.classList.add('et-no-transition')
    const thaw = () => {
      const el = herdRef.current?.getElement()
      if (el) requestAnimationFrame(() => el.classList.remove('et-no-transition'))
    }
    map.on('zoomstart', freeze).on('zoomend', thaw)

    // Delegate clicks to the latest handler (planner drawing). No-op otherwise.
    const click = (e: L.LeafletMouseEvent) => onMapClickRef.current?.(e.latlng.lat, e.latlng.lng)
    map.on('click', click)

    mapRef.current = map
    const markers = markersRef.current
    const pins = pinHtmlRef.current
    return () => {
      map.off('zoomstart', freeze).off('zoomend', thaw)
      map.off('click', click)
      map.remove()
      mapRef.current = null
      markers.clear()
      pins.clear()
      herdRef.current = null
      lineRef.current = null
      boundaryRef.current = null
      plannedRef.current = null
      crossingRef.current = null
    }
  }, [])

  // Frame the deployment once the node set resolves (incident views only).
  //
  // invalidateSize() first, always. Leaflet caches the container size at L.map()
  // time and getBoundsZoom() measures against that cache, not the DOM. The map
  // mounts before the surrounding header has settled, so the cached size is
  // stale by a layout pass — enough to pick a zoom level one step off in either
  // direction and push an edge node out of view.
  useEffect(() => {
    const map = mapRef.current
    if (!map || fit !== 'bounds' || located.length === 0) return
    const key = located.map((n) => n.id).join(',')
    if (fittedRef.current === key) return
    fittedRef.current = key
    map.invalidateSize(false)
    map.fitBounds(
      L.latLngBounds(located.map((n) => [n.lat as number, n.lng as number] as [number, number])),
      { padding: PIN_PADDING, maxZoom: 15 },
    )
  }, [located, fit])

  // Re-measure on container resize (orientation change, sidebar collapse) and
  // re-frame, so the fit never outlives the size it was computed against.
  useEffect(() => {
    const map = mapRef.current
    const container = containerRef.current
    if (!map || !container) return
    const observer = new ResizeObserver(() => {
      map.invalidateSize(false)
      if (fit !== 'bounds' || located.length === 0) return
      map.fitBounds(
        L.latLngBounds(located.map((n) => [n.lat as number, n.lng as number] as [number, number])),
        { padding: PIN_PADDING, maxZoom: 15, animate: false },
      )
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [located, fit])

  // Reconcile markers against the current node set (add / update / remove).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const markers = markersRef.current
    const pins = pinHtmlRef.current
    const seen = new Set<string>()

    for (const node of located) {
      seen.add(node.id)
      const latlng: [number, number] = [node.lat as number, node.lng as number]
      const html = pinHtml(node, node.id === selectedNodeId, activeNodeIds?.has(node.id) ?? false)
      const existing = markers.get(node.id)
      if (existing) {
        existing.setLatLng(latlng)
        if (pins.get(node.id) !== html) {
          existing.setIcon(L.divIcon({ html, className: 'et-node-pin', iconSize: [26, 40], iconAnchor: [13, 13] }))
        }
      } else {
        const icon = L.divIcon({ html, className: 'et-node-pin', iconSize: [26, 40], iconAnchor: [13, 13] })
        const marker = L.marker(latlng, { icon, title: node.name ?? node.id })
          .addTo(map)
          .on('click', () => onSelectRef.current?.(node.id))
        markers.set(node.id, marker)
      }
      pins.set(node.id, html)
    }

    for (const [id, marker] of markers) {
      if (!seen.has(id)) {
        marker.remove()
        markers.delete(id)
        pins.delete(id)
      }
    }
    // activeNodeIds is a fresh Set each render; activeKey is its stable identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [located, selectedNodeId, activeKey])

  // Corridor polyline. Leaflet draws it as SVG, so et-dash animates the flow.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!corridor || corridor.length < 2) {
      lineRef.current?.remove()
      lineRef.current = null
      return
    }
    if (lineRef.current) {
      lineRef.current.setLatLngs(corridor)
    } else {
      lineRef.current = L.polyline(corridor, {
        color: GOLD,
        weight: 2,
        dashArray: '6 5',
        className: 'et-corridor-line',
        interactive: false,
      }).addTo(map)
    }
  }, [corridor])

  // Herd marker. Created once and only moved — re-creating it per position would
  // restart the CSS transition and the movement would read as a jump.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (!herd) {
      herdRef.current?.remove()
      herdRef.current = null
      return
    }
    const latlng: [number, number] = [herd.lat, herd.lng]
    const html = herdHtml(herd.count, herd.label)
    const existing = herdRef.current
    if (existing) {
      existing.setLatLng(latlng)
      // Refresh the badge in place rather than via setIcon: setIcon swaps the
      // icon element, which is the one carrying the in-flight transform
      // transition, so the herd would teleport instead of gliding.
      const el = existing.getElement()
      if (el && herdHtmlRef.current !== html) el.innerHTML = html
      herdHtmlRef.current = html
    } else {
      herdHtmlRef.current = html
      herdRef.current = L.marker(latlng, {
        icon: L.divIcon({ html, className: 'et-herd-marker', iconSize: [34, 50], iconAnchor: [17, 17] }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 1000,
      }).addTo(map)
    }
  }, [herd])

  // Boundary line + vertex dots (planner). One layer group, rebuilt on change —
  // the vertex set is small and edits are user-paced, so no per-vertex diffing.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    boundaryRef.current?.remove()
    boundaryRef.current = null
    if (!boundary || boundary.points.length === 0) return
    const group = L.layerGroup().addTo(map)
    const ring: [number, number][] = boundary.closed
      ? [...boundary.points, boundary.points[0]]
      : boundary.points
    if (ring.length >= 2) {
      L.polyline(ring, { color: GOLD, weight: 2.5, opacity: 0.9, interactive: false }).addTo(group)
    }
    boundary.points.forEach((p, i) => {
      const first = i === 0 && !boundary.closed
      L.circleMarker(p, {
        radius: first ? 5 : 3.5,
        color: PLANNER_VERTEX,
        weight: first ? 2 : 1.5,
        fillColor: first ? '#070D0A' : PLANNER_VERTEX,
        fillOpacity: 1,
        interactive: false,
      }).addTo(group)
    })
    boundaryRef.current = group
  }, [boundary])

  // Proposed node layout (planner). Ghost pins: GUARD a filled gold disc, WATCH a
  // hollow ring — the same colour language as the deployment legend.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    plannedRef.current?.remove()
    plannedRef.current = null
    if (!plannedNodes || plannedNodes.length === 0) return
    const group = L.layerGroup().addTo(map)
    for (const pn of plannedNodes) {
      const guard = pn.kind === 'guard'
      const size = guard ? 14 : 11
      const html = guard
        ? `<span style="display:block;width:14px;height:14px;border-radius:50%;border:2px solid ${GOLD};background:${GOLD};box-shadow:0 0 8px rgba(226,161,60,0.75)"></span>`
        : `<span style="display:block;width:11px;height:11px;border-radius:50%;border:2px solid ${PLANNER_GREEN};background:transparent;box-shadow:0 0 5px rgba(95,169,124,0.5)"></span>`
      L.marker([pn.lat, pn.lng], {
        icon: L.divIcon({ html, className: 'et-planned-pin', iconSize: [size, size], iconAnchor: [size / 2, size / 2] }),
        interactive: false,
        keyboard: false,
      }).addTo(group)
    }
    plannedRef.current = group
  }, [plannedNodes])

  // Marked boundary crossings (planner) — a red diamond where a herd path meets
  // the boundary, the points that earn a GUARD role.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    crossingRef.current?.remove()
    crossingRef.current = null
    if (!crossings || crossings.length === 0) return
    const group = L.layerGroup().addTo(map)
    for (const c of crossings) {
      const html = `<span style="display:block;width:12px;height:12px;background:#e25b4a;transform:rotate(45deg);border:1.5px solid rgba(7,13,10,0.85);box-shadow:0 0 7px #e25b4a"></span>`
      L.marker(c, {
        icon: L.divIcon({ html, className: 'et-crossing-pin', iconSize: [12, 12], iconAnchor: [6, 6] }),
        interactive: false,
        keyboard: false,
        zIndexOffset: 500,
      }).addTo(group)
    }
    crossingRef.current = group
  }, [crossings])

  // Frame an explicit point set once when its signature changes (planner preset
  // load). Manual drawing passes none, so the view stays put under the cursor.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !fitPoints || fitPoints.length === 0) return
    const key = fitPoints.map((p) => `${p[0].toFixed(4)},${p[1].toFixed(4)}`).join('|')
    if (fitPointsRef.current === key) return
    fitPointsRef.current = key
    map.invalidateSize(false)
    map.fitBounds(L.latLngBounds(fitPoints), { padding: PIN_PADDING, maxZoom: 15 })
  }, [fitPoints])

  return (
    <div
      className="border-brand-fg/10 bg-brand-bg relative h-full w-full overflow-hidden rounded-2xl border"
      style={{ '--et-herd-ms': `${herdTransitionMs}ms` } as React.CSSProperties}
    >
      <div
        ref={containerRef}
        role="application"
        aria-label="Live sector map"
        className="h-full w-full"
        style={cursor ? { cursor } : undefined}
      />
      {label && (
        <>
          <div className="text-brand-fg/85 pointer-events-none absolute top-2.5 right-3 z-500 flex items-center gap-1.5 rounded bg-[rgba(7,13,10,0.72)] px-2 py-1 font-mono text-[9.5px] font-semibold">
            <span className="bg-brand-green inline-block h-1.75 w-1.75 rounded-full" />
            {label}
          </div>
          {/* The legend has to explain the markers actually on screen. On the planner
              the health legend was meaningless — it described node status while the
              map was showing GUARD/WATCH proposals, drawn corners and crossings, four
              marker types it never mentioned (three of which used to be gold). */}
          {isPlanner ? (
            <div className="text-brand-fg/85 pointer-events-none absolute bottom-2.5 left-3 z-500 flex flex-wrap gap-x-3 gap-y-1 rounded bg-[rgba(7,13,10,0.8)] px-2 py-1.5 font-mono text-[9px] font-medium">
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: GOLD, border: `1.5px solid ${GOLD}` }}
                />
                GUARD NODE
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{ background: 'transparent', border: `1.5px solid ${PLANNER_GREEN}` }}
                />
                WATCH NODE
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-1.75 w-1.75 rounded-full"
                  style={{ background: PLANNER_VERTEX }}
                />
                YOUR BOUNDARY CORNER
              </span>
              <span className="flex items-center gap-1">
                <span
                  className="inline-block h-2 w-2"
                  style={{ background: '#e25b4a', transform: 'rotate(45deg)' }}
                />
                CROSSING
              </span>
            </div>
          ) : (
            <div className="text-brand-fg/85 pointer-events-none absolute bottom-2.5 left-3 z-500 flex flex-wrap gap-3 rounded bg-[rgba(7,13,10,0.72)] px-2 py-1 font-mono text-[9px] font-medium">
              <span>
                <span className="bg-brand-green mr-1 inline-block h-1.75 w-1.75 rounded-full" />
                HEALTHY
              </span>
              <span>
                <span className="bg-brand-yellow mr-1 inline-block h-1.75 w-1.75 rounded-full" />
                ATTENTION
              </span>
              <span>
                <span className="bg-brand-red mr-1 inline-block h-1.75 w-1.75 rounded-full" />
                ALERT
              </span>
            </div>
          )}
        </>
      )}
    </div>
  )
}
