import { supabase } from './supabase.js';
import {
  decodeUplink,
  eventAction,
  eventPriority,
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
}

interface Radio {
  fcnt: number | null;
  rssi: number | null;
  snr: number | null;
}

// A frame the node re-sends after its AT exchange was cut short carries the
// same seq (ADR 0031). seq wraps at 256, so a match only counts inside this
// window - far longer than the node's retry span, far shorter than 256
// uplinks at the heartbeat rate.
const DUPLICATE_WINDOW_MS = 15 * 60 * 1000;

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

async function isDuplicate(table: 'events' | 'health', column: string, devEui: string, seq: number) {
  const since = new Date(Date.now() - DUPLICATE_WINDOW_MS).toISOString();
  const { data, error } = await supabase
    .from(table)
    .select('id')
    .eq('node_id', devEui)
    .eq(`${column}->>seq`, String(seq))
    .gte('ts', since)
    .limit(1);
  if (error) throw error;
  return (data ?? []).length > 0;
}

async function writeEvent(devEui: string, ev: UplinkEvent, radio: Radio) {
  if (await isDuplicate('events', 'uplink', devEui, ev.seq)) {
    console.log(`Dropped duplicate event seq=${ev.seq} from ${devEui}`);
    return;
  }
  const priority = eventPriority(ev);
  const { error } = await supabase.from('events').insert({
    node_id: devEui,
    species: ev.species,
    confidence: ev.confidence,
    action: eventAction(ev),
    priority,
    uplink: {
      seq: ev.seq,
      class: ev.eventClass,
      tier: ev.tier,
      flags: ev.flags,
      vision_confirmed: ev.visionConfirmed,
      deterrent_fired: ev.deterrentFired,
      safe_mode: ev.safeMode,
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

async function writeStatus(devEui: string, st: UplinkStatus, radio: Radio) {
  if (await isDuplicate('health', 'metrics', devEui, st.seq)) {
    console.log(`Dropped duplicate status seq=${st.seq} from ${devEui}`);
    return;
  }
  const { error } = await supabase.from('health').insert({
    node_id: devEui,
    battery_pct: null, // the node reports mV; no pack curve is agreed yet
    metrics: {
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
  let decoded;
  try {
    decoded = decodeUplink(Uint8Array.from(Buffer.from(msg.data ?? '', 'base64')));
  } catch (err) {
    if (err instanceof PayloadError) {
      console.warn(`Undecodable frame from ${devEui} (fCnt=${msg.fCnt ?? '?'}): ${err.message}`);
      return;
    }
    throw err;
  }
  const radio = bestRadio(msg);
  if (decoded.kind === 'event') await writeEvent(devEui, decoded, radio);
  else await writeStatus(devEui, decoded, radio);
}

// Pre-decoded JSON in `object` - test devices and test-uplink.json.
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
      priority: typeof object.priority === 'string' ? object.priority : 'normal',
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
