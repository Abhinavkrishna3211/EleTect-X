# web/ingest

Bridges ChirpStack's MQTT uplink stream into Supabase. Subscribes to
`application/{id}/device/{devEui}/event/up`, reads the decoded `object`
payload, and writes rows into `nodes`, `events`, and `health` per
`web/backend/schema.sql`.

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

- On every uplink, upserts a `nodes` row for the sending device (auto-registers
  a node that hasn't been seeded yet, keyed on Device EUI).
- If the decoded payload carries `battery_pct`, `solar_w`, or `temp_c`, inserts
  a `health` row.
- If the decoded payload carries a `species` field, inserts an `events` row
  (`confidence`, `direction_deg`, `action`, `priority` read if present).

## Testing without hardware

Publish a synthetic uplink straight to the broker's MQTT topic and confirm a
row lands in Supabase:

```
mosquitto_pub -h localhost -t "application/<APPLICATION_ID>/device/<DEV_EUI>/event/up" -m "{\"deviceInfo\":{\"devEui\":\"<DEV_EUI>\",\"deviceName\":\"node-test-01\"},\"object\":{\"species\":\"elephant\",\"confidence\":0.85,\"direction_deg\":45,\"battery_pct\":78,\"solar_w\":2.9,\"temp_c\":27.5}}"
```

Replace `<APPLICATION_ID>` and `<DEV_EUI>` with the values from the ChirpStack
UI. This does not require a real join or radio uplink - it proves the bridge's
MQTT-to-Supabase path independent of firmware.
