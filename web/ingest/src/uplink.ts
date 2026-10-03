import { createHash } from 'node:crypto';
import { supabase } from './supabase.js';
import {
  decodeUplink,
  eventAction,
  eventPriority,
  frameIdentityBytes,
  PayloadError,
  UPLINK_FPORT,
  type UplinkEvent,
  type UplinkStatus,
} from './payload.js';

// Shape of a ChirpStack v4 MQTT uplink event (application/{id}/device/{devEui}/event/up).
// Node frames arrive as raw bytes in `data` (base64) on UPLINK_FPORT and are
// decoded by payload.ts (ADR 0031). `object` is only present when a device
// profile has its own payload codec; it is still read, for test devices that
// send pre-decoded JSON.
interface ChirpstackUplink {
  deviceInfo?: { devEui?: string; deviceName?: string };
  fPort?: number;
  fCnt?: number;
  data?: string;
  object?: Record<string, unknown>;
  rxInfo?: Array<{ rssi?: number; snr?: number }>;
  // RFC3339, stamped by ChirpStack when it received the frame. Read in
  // preference to this process's own clock: with a persistent session the
  // broker holds uplinks while the bridge is down, so on reconnect a backlog
  // arrives all at once and Date.now() would file an hour of history as
  // having happened in the same second.
  time?: string;
}

interface Radio {
  fcnt: number | null;
  rssi: number | null;
  snr: number | null;
}

// A frame the node re-sends after its AT exchange was cut short carries the
// same bytes and the same seq (ADR 0031 B), so a retransmission is identified
// by hashing the frame rather than by its seq alone.
//
// Keying on seq was wrong in two ways that both silently discarded real
// alerts. lora_init() resets g_seq to 0 on every boot, and this board's
// brown-out reboots are a documented field failure - so the first events after
// a reboot reused seq values already seen and were dropped as duplicates. And
// g_seq is a uint8_t that wraps at 256 independently of any reboot. Dropping a
// genuine elephant alert is the most expensive thing this bridge can do, so
// the key is now the frame content, which collides only when the node really
// did send the same frame twice.
//
// The window is anchored on created_at, the row's insertion time, not on ts:
// ts is now backdated by age_s and by ChirpStack's receive time, and a
// backdated row would fall outside a window measured from the wall clock.
// 15 minutes is far longer than the node's own resend span -
// LORA_UPLINK_MAX_ATTEMPTS 3 at LORA_UPLINK_RETRY_BASE_MS 15 s is under a
// minute - and short enough that two unrelated events cannot collide.
const DUPLICATE_WINDOW_MS = 15 * 60 * 1000;

// 64 bits of SHA-256. The population inside one window is a handful of frames
// from one node, so this is nowhere near a collision; the full digest would
// just be 48 more bytes in every jsonb row.
function frameDigest(bytes: Uint8Array): string {
  return createHash('sha256').update(frameIdentityBytes(bytes)).digest('hex').slice(0, 16);
}

// When the node says the event actually happened: ChirpStack's receive time,
// less the transport delay the node reported.
//
// Both terms matter and they cover different gaps. age_s covers the node side
// - a frame that waited out a horn fire, two send retries or a join backoff.
// ChirpStack's `time` covers the server side - a broker backlog handed over
// after this bridge reconnects. Without either, every delayed frame was filed
// at the moment it happened to be written, so a stale alert looked new and the
// dashboard's ordering was transport latency rather than history.
function eventTimestamp(msg: ChirpstackUplink, ageS: number | null): string {
  const received = msg.time ? Date.parse(msg.time) : Number.NaN;
  const base = Number.isFinite(received) ? received : Date.now();
  return new Date(base - (ageS ?? 0) * 1000).toISOString();
}

function num(v: unknown): number | null {
  return typeof v === 'number' ? v : null;
}

function bestRadio(msg: ChirpstackUplink): Radio {
  // Several gateways can hear one frame; the strongest is the useful one.
  const rx = [...(msg.rxInfo ?? [])].sort((a, b) => (b.rssi ?? -999) - (a.rssi ?? -999))[0];
  return { fcnt: msg.fCnt ?? null, rssi: rx?.rssi ?? null, snr: rx?.snr ?? null };
}

// schema.sql's events/health tables have a foreign key to nodes.id. A real
// deployment pre-seeds nodes at install time (CONTEXT.md §6); this only
// creates the row for a node that has not been seeded yet, so a fresh test
// device never loses data to a missing key. An existing row keeps the name
// and status staff gave it - only last_seen moves, and an 'offline' node
// comes back 'online'. 'alert' and 'maintenance' are left for staff to clear.
async function touchNode(devEui: string, deviceName: string | undefined, extra: Record<string, unknown>) {
  const now = new Date().toISOString();
  const { error: insertErr } = await supabase
    .from('nodes')
    .upsert({ id: devEui, name: deviceName ?? devEui, status: 'online', last_seen: now }, {
      onConflict: 'id',
      ignoreDuplicates: true,
    });
  if (insertErr) throw insertErr;

  const { error: seenErr } = await supabase
    .from('nodes')
    .update({ last_seen: now, ...extra })
    .eq('id', devEui);
  if (seenErr) throw seenErr;

  const { error: statusErr } = await supabase
    .from('nodes')
    .update({ status: 'online' })
    .eq('id', devEui)
    .eq('status', 'offline');
  if (statusErr) throw statusErr;
}

// Rows written before the frame digest existed carry no `frame` key and so
// never match. A retransmission that straddles the deploy is written twice,
// once; after one duplicate window has passed there is nothing left to miss.
async function isDuplicate(table: 'events' | 'health', column: string, devEui: string, frame: string) {
  const since = new Date(Date.now() - DUPLICATE_WINDOW_MS).toISOString();
  const { data, error } = await supabase
    .from(table)
    .select('id')
    .eq('node_id', devEui)
    .eq(`${column}->>frame`, frame)
    .gte('created_at', since)
    .limit(1);
  if (error) throw error;
  return (data ?? []).length > 0;
}

async function writeEvent(devEui: string, ev: UplinkEvent, radio: Radio, frame: string, ts: string) {
  if (await isDuplicate('events', 'uplink', devEui, frame)) {
    console.log(`Dropped duplicate event frame=${frame} seq=${ev.seq} from ${devEui}`);
    return;
  }
  const priority = eventPriority(ev);
  const { error } = await supabase.from('events').insert({
    node_id: devEui,
    ts,
    species: ev.species,
    confidence: ev.confidence,
    action: eventAction(ev),
    priority,
    uplink: {
      frame,
      seq: ev.seq,
      age_s: ev.ageS,
      class: ev.eventClass,
      tier: ev.tier,
      flags: ev.flags,
      vision_confirmed: ev.visionConfirmed,
      deterrent_fired: ev.deterrentFired,
      safe_mode: ev.safeMode,
      no_retreat: ev.noRetreat,
      capture_ref: ev.captureRef,
      ...radio,
    },
  });
  if (error) throw error;
  console.log(
    `Logged ${ev.species ?? 'unconfirmed'} event from ${devEui} ` +
      `(confidence=${ev.confidence}, tier=${ev.tier}, priority=${priority})`,
  );
}

async function writeStatus(devEui: string, st: UplinkStatus, radio: Radio, frame: string, ts: string) {
  if (await isDuplicate('health', 'metrics', devEui, frame)) {
    console.log(`Dropped duplicate status frame=${frame} seq=${st.seq} from ${devEui}`);
    return;
  }
  const { error } = await supabase.from('health').insert({
    node_id: devEui,
    ts,
    battery_pct: null, // the node reports mV; no pack curve is agreed yet
    metrics: {
      frame,
      seq: st.seq,
      battery_mv: st.batteryMv,
      uptime_s: st.uptimeS,
      geophone_ok: st.geophoneOk,
      home_test: st.homeTest,
      ...radio,
    },
  });
  if (error) throw error;
  console.log(`Logged status from ${devEui} (uptime=${st.uptimeS}s, geophone_ok=${st.geophoneOk})`);
}

async function handleRawFrame(devEui: string, msg: ChirpstackUplink) {
  const bytes = Uint8Array.from(Buffer.from(msg.data ?? '', 'base64'));
  let decoded;
  try {
    decoded = decodeUplink(bytes);
  } catch (err) {
    if (err instanceof PayloadError) {
      console.warn(`Undecodable frame from ${devEui} (fCnt=${msg.fCnt ?? '?'}): ${err.message}`);
      return;
    }
    throw err;
  }
  const radio = bestRadio(msg);
  const frame = frameDigest(bytes);
  // A status frame has no age field; its timestamp is the receive time.
  const ts = eventTimestamp(msg, decoded.kind === 'event' ? decoded.ageS : null);
  if (decoded.kind === 'event') await writeEvent(devEui, decoded, radio, frame, ts);
  else await writeStatus(devEui, decoded, radio, frame, ts);
}

// Pre-decoded JSON in `object` - test devices and test-uplink.json.
//
// The priority is derived here and never read off the uplink, for the same
// reason the binary path derives it: which phones ring is this bridge's
// decision, and `object` is whatever was published to the broker. Copying
// `object.priority` straight into the row, as this did, was a door around the
// entire routing table - `{"species":"elephant","priority":"critical"}` on the
// MQTT topic inserted an event that the send-alert webhook fans out to every
// officer and every opted-in resident within 3 km of the node, with a message
// asking them to send a team. Nothing on the binary path can produce that
// without the device having actually fired its top tier and watched the animal
// stay.
async function handleObject(
  devEui: string,
  deviceName: string | undefined,
  object: Record<string, unknown>,
  radio: Radio,
) {
  const batteryPct = num(object.battery_pct);
  const solarW = num(object.solar_w);
  const tempC = num(object.temp_c);

  await touchNode(devEui, deviceName, {
    ...(batteryPct !== null ? { battery_pct: batteryPct } : {}),
    ...(solarW !== null ? { solar_w: solarW } : {}),
  });

  if (batteryPct !== null || solarW !== null || tempC !== null) {
    const { error } = await supabase.from('health').insert({
      node_id: devEui,
      battery_pct: batteryPct,
      solar_w: solarW,
      temp_c: tempC,
      metrics: { rssi: radio.rssi, snr: radio.snr },
    });
    if (error) throw error;
  }

  if (typeof object.species === 'string') {
    const { error } = await supabase.from('events').insert({
      node_id: devEui,
      species: object.species,
      confidence: num(object.confidence),
      direction_deg: num(object.direction_deg),
      action: typeof object.action === 'string' ? object.action : null,
      priority: eventPriority({
        species: object.species,
        visionConfirmed: object.vision_confirmed === true,
        noRetreat: object.no_retreat === true,
      }),
    });
    if (error) throw error;
    console.log(`Logged ${object.species} event from ${devEui} (confidence=${object.confidence ?? 'n/a'})`);
    return;
  }
  console.log(`Logged telemetry from ${devEui}, no detection payload`);
}

export async function handleUplink(payload: unknown): Promise<void> {
  const msg = payload as ChirpstackUplink;
  const devEui = msg.deviceInfo?.devEui;
  if (!devEui) {
    console.warn('Uplink with no deviceInfo.devEui, skipping:', payload);
    return;
  }

  if (msg.object) {
    await handleObject(devEui, msg.deviceInfo?.deviceName, msg.object, bestRadio(msg));
    return;
  }

  // Every uplink proves the node is alive, whatever it carries.
  await touchNode(devEui, msg.deviceInfo?.deviceName, {});

  if (msg.fPort === UPLINK_FPORT && msg.data) {
    await handleRawFrame(devEui, msg);
    return;
  }
  console.log(`Uplink from ${devEui} on fPort ${msg.fPort ?? 'none'} with no node frame, last_seen only`);
}
