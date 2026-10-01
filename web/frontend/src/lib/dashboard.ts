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

// A node's role in a coordinated safe-herding corridor (CONTEXT.md §4). detect =
// first to sense the herd; deter = active on the village side to push it back;
// escort = kept quiet to hold the forest-side escape lane open.
export type CorridorRole = 'detect' | 'deter' | 'escort'

// Coordinated-corridor activation breakdown on an event (events.corridor). Groups
// the neighbour events of one herd movement and records this node's handoff role
// and order. Null on ordinary, uncoordinated detections.
export interface Corridor {
  activation: string // groups all events of one herd movement
  seq: number // 0-based order in the handoff sequence
  role: CorridorRole
  heading_deg: number // herd heading derived from node sequence (no TDOA)
  note: string // step-card action text
}

const ROLE_DISPLAY: Record<CorridorRole, { label: string; color: string }> = {
  detect: { label: 'DETECT', color: '#e2a13c' },
  deter: { label: 'DETER', color: '#e25b4a' },
  escort: { label: 'ESCORT', color: '#5fa97c' },
}

export function corridorRoleDisplay(role: CorridorRole): { label: string; color: string } {
  return ROLE_DISPLAY[role] ?? ROLE_DISPLAY.detect
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
  priority: string | null // normal | high | critical
  fusion: Fusion | null
  corridor: Corridor | null
  uplink: UplinkMeta | null
  created_at: string
}

// The LoRaWAN frame the event arrived in (events.uplink), as web/ingest writes
// it. Worth typing rather than ignoring: a real uplinked event carries no
// `fusion` breakdown - the frame has 11 bytes and cannot - so for everything
// that is not a demo row this is the only account of what the node did.
export interface UplinkMeta {
  seq?: number
  class?: number
  tier?: number
  flags?: number
  vision_confirmed?: boolean
  deterrent_fired?: boolean
  safe_mode?: boolean
  no_retreat?: boolean
  capture_ref?: number
}

// 'critical' is a no-retreat event (ADR 0034): the node fired its top tier and
// the animal was still there when it stopped watching. It pages like a 'high'
// and must not be *drawn* like one - "we have run out of options" is a
// different message from "an elephant is near the village", and a feed that
// renders them identically loses the distinction the device went to the
// trouble of measuring.
export function isUrgent(priority: string | null): boolean {
  return priority === 'high' || priority === 'critical'
}

export function isCritical(priority: string | null): boolean {
  return priority === 'critical'
}

export interface PriorityDisplay {
  label: string // short, upper case, for a pill
  color: string
  // Non-null only where the priority earns a filled badge rather than
  // coloured text. Only 'critical' does.
  fill: string | null
}

const PRIORITY_DISPLAY: Record<string, PriorityDisplay> = {
  critical: { label: 'NO RETREAT', color: '#070d0a', fill: '#e25b4a' },
  high: { label: 'HIGH', color: '#e25b4a', fill: null },
  normal: { label: 'ROUTINE', color: '#e2a13c', fill: null },
}

export function priorityDisplay(priority: string | null): PriorityDisplay {
  return PRIORITY_DISPLAY[priority ?? 'normal'] ?? PRIORITY_DISPLAY.normal
}

// Did the animal stay through a full deterrence sequence? Read from the routed
// priority rather than from the frame flag, because the priority is the value
// every other layer - the fan-out, the public risk view, the officer page -
// already acted on. The flag is kept as a cross-check for the detail card.
export function noRetreat(event: EventRow): boolean {
  return isCritical(event.priority) || event.uplink?.no_retreat === true
}

// How a species reads on screen. The six keys below are the entire vocabulary
// the wire format can carry (web/ingest/src/payload.ts's EVENT_CLASS_SPECIES);
// anything else reaching here is a legacy free-text row, a maintenance row that
// borrows the column, or a class from firmware newer than this build.
export interface SpeciesDisplay {
  label: string // sentence case, for a feed row or a detail line
  short: string // upper case, for the replay headline and the filter chips
  icon: string
  // Ordering only, for picking which species headlines a mixed incident. Not a
  // risk score and never shown.
  rank: number
}

const SPECIES_DISPLAY: Record<string, SpeciesDisplay> = {
  // Poaching sounds outrank the animals: they are the only classes that mean
  // people, and an incident holding both is about the people.
  gunshot: { label: 'Gunshot', short: 'GUNSHOT', icon: '\u{1F52B}', rank: 7 },
  chainsaw: { label: 'Chainsaw', short: 'CHAINSAW', icon: '\u{1FA9A}', rank: 6 },
  elephant: { label: 'Elephant', short: 'ELEPHANT', icon: '\u{1F418}', rank: 5 },
  // Heard and not seen, and deliberately given its own word and its own glyph.
  // The old icon lookup matched on substring, so 'elephant_call' drew the same
  // elephant as a camera confirmation - an officer deciding whether to drive
  // out was shown a photograph's certainty for a microphone's evidence.
  elephant_call: {
    label: 'Elephant heard',
    short: 'ELEPHANT HEARD',
    icon: '\u{1F4E3}',
    rank: 4,
  },
  boar: { label: 'Wild boar', short: 'BOAR', icon: '\u{1F417}', rank: 3 },
  fox: { label: 'Fox', short: 'FOX', icon: '\u{1F98A}', rank: 2 },
}

// Glyphs for species strings that are not wire classes: the demo's rejected
// cattle detection, and animals the hardware may meet but the device cannot
// name today. Matched by substring, which is what the feed has always done for
// free-text rows - but only *after* an exact wire-class lookup fails, so no
// entry here can shadow a real class again.
const FALLBACK_ICON: Record<string, string> = {
  cattle: '\u{1F404}',
  gaur: '\u{1F403}',
  deer: '\u{1F98C}',
  monkey: '\u{1F412}',
  leopard: '\u{1F406}',
  tiger: '\u{1F405}',
}

const UNKNOWN_ICON = '\u{1F4E1}'

function speciesKey(species: string | null | undefined): string {
  return (species ?? '').trim().toLowerCase()
}

export function speciesDisplay(species: string | null | undefined): SpeciesDisplay | null {
  return SPECIES_DISPLAY[speciesKey(species)] ?? null
}

// Every species the wire can carry, worst first. Exported so a test can assert
// this table covers the decoder, and so the filter chips have a stable order.
export function knownSpecies(): string[] {
  return Object.keys(SPECIES_DISPLAY).sort(
    (a, b) => SPECIES_DISPLAY[b].rank - SPECIES_DISPLAY[a].rank,
  )
}

// Never the raw column value: 'elephant_call' read as "Elephant_call", which
// is both ugly and wrong about what happened. An unrecognised value is
// de-snaked and sentence-cased rather than guessed at or hidden - a row the
// dashboard cannot name still has to be legible.
export function speciesLabel(species: string | null | undefined): string {
  const known = speciesDisplay(species)
  if (known) return known.label
  const key = speciesKey(species)
  if (!key) return 'Detection'
  const words = key.replace(/_/g, ' ')
  return words[0].toUpperCase() + words.slice(1)
}

export function speciesShort(species: string | null | undefined): string {
  return speciesDisplay(species)?.short ?? speciesLabel(species).toUpperCase()
}

export function speciesIcon(species: string | null | undefined): string {
  const known = speciesDisplay(species)
  if (known) return known.icon
  const key = speciesKey(species)
  if (!key) return UNKNOWN_ICON
  // Longest key first so the match is deterministic rather than dependent on
  // object insertion order.
  for (const name of Object.keys(FALLBACK_ICON).sort((a, b) => b.length - a.length)) {
    if (key.includes(name)) return FALLBACK_ICON[name]
  }
  return UNKNOWN_ICON
}

// Which species an incident is *about*. Replay used the earliest event that
// carried one, so a fox that walked past first titled an elephant incursion
// "FOX INCURSION". With six classes on the wire instead of two, a mixed cluster
// stopped being a corner case.
export function headlineSpecies(events: EventRow[]): string | null {
  let best: string | null = null
  let bestRank = -Infinity
  for (const e of events) {
    const key = speciesKey(e.species)
    if (!key) continue
    // An unrecognised species still beats nothing, but loses to any named one.
    const rank = SPECIES_DISPLAY[key]?.rank ?? 0
    if (rank > bestRank) {
      bestRank = rank
      best = e.species
    }
  }
  return best
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

// A generic 2-D point the incident geometry interpolates over (see lib/incident.ts).
// Carries a node's real position as left = longitude, top = latitude.
export interface MapPoint {
  left: number
  top: number
}

// Node positions as MapPoints for the incident math. Nodes without a fix are
// dropped — no invented coordinates, same rule as the map pins themselves.
export function geoPoints(nodes: NodeRow[]): Map<string, MapPoint> {
  const out = new Map<string, MapPoint>()
  for (const n of nodes) {
    if (n.lat == null || n.lng == null) continue
    out.set(n.id, { left: n.lng, top: n.lat })
  }
  return out
}

// A MapPoint as a Leaflet [lat, lng] pair.
export function toLatLng(p: MapPoint): [number, number] {
  return [p.top, p.left]
}

// Kothamangalam forest edge - the sector the pilot deployment covers. The map
// centres here, nodes without a fix fall back to it, and node placement is
// sanity-checked against it (lib/fleet.ts). It lives here rather than in
// LiveMap because it is a fact about the deployment, not about the map.
export const SECTOR_CENTER: [number, number] = [10.06, 76.63]

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
