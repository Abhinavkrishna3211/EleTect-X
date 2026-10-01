# ADR 0031: LoRaWAN uplink payload, delivery and alert routing

- **Status:** accepted
- **Date:** 2026-09-30
- **Amends:** ADR 0002 (what goes over LoRa), ADR 0029 B.3 (when a joined radio takes USART1)
- **Amended:** 2026-10-02 — see the amendment immediately below, which replaces §A's "no species
  is guessed" rule and widens §D's priority and audience tables

## Amendment, 2 Oct 2026 — the frame carries the species the camera saw (not a rewrite of this ADR)

Everything below stands as written except the four points here. The byte layout is unchanged; two
class values and one flag bit are **appended**, which §A's append-only rule already permits.

**1. §A's "No species is guessed" paragraph is replaced.** It read: a node that deters exactly one
species reports it; a node that deters several reports class 0 with the vision flag set. That was
honest about the mechanism it described — `confirmed_class()` inferred the species from the node's
*configuration*, on the reasoning that one configured target meant it must have been that one — but
the mechanism itself was wrong, and multi-species nodes are now the normal case rather than the
exception, so most events would have arrived species-less.

The rule was always meant to say something narrower, and now does: **report what the camera
observed; never infer a species from configuration.** The vision watch knew which label confirmed
and discarded it before building the outcome; it is now threaded through and reported on the frame.
A node deterring three species names the one it saw. Class 0 keeps its meaning — a seismic alert
with no camera confirmation — rather than doubling as "could not tell which".

This is required rather than cosmetic: the routing rules in point 3 are undecidable in the backend
without a species on the frame.

**2. Two classes and one flag, appended in lockstep.** `5 = elephant_call` (ADR 0033) and
`6 = fox` join §A's class table; `0x08 = no retreat` joins its flag byte. Appended across
`device/mcu/src/uplink.h` (`UPLINK_EVENT_CLASS_MAX` → 6), `comms/lora_uplink.py`,
`web/ingest/src/payload.ts` and `send-alert/message.ts`, with the known-answer byte vectors in
`device/mcu/tests/test_uplink/` and `payload.test.ts` updated together — those shared vectors are
the only thing keeping the two decoders honest. **No DDL:** `events.species` and `events.priority`
are plain `text` with no CHECK and no Postgres enum.

`5` stays distinct from `1` because an officer must be able to tell a microphone detection from a
camera one — they have different false-positive profiles — and it therefore never carries
`FLAG_VISION_CONFIRMED`.

**3. §D's priority and audience tables are replaced by this one.**

| Trigger | Dashboard | Officers | Residents within 3 km |
|---|---|---|---|
| Any detection | yes | — | — |
| Gunshot, chainsaw | yes | yes (`high`) | **never** |
| Elephant sighted and deterred | yes | yes (`high`) | yes |
| Elephant, top tier, **did not retreat** | yes | yes (`critical`) | yes |
| Boar, fox | yes | no push | no push |

`audienceFor()` **stops failing open.** It consulted nothing and returned "officers and residents"
for every species that was not gunshot or chainsaw, so a fox would have paged a village. It now
reads the species registry's audience class, and anything unmapped — including a class byte from
firmware newer than the running backend — resolves to `staff_only` rather than defaulting to the
loudest possible fan-out. Boar and fox stay `priority = 'normal'`: on the dashboard, no push.

A third priority value `'critical'` is added, and the gates in `send-alert/index.ts` and the
`public_area_risk` view widen from `= 'high'` to `in ('high','critical')`. `'critical'` means one
specific thing — the node reached the top of its ladder and the animal did not leave — and the
officer-facing text says a forest team is being requested rather than instructing the reader to
send one, because residents within 3 km receive the same text.

**4. `alertText()`'s fallback asserts nothing.** An unknown or absent species renders as
"unidentified detection", and the anti-poaching advice line is keyed off the species rather than
off the audience. Those were the same test while `staff_only` meant "poaching sound"; now
`staff_only` is also the default for anything unnamed, and telling an officer to follow the
anti-poaching protocol because the class byte was one this build does not know would be a
fabricated instruction.

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
