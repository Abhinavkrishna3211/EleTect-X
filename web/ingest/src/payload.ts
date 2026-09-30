// Decoder for the node's raw LoRaWAN uplink bytes (ADR 0031). The byte
// layout is defined by device/mcu/src/uplink.h; the known-answer vectors in
// payload.test.ts are the same ones device/mcu/tests/test_uplink checks, so
// the two sides cannot drift apart silently.
//
// Decoding happens here rather than in a ChirpStack device-profile codec so
// the format lives in version control next to its tests, and a ChirpStack
// reinstall cannot quietly drop it.

export const UPLINK_FPORT = 10;
export const UPLINK_FORMAT_VERSION = 1;

const TYPE_STATUS = 1;
const TYPE_EVENT = 2;
const EVENT_LEN = 10;
const STATUS_LEN = 9;

export const EVENT_FLAG_VISION_CONFIRMED = 0x01;
export const EVENT_FLAG_DETERRENT_FIRED = 0x02;
export const EVENT_FLAG_SAFE_MODE = 0x04;

export const STATUS_FLAG_GEOPHONE_OK = 0x01;
export const STATUS_FLAG_HOME_TEST = 0x02;

const BATTERY_UNKNOWN = 0xffff;

// Wire value -> events.species. 0 is a seismic alert the camera did not
// confirm, so it has no species.
const EVENT_CLASS_SPECIES: Record<number, string | null> = {
  0: null,
  1: 'elephant',
  2: 'boar',
  3: 'gunshot',
  4: 'chainsaw',
};

export interface UplinkEvent {
  kind: 'event';
  seq: number;
  eventClass: number;
  species: string | null;
  confidence: number; // 0..1
  tier: number;
  flags: number;
  visionConfirmed: boolean;
  deterrentFired: boolean;
  safeMode: boolean;
  captureRef: number;
}

export interface UplinkStatus {
  kind: 'status';
  seq: number;
  flags: number;
  geophoneOk: boolean;
  homeTest: boolean;
  batteryMv: number | null;
  uptimeS: number;
}

export type DecodedUplink = UplinkEvent | UplinkStatus;

export class PayloadError extends Error {}

export function decodeUplink(bytes: Uint8Array): DecodedUplink {
  if (bytes.length < 2) throw new PayloadError(`frame too short (${bytes.length} bytes)`);
  const format = bytes[0] >> 4;
  const type = bytes[0] & 0x0f;
  if (format !== UPLINK_FORMAT_VERSION) {
    throw new PayloadError(`unsupported format version ${format}`);
  }
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const seq = bytes[1];

  if (type === TYPE_EVENT) {
    if (bytes.length !== EVENT_LEN) throw new PayloadError(`event frame is ${bytes.length} bytes`);
    const eventClass = bytes[2];
    const flags = bytes[5];
    return {
      kind: 'event',
      seq,
      eventClass,
      // An unknown class from newer firmware is kept as "no species" rather
      // than rejected - the detection still happened.
      species: EVENT_CLASS_SPECIES[eventClass] ?? null,
      confidence: Math.min(bytes[3], 100) / 100,
      tier: bytes[4],
      flags,
      visionConfirmed: (flags & EVENT_FLAG_VISION_CONFIRMED) !== 0,
      deterrentFired: (flags & EVENT_FLAG_DETERRENT_FIRED) !== 0,
      safeMode: (flags & EVENT_FLAG_SAFE_MODE) !== 0,
      captureRef: view.getUint32(6),
    };
  }

  if (type === TYPE_STATUS) {
    if (bytes.length !== STATUS_LEN) throw new PayloadError(`status frame is ${bytes.length} bytes`);
    const flags = bytes[2];
    const batteryMv = view.getUint16(3);
    return {
      kind: 'status',
      seq,
      flags,
      geophoneOk: (flags & STATUS_FLAG_GEOPHONE_OK) !== 0,
      homeTest: (flags & STATUS_FLAG_HOME_TEST) !== 0,
      batteryMv: batteryMv === BATTERY_UNKNOWN ? null : batteryMv,
      uptimeS: view.getUint32(5),
    };
  }

  throw new PayloadError(`unknown frame type ${type}`);
}

// Who gets paged, decided from what the node actually saw:
//  - a species the camera confirmed, or a gunshot/chainsaw, is 'high'
//    (send-alert fans it out);
//  - a seismic-only alert is 'normal' - it shows on the dashboard, but it
//    does not wake a village.
export function eventPriority(ev: UplinkEvent): 'high' | 'normal' {
  if (ev.species === 'gunshot' || ev.species === 'chainsaw') return 'high';
  return ev.visionConfirmed ? 'high' : 'normal';
}

// Short dashboard label for events.action.
export function eventAction(ev: UplinkEvent): string | null {
  if (ev.tier === 0) return null;
  const parts = [`Tier ${ev.tier}`];
  if (ev.safeMode) parts.push('dry run');
  else if (!ev.deterrentFired) parts.push('not fired');
  return parts.join(', ');
}
