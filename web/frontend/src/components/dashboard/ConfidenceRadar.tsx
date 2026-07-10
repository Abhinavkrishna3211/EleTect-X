import type { Modality, ModalityKind } from '@/lib/dashboard'

// Triangle radar matching the design: vision at top, audio lower-right, seismic
// lower-left. Each axis runs from the centroid (confidence 0) out to the vertex
// (confidence 1), so a dropped-out modality collapses cleanly to the centre.
const VERTEX: Record<ModalityKind, [number, number]> = {
  vision: [60, 10],
  acoustic: [110, 92],
  seismic: [10, 92],
}
const CENTER: [number, number] = [60, 64.67]

function point(kind: ModalityKind, confidence: number): [number, number] {
  const [vx, vy] = VERTEX[kind]
  const c = Math.max(0, Math.min(1, confidence))
  return [CENTER[0] + c * (vx - CENTER[0]), CENTER[1] + c * (vy - CENTER[1])]
}

function toStr(p: [number, number]): string {
  return `${p[0].toFixed(1)},${p[1].toFixed(1)}`
}

export function ConfidenceRadar({ modalities }: { modalities: Modality[] }) {
  const byKind = new Map(modalities.map((m) => [m.kind, m]))
  const order: ModalityKind[] = ['vision', 'acoustic', 'seismic']

  const dataPoints = order
    .map((kind) => {
      const m = byKind.get(kind)
      const conf = m?.available && m.confidence != null ? m.confidence : 0
      return toStr(point(kind, conf))
    })
    .join(' ')

  const labelStyle = (kind: ModalityKind) =>
    byKind.get(kind)?.available ? 'rgba(233,237,230,0.55)' : 'rgba(233,237,230,0.28)'

  return (
    <svg width="120" height="110" viewBox="0 0 120 110" aria-label="Per-sensor confidence radar" role="img">
      {/* guide rings: outer (100%) and inner (50%) */}
      <polygon points="60,10 110,92 10,92" fill="none" stroke="rgba(233,237,230,0.15)" strokeWidth="1" />
      <polygon points="60,37 93,81 27,81" fill="none" stroke="rgba(233,237,230,0.1)" strokeWidth="1" />
      {/* fused shape */}
      <polygon points={dataPoints} fill="rgba(226,161,60,0.25)" stroke="#E2A13C" strokeWidth="1.5" />
      <text x="60" y="8" textAnchor="middle" fontFamily="'IBM Plex Mono',monospace" fontSize="8" fontWeight="600" fill={labelStyle('vision')}>
        VISION
      </text>
      <text x="114" y="101" textAnchor="end" fontFamily="'IBM Plex Mono',monospace" fontSize="8" fontWeight="600" fill={labelStyle('acoustic')}>
        AUDIO
      </text>
      <text x="6" y="101" textAnchor="start" fontFamily="'IBM Plex Mono',monospace" fontSize="8" fontWeight="600" fill={labelStyle('seismic')}>
        SEISMIC
      </text>
    </svg>
  )
}
