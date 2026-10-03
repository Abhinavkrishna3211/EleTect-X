# LoRaWAN network server

Everything between a node's radio and the `events` table in Supabase:

```
node --LoRa--> gateway --UDP--> gateway-bridge --> mosquitto --> chirpstack
                                                        |
                                                        +--> eletect-ingest --> Supabase
```

ChirpStack 4 decrypts and de-duplicates LoRaWAN frames and publishes them as
JSON on MQTT. `eletect-ingest` (built from [`../ingest`](../ingest)) subscribes,
decodes the payload bytes per [ADR 0031](../../docs/decisions/0031-lora-uplink-payload.md),
and writes rows to Supabase.

This directory is a trimmed and hardened copy of
[chirpstack-docker](https://github.com/chirpstack/chirpstack-docker) (MIT —
see `LICENSE.chirpstack-docker`). The differences from upstream are listed at
the top of `docker-compose.yml`; the short version is that credentials come
from `.env`, the MQTT broker is not exposed to the LAN, and the broker is
configured to hold uplinks while the bridge is down.

## Setup

You need Docker with Compose v2. Nothing else — the images carry the rest.

**1. Configure this stack.**

```sh
cd web/chirpstack
cp .env.example .env
```

Fill in `CHIRPSTACK_API_SECRET` and `POSTGRES_PASSWORD`; `.env.example` says
how to generate each. Leave `CHIRPSTACK_APPLICATION_ID` empty for now.

**2. Configure the Supabase bridge.** The ingest service reads its Supabase
credentials from `../ingest/.env`, not from this one. Follow
[`../ingest/README.md`](../ingest/README.md) and make sure that file exists —
Compose will not start the stack without it.

**3. Start it.**

```sh
docker compose up -d
```

First start pulls images and initialises the database, so give it a minute.
`docker compose ps` should show every service `running`.

**4. Set up the network server.** Open <http://localhost:8080> and sign in with
`admin` / `admin`. **Change that password immediately** — it is the upstream
default and this account can read every uplink. Then:

- **Device profiles** → add one for your region (`in865` here), LoRaWAN 1.0.3,
  Class A, and turn on *Device supports OTAA*.
- **Applications** → create one. Call it anything.
- **Gateways** → add your gateway with its gateway EUI, and point the gateway's
  packet forwarder at this host on UDP port 1700.
- **Applications → your application → Devices** → add a device with the DevEUI,
  AppEUI/JoinEUI and AppKey you flashed into the node. For EleTect X nodes
  those live in `device/mcu/src/secrets.h`, which is not in version control —
  see `device/mcu/src/secrets.h.example`.

**5. Point the bridge at the application.** Copy the application UUID from the
ChirpStack URL, put it in `CHIRPSTACK_APPLICATION_ID` in `.env`, then:

```sh
docker compose up -d eletect-ingest
```

This step is optional with a single application — unset means "subscribe to
all of them" — but it is worth doing, because it stops a second application
on the same broker from writing into the same Supabase tables.

## Checking it works

Watch uplinks arrive on the broker:

```sh
docker compose exec mosquitto mosquitto_sub -t 'application/#' -v
```

Watch the bridge decode them:

```sh
docker compose logs -f eletect-ingest
```

A joined node sends a status frame every ten minutes
(`LORA_STATUS_INTERVAL_MS`), so a quiet network should still produce traffic
within that window. If frames appear on MQTT but no rows appear in Supabase,
the problem is in `../ingest`; if nothing appears on MQTT, it is the gateway
or the join.

## Using a different region

The default is `in865`. Changing it is two edits plus one file, and all three
must agree or ChirpStack starts with no region loaded:

1. `CHIRPSTACK_REGION` in `.env` — drives the gateway-bridge topic templates
   and which Basics Station config is loaded.
2. `enabled_regions` in `configuration/chirpstack/chirpstack.toml`.
3. Copy `region_<name>.toml` into `configuration/chirpstack/` and
   `chirpstack-gateway-bridge-basicstation-<name>.toml` into
   `configuration/chirpstack-gateway-bridge/`, both from
   [chirpstack-docker](https://github.com/chirpstack/chirpstack-docker). Only
   the `in865` pair is vendored here; carrying all forty would mean carrying
   thirty-nine we never load.

Then `docker compose up -d --force-recreate`.

## Operational notes

**Mosquitto is deliberately unreachable from outside.** It allows anonymous
connections, so a host port would let anyone on the network publish a
fabricated uplink — a fake elephant detection that reaches real officers. If
you need to reach it from another machine, add authentication first.

**Ports 8080 and 8090 are bound to localhost.** Neither speaks TLS. Reach them
from elsewhere over an SSH tunnel or behind a reverse proxy that terminates
TLS, not by changing the binding.

**Uplinks queue while the bridge is down.** `mosquitto.conf` enables
persistence, the ChirpStack MQTT integration publishes at QoS 1, and the
bridge connects with a fixed client id and `clean: false` — so an undelivered
uplink waits in the broker and survives a broker restart. The bridge also
acknowledges each message only after the Supabase write succeeds
(`../ingest/src/mqtt.ts`), which means a write failure leaves the frame with
the broker instead of dropping it. Do not change `qos` back to 0 or remove the
`mosquittodata` volume without understanding that this is what stops a night
of alerts from being lost to a database outage.

**The stack restarts itself, the host does not.** Every service is
`restart: unless-stopped`, so they come back after a crash or a Docker
restart — but only if the Docker daemon itself starts at boot. On a
deployment host, enable that.

**Backups.** The `postgresqldata` volume holds the device keys and session
state; losing it means re-joining every node. Alert history lives in Supabase,
not here.
