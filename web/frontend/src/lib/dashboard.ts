// Shared types and helpers for the ops dashboard. Mirrors the Supabase schema
// in web/backend/schema.sql (nodes / events / health) plus the fusion breakdown
// that backs the explainable-AI decision card (CONTEXT.md §4).

export type NodeStatus = 'online' | 'offline' | 'alert' | 'maintenance'

export interface NodeRow {
  id: string
  name: string | null
  lat: number | null
  lng: number | null
  kind: string | null // guard | watch
  status: NodeStatus
  firmware: string | null
  battery_pct: number | null
  solar_w: number | null
  last_seen: string | null
  created_at: string
}

export type ModalityKind = 'seismic' | 'acoustic' | 'vision'

// One sensing modality's contribution to a fused decision. A modality that did
// not report is available=false — logodds/confidence are null and it must render
// as "dropped out", not as a zero.
export interface Modality {
  kind: ModalityKind
  available: boolean
  weight: number
  logodds: number | null
  baseline: number
  contribution: number
  confidence: number | null // σ(logodds), 0..1
}

// Log-odds fusion behind events.confidence: L = L_prior + Σ aᵢ wᵢ (ℓᵢ − ℓ₀ᵢ).
export interface Fusion {
  prior: number
  logodds: number // fused L; σ(logodds) == events.confidence
  modalities: Modality[]
}

export interface EventRow {
  id: number
  node_id: string | null
  ts: string
  species: string | null
  confidence: number | null // 0..1, fused P
  direction_deg: number | null
  media_url: string | null
  action: string | null
  outcome: string | null
  priority: string | null // normal | high
  fusion: Fusion | null
  created_at: string
}

export interface HealthRow {
  id: number
  node_id: string | null
  ts: string
  battery_pct: number | null
  solar_w: number | null
  temp_c: number | null
  metrics: Record<string, unknown> | null
}

// The three display buckets the design legend uses (HEALTHY / ATTENTION / ALERT),
// plus OFFLINE. node_status collapses onto them for pin + tile colouring.
export interface StatusDisplay {
  label: string
  color: string
}

const STATUS_DISPLAY: Record<NodeStatus, StatusDisplay> = {
  online: { label: 'HEALTHY', color: '#5fa97c' },
  maintenance: { label: 'ATTENTION', color: '#d9b44a' },
  alert: { label: 'ALERT', color: '#e25b4a' },
  offline: { label: 'OFFLINE', color: '#6b7a70' },
}

export function statusDisplay(status: NodeStatus): StatusDisplay {
  return STATUS_DISPLAY[status] ?? STATUS_DISPLAY.offline
}

export function sigmoid(logodds: number): number {
  return 1 / (1 + Math.exp(-logodds))
}

// The fused confidence to headline on the decision card: the stored scalar if
// present, otherwise derived from the fusion log-odds.
export function fusedConfidence(event: EventRow): number | null {
  if (event.confidence != null) return event.confidence
  if (event.fusion) return sigmoid(event.fusion.logodds)
  return null
}

const MODALITY_LABEL: Record<ModalityKind, string> = {
  seismic: 'Ground vibration',
  acoustic: 'Audio',
  vision: 'Vision',
}

export function modalityLabel(kind: ModalityKind): string {
  return MODALITY_LABEL[kind] ?? kind
}

// Compact relative time ("40 s ago", "12 m ago", "2 d ago") for last_seen /
// event timestamps. Returns "never" for a missing timestamp.
export function relativeTime(iso: string | null): string {
  if (!iso) return 'never'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'unknown'
  const secs = Math.round((Date.now() - then) / 1000)
  if (secs < 0) return 'just now'
  if (secs < 60) return `${secs} s ago`
  const mins = Math.round(secs / 60)
  if (mins < 60) return `${mins} m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return `${days} d ago`
}
