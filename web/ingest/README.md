# web/ingest

Bridges ChirpStack's MQTT uplink stream into Supabase. Subscribes to
`application/{id}/device/{devEui}/event/up`, decodes the node's raw frame
(FPort 10, ADR 0031) in `src/payload.ts`, and writes rows into `nodes`,
`events`, and `health` per `web/backend/schema.sql`. No ChirpStack payload
codec is needed - leave the device profile's codec empty.

## Local setup

1. Stand up ChirpStack locally (see the sibling `chirpstack-stack` repo's
   `docker-compose.yml`, configured for region IN865).
2. Copy `.env.example` to `.env` and fill in:
   - `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` - from the Supabase project
     settings. The service-role key bypasses RLS; keep it out of git and out
     of the frontend.
   - `CHIRPSTACK_APPLICATION_ID` - the application ID from the ChirpStack UI
     (Tenant → Applications). Optional, but recommended once you have more
     than one test application on the same broker.
3. Install dependencies and run:
   ```
   npm install
   npm run dev
   ```

## What it does

- On every uplink, registers the node if it hasn't been seeded yet (keyed on
  Device EUI) and moves `last_seen`. A seeded node keeps its name; an
  `offline` node goes back to `online`.
- **Event frame** -> an `events` row: species from the class byte (none for a
  seismic-only alert or a multi-species node), confidence, a short `action`
  label, and the decoded frame plus RSSI/SNR/fCnt in `events.uplink`.
  Priority is `high` for camera-confirmed wildlife and for gunshot/chainsaw,
  `normal` for a seismic-only alert - only `high` fans out through
  `send-alert`.
- **Status frame** -> a `health` row with battery mV, uptime, geophone and
  home-test flags in `metrics`.
- A frame the node re-sent (same `seq` from the same node within 15 minutes)
  is dropped, so one event is one row.
- A pre-decoded `object` (test devices, the command below) is still accepted:
  `battery_pct` / `solar_w` / `temp_c` make a `health` row and a `species`
  field makes an `events` row.

Run the decoder tests with `npm test`.

## Testing without hardware

Publish a synthetic uplink straight to the broker's MQTT topic and confirm a
row lands in Supabase:

```
mosquitto_pub -h localhost -t "application/<APPLICATION_ID>/device/<DEV_EUI>/event/up" -m "{\"deviceInfo\":{\"devEui\":\"<DEV_EUI>\",\"deviceName\":\"node-test-01\"},\"object\":{\"species\":\"elephant\",\"confidence\":0.85,\"direction_deg\":45,\"battery_pct\":78,\"solar_w\":2.9,\"temp_c\":27.5}}"
```

To exercise the real decoder instead, send the raw frame in `data` (base64) on
FPort 10. This is the known-answer event from `src/payload.test.ts` - a
camera-confirmed elephant at 87%, tier 2 fired:

```
mosquitto_pub -h localhost -t "application/<APPLICATION_ID>/device/<DEV_EUI>/event/up" -m "{\"deviceInfo\":{\"devEui\":\"<DEV_EUI>\"},\"fPort\":10,\"fCnt\":1,\"data\":\"EgUBVwIDAQIDBA==\"}"
```

It is `high` priority, so against a project with `send-alert` wired it pages
real people - use a local project.

Replace `<APPLICATION_ID>` and `<DEV_EUI>` with the values from the ChirpStack
UI. This does not require a real join or radio uplink - it proves the bridge's
MQTT-to-Supabase path independent of firmware.

**Clean up after yourself when testing against the production project.** The
bridge upserts a `nodes` row for every device it hears from, by design - that is
how a real node registers itself on first uplink. A synthetic uplink therefore
creates a real node row, and it then shows up on the Fleet and Overview screens
with a raw DevEUI instead of an `S7-XX` id, no firmware version, and stale
telemetry. `node-test-01` (`4f3030e129cfeb14`) lived on the production dashboard
for exactly this reason until it was removed on 12 Jul. `events` and `health`
cascade off `nodes`, so one delete is enough:

```sql
delete from nodes where id = '<DEV_EUI>';
```

Prefer a local Supabase project for this test; if you must use production, delete
the node afterwards.
