// Shared derivation for the Replay and Corridor views: turn a flat list of
// `events` into one coherent incident (a herd movement) and the geometry to
// animate it over the sector map. Movement comes from the node-detection
// sequence (CONTEXT.md §4, no TDOA) — either the explicit coordinated-corridor
// activation tag, or, absent that, the most recent time-contiguous cluster.

import type { EventRow, MapPoint } from './dashboard'

export function sortByTs(events: EventRow[]): EventRow[] {
  return [...events].sort((a, b) => a.ts.localeCompare(b.ts))
}

export function ms(iso: string): number {
  return new Date(iso).getTime()
}

// Events of the most recent coordinated-corridor activation, ordered by handoff
// sequence. Empty when nothing is corridor-tagged (caller falls back to a cluster).
export function latestActivation(events: EventRow[]): EventRow[] {
  const groups = new Map<string, EventRow[]>()
  for (const e of events) {
    if (!e.corridor) continue
    const arr = groups.get(e.corridor.activation) ?? []
    arr.push(e)
    groups.set(e.corridor.activation, arr)
  }
  let best: EventRow[] = []
  let bestTs = ''
  for (const arr of groups.values()) {
    const maxTs = arr.reduce((m, e) => (e.ts > m ? e.ts : m), '')
    if (maxTs > bestTs) {
      bestTs = maxTs
      best = arr
    }
  }
  return best.slice().sort((a, b) => (a.corridor!.seq - b.corridor!.seq) || a.ts.localeCompare(b.ts))
}

// Fallback incident: the most recent run of events with no gap larger than
// `gapMinutes` between neighbours. Returned ascending by time.
export function latestCluster(events: EventRow[], gapMinutes = 90): EventRow[] {
  const asc = sortByTs(events)
  if (asc.length === 0) return []
  const gap = gapMinutes * 60_000
  const chosen: EventRow[] = []
  for (let i = asc.length - 1; i >= 0; i--) {
    if (chosen.length === 0) {
      chosen.push(asc[i])
      continue
    }
    const earliest = chosen[chosen.length - 1]
    if (ms(earliest.ts) - ms(asc[i].ts) <= gap) chosen.push(asc[i])
    else break
  }
  return chosen.reverse()
}

// The incident's node path across the map, in order, dropping unlocated nodes and
// collapsing consecutive repeats — this is the safe-herding corridor polyline.
export function incidentPath(incident: EventRow[], points: Map<string, MapPoint>): MapPoint[] {
  const path: MapPoint[] = []
  for (const e of incident) {
    if (!e.node_id) continue
    const p = points.get(e.node_id)
    if (!p) continue
    const last = path[path.length - 1]
    if (last && last.left === p.left && last.top === p.top) continue
    path.push(p)
  }
  return path
}

// Herd position at wall-clock time `tMs`, interpolated between the map points of
// the two incident events that bracket it. Clamps to the first/last node outside
// the window. Null when no incident event has a located node.
export function herdAt(incident: EventRow[], points: Map<string, MapPoint>, tMs: number): MapPoint | null {
  const track = incident
    .map((e) => ({ t: ms(e.ts), p: e.node_id ? points.get(e.node_id) : undefined }))
    .filter((x): x is { t: number; p: MapPoint } => x.p != null)
  if (track.length === 0) return null
  if (tMs <= track[0].t) return track[0].p
  if (tMs >= track[track.length - 1].t) return track[track.length - 1].p
  for (let i = 0; i < track.length - 1; i++) {
    const a = track[i]
    const b = track[i + 1]
    if (tMs >= a.t && tMs <= b.t) {
      const f = b.t === a.t ? 0 : (tMs - a.t) / (b.t - a.t)
      return { left: a.p.left + f * (b.p.left - a.p.left), top: a.p.top + f * (b.p.top - a.p.top) }
    }
  }
  return track[track.length - 1].p
}

// HH:MM in IST, the sector's operating timezone.
const IST_HM = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Kolkata',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})
export function istHM(iso: string | number): string {
  return IST_HM.format(typeof iso === 'number' ? new Date(iso) : new Date(iso))
}
