import { supabase } from './supabase.js';

// Shape of a ChirpStack v4 MQTT uplink event (application/{id}/device/{devEui}/event/up).
// `object` is only present when the device profile has a payload codec configured;
// it holds the already-decoded fields. We only read the handful of keys this
// project's node firmware is expected to send - everything else is ignored.
interface ChirpstackUplink {
  deviceInfo?: { devEui?: string; deviceName?: string };
  object?: Record<string, unknown>;
  rxInfo?: Array<{ rssi?: number; snr?: number }>;
}

function num(v: unknown): number | null {
  return typeof v === 'number' ? v : null;
}

export async function handleUplink(payload: unknown): Promise<void> {
  const msg = payload as ChirpstackUplink;
  const devEui = msg.deviceInfo?.devEui;
  if (!devEui) {
    console.warn('Uplink with no deviceInfo.devEui, skipping:', payload);
    return;
  }

  const object = msg.object ?? {};
  const rx = msg.rxInfo?.[0];
  const batteryPct = num(object.battery_pct);
  const solarW = num(object.solar_w);
  const tempC = num(object.temp_c);

  // schema.sql's events/health tables have a foreign key to nodes.id. A real
  // deployment pre-seeds nodes at install time (CONTEXT.md §6), but this
  // upsert means a node that hasn't been seeded yet - a fresh test device,
  // most likely - never blocks on a missing row instead of silently dropping data.
  const { error: nodeErr } = await supabase.from('nodes').upsert(
    {
      id: devEui,
      name: msg.deviceInfo?.deviceName ?? devEui,
      status: 'online',
      last_seen: new Date().toISOString(),
      ...(batteryPct !== null ? { battery_pct: batteryPct } : {}),
      ...(solarW !== null ? { solar_w: solarW } : {}),
    },
    { onConflict: 'id' },
  );
  if (nodeErr) throw nodeErr;

  // Health telemetry - only written if the payload actually carries any.
  if (batteryPct !== null || solarW !== null || tempC !== null) {
    const { error: healthErr } = await supabase.from('health').insert({
      node_id: devEui,
      battery_pct: batteryPct,
      solar_w: solarW,
      temp_c: tempC,
      metrics: { rssi: rx?.rssi ?? null, snr: rx?.snr ?? null },
    });
    if (healthErr) throw healthErr;
  }

  // Detection event - only written if the payload carries a species classification.
  if (typeof object.species === 'string') {
    const { error: eventErr } = await supabase.from('events').insert({
      node_id: devEui,
      species: object.species,
      confidence: num(object.confidence),
      direction_deg: num(object.direction_deg),
      action: typeof object.action === 'string' ? object.action : null,
      priority: typeof object.priority === 'string' ? object.priority : 'normal',
    });
    if (eventErr) throw eventErr;
    console.log(`Logged ${object.species} event from ${devEui} (confidence=${object.confidence ?? 'n/a'})`);
    return;
  }

  console.log(`Logged telemetry from ${devEui}, no detection payload`);
}
