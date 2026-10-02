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
// The node fired its top tier and the animal was still there at the end of
// the retreat tail (ADR 0034). Distinct from every other alert, which says
// the node is handling it; this one says it has run out of options.
export const EVENT_FLAG_NO_RETREAT = 0x08;

export const STATUS_FLAG_GEOPHONE_OK = 0x01;
export const STATUS_FLAG_HOME_TEST = 0x02;

const BATTERY_UNKNOWN = 0xffff;

// Wire value -> events.species. 0 is a seismic alert the camera did not
// confirm, so it has no species. Append only, never renumber - these are
// the codes in device/mcu/src/uplink.h and device/mpu/comms/lora_uplink.py,
// and all three lists are checked against each other by the known-answer
// vectors in payload.test.ts and device/mcu/tests/test_uplink.
//
// 'elephant_call' is an elephant heard and not seen. It stays separate from
// 'elephant' all the way to the officer's screen: the two have different
// false-positive profiles, and collapsing them here would make a microphone
// detection indistinguishable from a camera confirmation.
const EVENT_CLASS_SPECIES: Record<number, string | null> = {
  0: null,
  1: 'elephant',
  2: 'boar',
  3: 'gunshot',
  4: 'chainsaw',
  5: 'elephant_call',
  6: 'fox',
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
  noRetreat: boolean;
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
      noRetreat: (flags & EVENT_FLAG_NO_RETREAT) !== 0,
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

// Species whose detections are worth paging somebody about.
//
// Boar and fox are deliberately absent: they are real detections and they
// belong on the dashboard, but a node that pages an officer every time a
// boar walks past is a node whose alerts get muted - and then the elephant
// alert is muted too.
//
// 'elephant_call' is absent for a different reason. It means heard and not
// seen, and the node only ever sends it when the camera did not confirm
// the encounter; the confirmed case is re-sent as 'elephant'. So there is
// nothing to page on yet, and paging on a microphone alone is what the
// vision gate exists to prevent.
//
// Who then receives a 'high' event - officers only, or officers and nearby
// residents - is send-alert's decision, not this one.
const PAGING_SPECIES = new Set(['elephant', 'gunshot', 'chainsaw']);

// Who gets paged, decided from what the node actually saw:
//  - 'critical' is the no-retreat flag: the node fired its top tier and
//    the animal stayed. Nothing else the node can do will move it, so this
//    is the one priority that means "send a person";
//  - a paging species the camera confirmed, or a gunshot/chainsaw, is
//    'high' (send-alert fans it out);
//  - everything else is 'normal' - it shows on the dashboard, but it does
//    not wake a village. That includes boar and fox however confident the
//    camera was, and it includes a seismic-only alert of any species.
//
// The default is 'normal' on purpose. An unknown class from newer firmware
// decodes to species null and lands here, and the safe direction for a
// species this build cannot name is the dashboard, not every phone within
// 3 km.
// send-alert (isPaging in message.ts) and the public_area_risk view both
// treat 'critical' as paging, so a no-retreat event reaches the same people
// a 'high' one does, worded as a request for a team (migration 0005).
export function eventPriority(
  ev: Pick<UplinkEvent, 'species' | 'visionConfirmed' | 'noRetreat'>,
): 'critical' | 'high' | 'normal' {
  const species = ev.species;
  // A species this build knows and deliberately does not page on - boar, fox,
  // an elephant heard and not seen - stays off every phone, and that has to
  // include the no-retreat flag.
  //
  // _no_retreat_flagged() on the device is species-blind by design: top tier,
  // something fired, the animal was still there. Fox and boar are ordinary
  // deterrence targets, and a fox is the animal most likely to sit through a
  // burst - habituating fast is the premise the whole bandit is built on. So
  // reading the flag before the species, as this did, routed a fox that held
  // its ground to 'critical' and asked an officer to drive into the forest at
  // night for it. That is the exact alert the boar and fox exclusion exists to
  // prevent, arriving through the one door that skipped the check.
  //
  // The flag stays on the frame either way. That a fox did not retreat is a
  // real finding about the deterrent; it belongs on the dashboard and in the
  // bandit's record. It is not a reason to wake anyone up.
  if (species !== null && !PAGING_SPECIES.has(species)) return 'normal';
  // An unnamed event keeps the escalation. Something was tracked through a
  // top-tier fire and did not leave, and the camera could not say what it was;
  // not knowing is a reason to send a person, not a reason not to.
  if (ev.noRetreat) return 'critical';
  if (species === null) return 'normal';
  if (species === 'gunshot' || species === 'chainsaw') return 'high';
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
