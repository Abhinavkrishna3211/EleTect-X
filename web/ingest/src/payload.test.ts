import assert from 'node:assert/strict';
import { test } from 'node:test';

import { decodeUplink, eventAction, eventPriority, PayloadError, type UplinkEvent } from './payload.js';

const hex = (s: string) => Uint8Array.from(Buffer.from(s.replace(/\s+/g, ''), 'hex'));

// Same vectors as device/mcu/tests/test_uplink/test_uplink.cpp.
test('event known answer', () => {
  const ev = decodeUplink(hex('12 05 01 57 02 03 01 02 03 04'));
  assert.deepEqual(ev, {
    kind: 'event',
    seq: 5,
    eventClass: 1,
    species: 'elephant',
    confidence: 0.87,
    tier: 2,
    flags: 0x03,
    visionConfirmed: true,
    deterrentFired: true,
    safeMode: false,
    noRetreat: false,
    captureRef: 0x01020304,
  });
});

// Same vector as test_uplink.cpp's test_no_retreat_event_known_answer.
test('no-retreat event known answer', () => {
  const ev = decodeUplink(hex('12 07 06 32 03 0B 00 00 00 00'));
  assert.deepEqual(ev, {
    kind: 'event',
    seq: 7,
    eventClass: 6,
    species: 'fox',
    confidence: 0.5,
    tier: 3,
    flags: 0x0b,
    visionConfirmed: true,
    deterrentFired: true,
    safeMode: false,
    noRetreat: true,
    captureRef: 0,
  });
});

test('the appended classes decode to their own species', () => {
  const species = (cls: number) =>
    (decodeUplink(Uint8Array.from([0x12, 0, cls, 80, 0, 0, 0, 0, 0, 0])) as UplinkEvent).species;
  // elephant_call must not collapse into elephant: heard and seen are
  // different evidence, and an officer has to be able to tell them apart.
  assert.equal(species(5), 'elephant_call');
  assert.equal(species(6), 'fox');
});

test('status known answer', () => {
  const st = decodeUplink(hex('11 C8 03 0E 80 00 01 51 80'));
  assert.deepEqual(st, {
    kind: 'status',
    seq: 200,
    flags: 0x03,
    geophoneOk: true,
    homeTest: true,
    batteryMv: 3712,
    uptimeS: 86400,
  });
});

test('unknown battery decodes to null', () => {
  const st = decodeUplink(hex('11 00 01 FF FF 00 00 00 00'));
  assert.equal(st.kind, 'status');
  assert.equal(st.kind === 'status' && st.batteryMv, null);
});

test('unconfirmed and unknown classes have no species', () => {
  const unconfirmed = decodeUplink(hex('12 00 00 40 00 00 00 00 00 00')) as UplinkEvent;
  assert.equal(unconfirmed.species, null);
  const future = decodeUplink(hex('12 00 09 40 00 00 00 00 00 00')) as UplinkEvent;
  assert.equal(future.species, null);
});

test('malformed frames are rejected', () => {
  assert.throws(() => decodeUplink(hex('12')), PayloadError);
  assert.throws(() => decodeUplink(hex('22 00 01 57 02 03 01 02 03 04')), PayloadError, 'format 2');
  assert.throws(() => decodeUplink(hex('12 05 01 57 02 03 01 02 03')), PayloadError, 'short event');
  assert.throws(() => decodeUplink(hex('13 05 01')), PayloadError, 'unknown type');
});

test('priority: only camera-confirmed wildlife and poaching sounds page people', () => {
  const ev = (cls: number, flags: number) =>
    decodeUplink(Uint8Array.from([0x12, 0, cls, 80, 1, flags, 0, 0, 0, 0])) as UplinkEvent;
  assert.equal(eventPriority(ev(1, 0x01)), 'high');
  assert.equal(eventPriority(ev(0, 0x00)), 'normal', 'seismic only');
  assert.equal(eventPriority(ev(3, 0x00)), 'high', 'gunshot');
  assert.equal(eventPriority(ev(4, 0x00)), 'high', 'chainsaw');

  // Since ADR 0034 the node names the species it saw, so a confirmation
  // that arrives with no species is either firmware older than that or a
  // class this build cannot name. Either way it must not page a village -
  // the old behaviour paged one on a guess drawn from the node's own
  // configuration.
  assert.equal(eventPriority(ev(0, 0x01)), 'normal', 'confirmed but unnamed');
  assert.equal(eventPriority(ev(9, 0x01)), 'normal', 'confirmed, class from newer firmware');

  // Boar and fox are shown, never pushed - however sure the camera was.
  assert.equal(eventPriority(ev(2, 0x01)), 'normal', 'boar');
  assert.equal(eventPriority(ev(6, 0x01)), 'normal', 'fox');

  // Heard and not seen is exactly what the vision gate declines to page on.
  assert.equal(eventPriority(ev(5, 0x00)), 'normal', 'elephant call');
});

test('priority: no retreat outranks everything the node pages on', () => {
  const ev = (cls: number, flags: number) =>
    decodeUplink(Uint8Array.from([0x12, 0, cls, 80, 3, flags, 0, 0, 0, 0])) as UplinkEvent;
  assert.equal(eventPriority(ev(1, 0x0b)), 'critical', 'elephant stayed after the top tier');
  // The flag says the node has run out of options, and when it cannot say
  // what stayed, not knowing is a reason to send someone rather than not to.
  assert.equal(eventPriority(ev(0, 0x08)), 'critical', 'unnamed, stayed');

  // But it does not promote a species that is never pushed. _no_retreat_flagged()
  // on the device is species-blind, and a fox sitting through a tier-3 burst is
  // the likeliest way the flag is ever set - habituating fast is what fox
  // deterrence is up against. Routing that as 'critical' sends an officer into
  // the forest at night for a fox, which is how the elephant alert stops being
  // believed.
  assert.equal(eventPriority(ev(6, 0x0b)), 'normal', 'fox stayed');
  assert.equal(eventPriority(ev(2, 0x0b)), 'normal', 'boar stayed');
  assert.equal(eventPriority(ev(5, 0x08)), 'normal', 'heard and not seen');
});

test('action label', () => {
  const ev = (tier: number, flags: number) =>
    decodeUplink(Uint8Array.from([0x12, 0, 1, 80, tier, flags, 0, 0, 0, 0])) as UplinkEvent;
  assert.equal(eventAction(ev(0, 0)), null);
  assert.equal(eventAction(ev(2, 0x02)), 'Tier 2');
  assert.equal(eventAction(ev(2, 0x04)), 'Tier 2, dry run');
  assert.equal(eventAction(ev(3, 0x00)), 'Tier 3, not fired');
});
