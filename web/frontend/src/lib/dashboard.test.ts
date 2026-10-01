import { readFileSync } from 'node:fs'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  fusedConfidence,
  geoPoints,
  headlineSpecies,
  isCritical,
  isUrgent,
  knownSpecies,
  modalityLabel,
  noRetreat,
  priorityDisplay,
  relativeTime,
  sigmoid,
  speciesIcon,
  speciesLabel,
  speciesShort,
  statusDisplay,
  toLatLng,
  type EventRow,
  type NodeRow,
} from './dashboard'

const NOW = new Date('2026-07-12T12:00:00.000Z')

describe('sigmoid', () => {
  // This is P = sigma(L) from the frozen fusion design (CONTEXT.md §4, ADR 0001
  // §6). The UI headlines the number it produces, so it is worth pinning rather
  // than assuming.
  it('maps zero log-odds to even odds', () => {
    expect(sigmoid(0)).toBe(0.5)
  })

  it('is monotonic and bounded in (0, 1)', () => {
    expect(sigmoid(-10)).toBeGreaterThan(0)
    expect(sigmoid(-10)).toBeLessThan(sigmoid(0))
    expect(sigmoid(0)).toBeLessThan(sigmoid(10))
    expect(sigmoid(10)).toBeLessThan(1)
  })

  it('is symmetric about zero: sigma(-x) === 1 - sigma(x)', () => {
    expect(sigmoid(-2)).toBeCloseTo(1 - sigmoid(2), 12)
  })

  it('matches the closed form at a known point', () => {
    expect(sigmoid(2)).toBeCloseTo(1 / (1 + Math.exp(-2)), 12)
  })
})

describe('fusedConfidence', () => {
  it('prefers the stored scalar when the event carries one', () => {
    const e = { confidence: 0.85, fusion: { logodds: 5 } } as EventRow
    expect(fusedConfidence(e)).toBe(0.85)
  })

  it('derives from the fusion log-odds when no scalar is stored', () => {
    const e = { confidence: null, fusion: { logodds: 0 } } as unknown as EventRow
    expect(fusedConfidence(e)).toBe(0.5)
  })

  it('is null when the event carries neither — never a fabricated 0', () => {
    // Rendering 0% confidence for "we do not know" would be a lie on the
    // decision card, so null has to survive all the way out.
    const e = { confidence: null, fusion: null } as unknown as EventRow
    expect(fusedConfidence(e)).toBeNull()
  })
})

describe('statusDisplay', () => {
  it('maps each node status to its legend bucket', () => {
    expect(statusDisplay('online').label).toBe('HEALTHY')
    expect(statusDisplay('maintenance').label).toBe('ATTENTION')
    expect(statusDisplay('alert').label).toBe('ALERT')
    expect(statusDisplay('offline').label).toBe('OFFLINE')
  })

  it('falls back to OFFLINE for an unknown status rather than rendering undefined', () => {
    expect(statusDisplay('bogus' as never).label).toBe('OFFLINE')
  })
})

describe('modalityLabel', () => {
  it('names the three fusion modalities', () => {
    expect(modalityLabel('seismic')).toBe('Ground vibration')
    expect(modalityLabel('acoustic')).toBe('Audio')
    expect(modalityLabel('vision')).toBe('Vision')
  })
})

describe('geoPoints / toLatLng', () => {
  it('keys located nodes by id, carrying lng as left and lat as top', () => {
    const nodes = [{ id: 'S7-01', lat: 10.058, lng: 76.628 }] as NodeRow[]
    const pts = geoPoints(nodes)
    expect(pts.get('S7-01')).toEqual({ left: 76.628, top: 10.058 })
  })

  it('drops nodes with no fix rather than inventing coordinates', () => {
    const nodes = [
      { id: 'a', lat: null, lng: 76.6 },
      { id: 'b', lat: 10.0, lng: null },
    ] as NodeRow[]
    expect(geoPoints(nodes).size).toBe(0)
  })

  it('round-trips a point back to a Leaflet [lat, lng] pair', () => {
    expect(toLatLng({ left: 76.628, top: 10.058 })).toEqual([10.058, 76.628])
  })
})

describe('relativeTime', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(NOW)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString()

  it('says "never" for a missing timestamp', () => {
    expect(relativeTime(null)).toBe('never')
  })

  it('says "unknown" for an unparseable timestamp', () => {
    expect(relativeTime('not-a-date')).toBe('unknown')
  })

  it('steps through seconds, minutes, hours and days', () => {
    expect(relativeTime(ago(40 * 1000))).toBe('40 s ago')
    expect(relativeTime(ago(12 * 60_000))).toBe('12 m ago')
    expect(relativeTime(ago(3 * 3_600_000))).toBe('3 h ago')
    expect(relativeTime(ago(2 * 86_400_000))).toBe('2 d ago')
  })

  it('clamps a future timestamp to "just now" rather than showing negative time', () => {
    expect(relativeTime(new Date(NOW.getTime() + 60_000).toISOString())).toBe('just now')
  })
})


const ev = (e: Partial<EventRow>): EventRow => e as EventRow

describe('speciesLabel', () => {
  it('names every class the wire format can carry', () => {
    expect(speciesLabel('elephant')).toBe('Elephant')
    expect(speciesLabel('boar')).toBe('Wild boar')
    expect(speciesLabel('fox')).toBe('Fox')
    expect(speciesLabel('gunshot')).toBe('Gunshot')
    expect(speciesLabel('chainsaw')).toBe('Chainsaw')
  })

  it('says an elephant was heard, not seen, for elephant_call', () => {
    // Every render site used to capitalise the raw column, which turned the
    // acoustic class into "Elephant_call". It is also the distinction an
    // officer deciding whether to drive out actually needs.
    expect(speciesLabel('elephant_call')).toBe('Elephant heard')
    expect(speciesLabel('elephant_call')).not.toBe(speciesLabel('elephant'))
  })

  it('says "Detection" for an event with no species, never an empty label', () => {
    expect(speciesLabel(null)).toBe('Detection')
    expect(speciesLabel(undefined)).toBe('Detection')
    expect(speciesLabel('   ')).toBe('Detection')
  })

  it('makes an unrecognised value legible instead of printing it raw', () => {
    // A class from firmware newer than this build, and the maintenance rows
    // that borrow the species column.
    expect(speciesLabel('wild_dog')).toBe('Wild dog')
    expect(speciesLabel('solar_degraded')).toBe('Solar degraded')
  })

  it('is case- and whitespace-insensitive about the wire value', () => {
    expect(speciesLabel(' Elephant ')).toBe('Elephant')
    expect(speciesLabel('ELEPHANT_CALL')).toBe('Elephant heard')
  })
})

describe('speciesIcon', () => {
  it('gives a confirmed elephant and a heard one different glyphs', () => {
    // The old lookup matched on substring, so 'elephant_call' drew the
    // elephant - a photograph's certainty for a microphone's evidence.
    expect(speciesIcon('elephant_call')).not.toBe(speciesIcon('elephant'))
  })

  it('gives every wire class its own glyph, with no collisions', () => {
    const icons = knownSpecies().map(speciesIcon)
    expect(new Set(icons).size).toBe(icons.length)
  })

  it('still draws the legacy free-text rows it always drew', () => {
    // The demo's rejected cattle detection, matched by substring as before -
    // but only after the exact wire-class lookup has missed.
    expect(speciesIcon('cattle')).toBe(speciesIcon('cattle herd'))
    expect(speciesIcon('cattle')).not.toBe(speciesIcon(null))
  })

  it('falls back to a generic marker rather than rendering nothing', () => {
    expect(speciesIcon(null)).toBeTruthy()
    expect(speciesIcon('wild_dog')).toBeTruthy()
  })
})

describe('speciesShort', () => {
  it('is upper case for the replay headline', () => {
    expect(speciesShort('elephant')).toBe('ELEPHANT')
    expect(speciesShort('elephant_call')).toBe('ELEPHANT HEARD')
    expect(speciesShort('wild_dog')).toBe('WILD DOG')
  })
})

describe('the frontend species table against the decoder', () => {
  // The same discipline test_rpc_contract.py applies to bridge/schema.md and
  // test_species_registry.py applies to message.ts: three hand-written copies
  // of one vocabulary with nothing comparing them is how the last class-scheme
  // defect happened. Read as text because web/ingest is a separate package.
  const payload = readFileSync(new URL('../../../ingest/src/payload.ts', import.meta.url), 'utf8')

  function decodableSpecies(): string[] {
    const start = payload.indexOf('const EVENT_CLASS_SPECIES')
    expect(start).toBeGreaterThan(-1)
    const body = payload.slice(payload.indexOf('{', start) + 1, payload.indexOf('}', start))
    const out: string[] = []
    for (const raw of body.split('\n')) {
      const value = raw.trim().replace(/,$/, '').split(':')[1]?.trim()
      if (value && value !== 'null') out.push(value.replace(/'/g, ''))
    }
    return out
  }

  it('finds the classes web/ingest can decode', () => {
    expect(decodableSpecies().sort()).toEqual([
      'boar',
      'chainsaw',
      'elephant',
      'elephant_call',
      'fox',
      'gunshot',
    ])
  })

  it('has a display entry for every one of them', () => {
    // A class the decoder can produce and this table cannot name reaches the
    // officer as a raw column value in a feed row.
    const missing = decodableSpecies().filter((s) => !knownSpecies().includes(s))
    expect(missing).toEqual([])
  })

  it('claims no species the decoder cannot produce', () => {
    const extra = knownSpecies().filter((s) => !decodableSpecies().includes(s))
    expect(extra).toEqual([])
  })
})

describe('priority', () => {
  it('treats high and critical as urgent, and nothing else', () => {
    expect(isUrgent('high')).toBe(true)
    expect(isUrgent('critical')).toBe(true)
    expect(isUrgent('normal')).toBe(false)
    expect(isUrgent(null)).toBe(false)
    expect(isUrgent('bogus')).toBe(false)
  })

  it('separates critical from high', () => {
    // isUrgent decides whether to shout; isCritical decides what to say. A
    // feed that collapses them loses the measurement the device made.
    expect(isCritical('critical')).toBe(true)
    expect(isCritical('high')).toBe(false)
    expect(isCritical(null)).toBe(false)
  })

  it('gives critical a filled badge and high only coloured text', () => {
    expect(priorityDisplay('critical').fill).not.toBeNull()
    expect(priorityDisplay('high').fill).toBeNull()
    expect(priorityDisplay('critical').label).toBe('NO RETREAT')
  })

  it('falls back to routine for an unknown priority rather than rendering undefined', () => {
    expect(priorityDisplay('bogus').label).toBe(priorityDisplay('normal').label)
    expect(priorityDisplay(null).label).toBe(priorityDisplay('normal').label)
  })
})

describe('noRetreat', () => {
  it('reads the routed priority, which is what every other layer acted on', () => {
    expect(noRetreat(ev({ priority: 'critical', uplink: null }))).toBe(true)
    expect(noRetreat(ev({ priority: 'high', uplink: null }))).toBe(false)
  })

  it('also believes the frame flag when the priority somehow did not follow it', () => {
    // web/ingest derives one from the other, so a disagreement means a routing
    // bug - and the safe reading of "the animal stayed" is to say so.
    expect(noRetreat(ev({ priority: 'high', uplink: { no_retreat: true } }))).toBe(true)
    expect(noRetreat(ev({ priority: 'normal', uplink: { no_retreat: false } }))).toBe(false)
  })
})

describe('headlineSpecies', () => {
  it('picks what the incident is about, not what walked past first', () => {
    const incident = [
      ev({ species: 'fox' }),
      ev({ species: 'elephant' }),
      ev({ species: 'boar' }),
    ]
    expect(headlineSpecies(incident)).toBe('elephant')
  })

  it('puts a poaching sound above any animal in the same cluster', () => {
    // A cluster holding both is about the people, not the herd.
    expect(headlineSpecies([ev({ species: 'elephant' }), ev({ species: 'gunshot' })])).toBe(
      'gunshot',
    )
  })

  it('prefers a camera confirmation to a microphone one', () => {
    expect(headlineSpecies([ev({ species: 'elephant_call' }), ev({ species: 'elephant' })])).toBe(
      'elephant',
    )
  })

  it('is null when nothing in the incident carries a species', () => {
    expect(headlineSpecies([ev({ species: null }), ev({})])).toBeNull()
    expect(headlineSpecies([])).toBeNull()
  })

  it('still returns an unrecognised species rather than nothing at all', () => {
    expect(headlineSpecies([ev({ species: 'wild_dog' })])).toBe('wild_dog')
    expect(headlineSpecies([ev({ species: 'wild_dog' }), ev({ species: 'fox' })])).toBe('fox')
  })
})
