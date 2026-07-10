import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { statusDisplay, type NodeRow } from '@/lib/dashboard'

// Kothamangalam forest edge — the sector the pilot deployment covers. Used as
// the map centre and the fallback for nodes that have not reported a fix yet.
const SECTOR_CENTER: [number, number] = [10.06, 76.63]
const SECTOR_ZOOM = 13

// CARTO dark basemap, rendered from OpenStreetMap data. Matches the dark ops
// design far better than the light raw-OSM raster while still being OSM-sourced.
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
const TILE_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>'

// A node pin styled like SectorMap.dc.html: a glowing status dot with its id
// below, plus an animated ping ring while the node is in the alert state.
function pinHtml(node: NodeRow, selected: boolean): string {
  const { color } = statusDisplay(node.status)
  const ping =
    node.status === 'alert'
      ? `<span style="position:absolute;inset:0;border-radius:50%;border:1.5px solid ${color};animation:et-ping 1.4s ease-out infinite"></span>`
      : ''
  const ring = selected ? `box-shadow:0 0 0 3px rgba(226,161,60,0.9), 0 0 12px ${color}` : `box-shadow:0 0 10px ${color}99`
  return `
    <div style="position:relative;display:flex;flex-direction:column;align-items:center;gap:3px">
      <div style="position:relative;width:26px;height:26px;display:grid;place-items:center">
        ${ping}
        <span style="width:12px;height:12px;border-radius:50%;background:${color};border:1.5px solid rgba(7,13,10,0.85);${ring}"></span>
      </div>
      <span style="font:600 8.5px 'IBM Plex Mono',monospace;color:rgba(233,237,230,0.75);letter-spacing:0.06em;white-space:nowrap;text-shadow:0 1px 3px #070d0a">${node.id}</span>
    </div>`
}

interface LiveMapProps {
  nodes: NodeRow[]
  selectedNodeId: string | null
  onSelect: (id: string) => void
}

export function LiveMap({ nodes, selectedNodeId, onSelect }: LiveMapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const markersRef = useRef<Map<string, L.Marker>>(new Map())
  // Keep the latest onSelect without re-binding marker handlers each render.
  const onSelectRef = useRef(onSelect)
  useLayoutEffect(() => {
    onSelectRef.current = onSelect
  }, [onSelect])

  // Only nodes with a real fix get a pin — no inventing coordinates.
  const located = useMemo(() => nodes.filter((n) => n.lat != null && n.lng != null), [nodes])

  useEffect(() => {
    if (mapRef.current || !containerRef.current) return
    const map = L.map(containerRef.current, {
      center: SECTOR_CENTER,
      zoom: SECTOR_ZOOM,
      zoomControl: true,
      attributionControl: true,
    })
    L.tileLayer(TILE_URL, { attribution: TILE_ATTRIBUTION, maxZoom: 19, subdomains: 'abcd' }).addTo(map)
    mapRef.current = map
    const markers = markersRef.current
    return () => {
      map.remove()
      mapRef.current = null
      markers.clear()
    }
  }, [])

  // Reconcile markers against the current node set (add / update / remove).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const markers = markersRef.current
    const seen = new Set<string>()

    for (const node of located) {
      seen.add(node.id)
      const latlng: [number, number] = [node.lat as number, node.lng as number]
      const html = pinHtml(node, node.id === selectedNodeId)
      const icon = L.divIcon({ html, className: 'et-node-pin', iconSize: [26, 40], iconAnchor: [13, 13] })
      const existing = markers.get(node.id)
      if (existing) {
        existing.setLatLng(latlng)
        existing.setIcon(icon)
      } else {
        const marker = L.marker(latlng, { icon, title: node.name ?? node.id })
          .addTo(map)
          .on('click', () => onSelectRef.current(node.id))
        markers.set(node.id, marker)
      }
    }

    for (const [id, marker] of markers) {
      if (!seen.has(id)) {
        marker.remove()
        markers.delete(id)
      }
    }
  }, [located, selectedNodeId])

  return (
    <div
      ref={containerRef}
      role="application"
      aria-label="Live sector map"
      className="border-brand-fg/10 bg-brand-bg h-full w-full overflow-hidden rounded-2xl border"
    />
  )
}
