# ADR 0031: LoRaWAN uplink payload, delivery and alert routing

- **Status:** accepted
- **Date:** 2026-09-30
- **Amends:** ADR 0002 (what goes over LoRa), ADR 0029 B.3 (when a joined radio takes USART1)

## Context

ADR 0002 puts alerts and health on LoRaWAN (Grove LoRa-E5 → SenseCAP gateway, IN865 → ChirpStack →
MQTT → `web/ingest` → Supabase → `send-alert`). The MCU could join, but nothing defined what a frame
contained, who retried it, or how the server told a re-sent frame from a new event. IN865 airtime is
scarce and a node can be days from a technician, so the format has to be small, versioned, and
decodable without anything configured by hand on the network server.

## Decision

### A. Frames

Every frame goes out on **FPort 10**, big-endian. Byte 0 is `(format << 4) | type` with format 1;
byte 1 is a `seq` assigned when the frame is queued and reused on every re-send of that frame.

**Event (type 2, 10 bytes)**

| Byte | Field |
|---|---|
| 2 | class: 0 unconfirmed (seismic alert, no camera), 1 elephant, 2 boar, 3 gunshot, 4 chainsaw |
| 3 | confidence, whole percent 0–100 |
| 4 | deterrence tier 0–3 (0 = none selected) |
| 5 | flags: 0x01 vision confirmed, 0x02 deterrent fired, 0x04 SAFE_MODE dry run |
| 6–9 | capture_ref, u32 |

**Status (type 1, 9 bytes)**

| Byte | Field |
|---|---|
| 2 | flags: 0x01 geophone ok, 0x02 home test |
| 3–4 | battery mV, 0xFFFF = unknown |
| 5–8 | uptime s, u32 |

Class values are append-only. An unknown class decodes as "no species" rather than an error, so
newer firmware never loses an event on an older server. Known-answer vectors are shared between
`device/mcu/tests/test_uplink` and `web/ingest/src/payload.test.ts`.

**No species is guessed.** The MPU knows the camera confirmed *a* deterrent target, not which one.
A node that deters exactly one species reports it; a node that deters several reports class 0 with
the vision flag set.

### B. Delivery (MCU, `mac.cpp`)

- Events are **confirmed** uplinks (`AT+CMSGHEX`); status heartbeats are unconfirmed (`AT+MSGHEX`),
  sent right after the join and then periodically.
- A small fixed queue. A new status replaces a queued one. When full, an event evicts the oldest
  status; otherwise it is refused and the Bridge call returns `false`.
- A frame the E5 reports as busy, no free channel or unacknowledged is retried with a linearly
  growing delay, and dropped after a fixed number of attempts. "Please join network first" re-joins
  and keeps the queue. "Length error" drops the frame.
- **A horn fire mid-send** (ADR 0029) re-sends the same bytes, same `seq`, without charging an
  attempt — the E5 may already have transmitted it.
- ADR 0029 B.3 is amended: a joined radio takes USART1 only when a queued frame is due, and gives
  it back when the exchange ends.

### C. MPU (`comms/lora_uplink.py`)

A fusion alert that vision did not overrule, or any camera confirmation, becomes one
`send_lora_event` Bridge call; a trigger fusion dismissed stays local. Gunshots use the same call.
Calls run on their own thread from a bounded queue, so a slow radio never delays a deterrent, and
are never retried on timeout (each call is a separate uplink).

### D. Server

- `web/ingest` decodes the raw bytes itself — **no ChirpStack payload codec**. The format lives in
  version control beside its tests, and a network-server reinstall cannot silently drop it.
- A frame with the same `seq` from the same node inside 15 minutes is a re-send and is dropped.
  `seq` wraps at 256, far slower than that window at the heartbeat rate.
- The decoded frame and radio metadata are stored in `events.uplink` (migration 0004); status goes
  to `health.metrics`.
- **Priority:** camera-confirmed wildlife and gunshot/chainsaw are `high` and page people. A
  seismic-only alert is `normal`: it shows on the dashboard but does not wake a village.
- **Audience (`send-alert`):** wildlife goes to officers and opted-in residents within 3 km.
  Gunshot and chainsaw go to **officers only** — paging residents would send them towards armed
  people and could tip off whoever fired.

## Consequences

- A whole event is 10 bytes, well inside the smallest IN865 data-rate payload.
- Dedupe depends on `seq` surviving a re-send, which is why it is assigned at queue time.
- Battery is reported as unknown until a battery ADC is fitted; `health.battery_pct` stays null.
- Changing a byte's meaning needs format 2 and both decoders updated together.

## Bring-up checks

1. OTAA join over the shared USART1; first status frame appears in ChirpStack on FPort 10.
2. `send_lora_event` from the MPU reaches the MCU (one new `Bridge.provide`, six scalars).
3. A confirmed event is acknowledged, lands in `events` with `uplink` filled, and `send-alert`
   reaches officers only for a gunshot and officers plus residents for a confirmed elephant.
4. Fire the horn during a send and confirm exactly one `events` row.
