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
    captureRef: 0x01020304,
  });
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
  assert.equal(eventPriority(ev(0, 0x01)), 'high', 'confirmed on a multi-species node');
  assert.equal(eventPriority(ev(0, 0x00)), 'normal', 'seismic only');
  assert.equal(eventPriority(ev(3, 0x00)), 'high', 'gunshot');
});

test('action label', () => {
  const ev = (tier: number, flags: number) =>
    decodeUplink(Uint8Array.from([0x12, 0, 1, 80, tier, flags, 0, 0, 0, 0])) as UplinkEvent;
  assert.equal(eventAction(ev(0, 0)), null);
  assert.equal(eventAction(ev(2, 0x02)), 'Tier 2');
  assert.equal(eventAction(ev(2, 0x04)), 'Tier 2, dry run');
  assert.equal(eventAction(ev(3, 0x00)), 'Tier 3, not fired');
});
