# Bridge RPC schema

Source of truth for the MCU↔MPU function boundary (`ENGINEERING_CONVENTIONS.md` §6). Both sides are
hand-written against this table, not against each other's code. Every payload carries `schema_version:
uint8 = 128` as its first field; bump on any breaking field change, never reuse a version number.

**The wire value is 128, not 4.** The schema is *semantically* at version 4 — the version-history
entries below number 1..4 and that numbering continues — but the byte actually sent is `128`. That is
not a fifth revision; it is version 4 carried in a value that survives the wire. The on-device MsgPack
library (0.4.2, vendored in `Arduino_RPClite`) mis-decodes any unsigned integer small enough to encode
as MessagePack *positive fixint* (0-127, one byte), rejecting the call with `MALFORMED_CALL_ERR`
despite the value being correct; 128 is the first value that forces the explicit `uint8` (`0xCC`)
format, which decodes correctly. Bench-verified 2026-09-09 by holding every other field fixed and
varying only this one. Both sides carry it: `device/mcu/src/config.h`'s `BRIDGE_SCHEMA_VERSION` and
`device/mpu/services/config.py`'s `SCHEMA_VERSION`, which must move together. The same bug affects
every other small unsigned field on the boundary, and those could *not* be renumbered this way because
their values are meaningful — see `device/mpu/bridge/wire_compat.py`, which patches the encoder
instead. A future schema 5 would be sent as `129`.

**Version history**
- `1` — initial boundary.
- `2` (2026-09-01, ADR 0014) — `drive_led` args changed from `pattern_id, duration_ms` to
  `channel, pattern_id, gain_pct, duration_ms`. `channel` (which wing) split out of `pattern_id` into
  its own field; `pattern_id` goes back to meaning "which flash pattern"; `gain_pct` added so the tier
  ladder can vary LED brightness. `drive_horn`, `pulse_ir`, and every MCU→MPU row are unchanged.
- `3` (2026-09-01, ADR 0014 §E) — `drive_led` gains dual-wing addressing. `channel` value `2` changes
  meaning from "unrecognized → left wing" to "**both wings**, driven together inside one blocking
  call"; `pattern_id` gains `4 = sweep` (wings antiphase at fast-strobe rate), `5 = pulse both sync`
  (wings in phase at fast-strobe rate), `6 = flicker both independent` (each wing its own irregular
  flicker). No wire field added or removed — the payload shape is identical to `2` — but a `2`-era
  sender that sent `channel = 2` expecting the left-wing fallback now fires both wings, so it is a
  breaking change. `drive_horn`, `pulse_ir`, and every MCU→MPU row are unchanged.
- `4` (2026-09-02, ADR 0015) — `drive_horn` gains a trailing `track_id: uint8`. The DFPlayer PRO is now
  driven over a real AT-command UART (`AT+PLAYNUM=<track_id>`, then `AT+VOL` from `gain_pct`), so the
  horn plays a selectable sound — bee swarm, predator growl, air horn, firecracker (ADR 0016) — instead
  of one fixed clip. `track_id` is a content selector, not a limit: the MCU does not clamp it and the
  ack does not echo it. A `3`-era sender omitting the field is a breaking mismatch. `drive_led`,
  `pulse_ir`, and every MCU→MPU row are unchanged.
- `4` continues (2026-10-01, ADR 0035) — **no bump.** `report_seismic_batch` is added to the
  MCU→MPU table. A new method is additive: an older peer that has never heard of it simply never
  receives it, and no existing payload shape changes. The version counter is reserved for breaking
  changes to a row that already exists, which is what every entry above is. Recorded here anyway,
  because "the table changed and the version did not" is exactly the kind of silent edit this
  history exists to make impossible.

Two Bridge primitives, both confirmed against Arduino's own reference Bricks, not assumed:
`Bridge.call(name, args) -> return_value` is synchronous request/response — caller blocks until a response
or timeout. `Bridge.notify(name, args)` is fire-and-forget — no return value, caller does not block. Use
`notify` for MCU→MPU event pushes (the MCU must not stall on MPU wake state); use `call` for MPU→MCU
actuator commands (the MPU needs to know the action actually executed before deciding what happens next).

## MCU → MPU (STM32 notifies; MPU provides the handler)

| Function | Args | MCU-side behavior | MPU-side notes |
|---|---|---|---|
| `report_footfall_event` | `schema_version, probability: float, sta_lta_ratio: float, feature_vector: float[8]` | Fires once per geophone STA/LTA threshold crossing that also clears the on-MCU EI footfall model's confidence gate. Non-blocking — MCU continues its reflex loop regardless of MPU wake state. | If the MPU is suspended, this notify is what triggers wake (ADR 0008); Bridge's own reconnect/queue behavior handles the transport, this schema doesn't re-implement it. |
| `report_seismic_batch` | `schema_version, first_sample_index: uint32, count: uint8, samples: int16[32], geophone_ok: bool` | Pushed continuously by the geophone service while `SEISMIC_CAPTURE_ENABLED` is set (ADR 0035), one notify per `SEISMIC_CAPTURE_BATCH_SAMPLES` accepted conversions — ~7.8/s at 250 SPS, ~1.0 kB/s, about 9% of the 115200 link. Carries the ADC's native `int16` counts, not volts: lossless, and it avoids the float32/float64 width ambiguity in the Bridge type map, which a 256-byte budget cannot absorb. `first_sample_index` is `samples[0]`'s position in `geophone_sample_count()`'s monotonic sequence; it is a uint32 and it wraps. A sample that does not continue the batch in progress flushes that batch short, so a discontinuity always appears *between* two notifies and never inside one. `geophone_ok` is the AND over every sample in the batch — a sensor that recovers mid-batch must not relabel the stale samples in front of it. Fire-and-forget by design: a `call` would block the reflex loop, and recording must continue straight through a deterrence fire. | The MPU stitches batches by index (`perception/seismic_stream.py`), records a named gap where one never arrived rather than splicing across it, and the vision watch labels the result minutes later (ADR 0035). **A full batch encodes to 133 of the Bridge's 256 bytes** (`BRIDGE_MAX_MESSAGE_BYTES`, `seismic_capture_encoded_bytes()`); an oversized notify is dropped *silently*, so that budget is a `static_assert`, not a runtime check. The figure is computed, never measured — nobody in this repo has encoded a Bridge frame and counted bytes, which is why the batch size leaves 123 bytes of slack. Neither side of this row has run on hardware: `SEISMIC_CAPTURE_ENABLED` is `0` and the MPU's `Bridge.provide()` is commented out, per the one-registration-per-hardware-session discipline in `DEVICE_DEVELOPMENT_WORKFLOW.md` §3. |
| `report_acoustic_event` | `schema_version, class_label: enum{gunshot, chainsaw, elephant_call, ambient}, confidence: float, capture_ref: uint32` | Fires once per on-MCU acoustic classifier crossing its confidence threshold (ADR 0009 primary path) or once per comparator-gated burst classification (ADR 0006 fallback) — same event shape either way. `capture_ref` indexes the raw window in MCU SRAM so the MPU can pull it via `read_acoustic_window()` if it wants raw audio, not just the label. | Three MPU-side routes (ADR 0007 §5 as ADR 0033 amends it): gunshot and chainsaw go straight out as a direct LoRa alert to officers, never touching elephant-presence fusion; `elephant_call` starts a vision-gated footfall event and alerts only if the camera confirms, so the microphone never alerts alone; `ambient` routes nowhere. All of that is MPU-side logic — this field exists to make it possible without re-classifying. |
| `report_system_status` | `schema_version, battery_v: float, geophone_ok: bool, acoustic_ok: bool, lora_joined: bool, uptime_s: uint32` | Fires on a slow periodic timer (proposed: every 10 min), independent of any trigger, so the dashboard has a heartbeat during quiet periods. | A missed status for >2× the period is the stale-node signal — that logic lives in `web/backend`, not here. |

## MPU → MCU (MPU calls; STM32 provides the handler)

| Function | Args | Return | MCU-side failure behavior |
|---|---|---|---|
| `drive_horn` | `schema_version, gain_pct: float (0–100), duration_ms: uint16, track_id: uint8` | `ack: bool` | MCU enforces its own burst-duration cap and cooldown (ADR 0003) regardless of what's requested — an out-of-bounds request is clamped, not rejected, and `ack` reports the values actually used. Never blocks past the physical burst duration. `gain_pct` maps to the DFPlayer absolute volume `round(gain_pct/100 · 30)` sent as `AT+VOL`; `track_id` (added `schema_version 4`, ADR 0015) is sent as `AT+PLAYNUM` to pick the sound (1 = bee swarm, 2 = tiger, 3 = lion, 4 = air horn, 5 = firecracker — ADR 0016 Decision C). `track_id` is a content selector, not a limit: not clamped, not echoed in `ack`. |
| `drive_led` | `schema_version, channel: uint8, pattern_id: uint8, gain_pct: float (0–100), duration_ms: uint16` | `ack: bool` | Same cooldown/cap discipline as `drive_horn`, with **per-channel** independent counters — the left wing firing does not gate the right. `channel`: 0 = left wing, 1 = right wing, 2 = both wings (`led_channel_from_wire()`, `device/mcu/src/bridge_handlers.cpp`); unrecognized → left. A `channel = 2` call gates on **both** wings' cooldown counters — refused (`ack=false`) if *either* wing is still cooling — and updates both on a fire; it runs one blocking loop toggling both pins, so it blocks for `duration_ms`, not twice that (ADR 0014 §E). `pattern_id`: 0 = steady, 1 = slow pulse, 2 = fast strobe, 3 = random flicker (single-wing); 4 = sweep (both wings antiphase, fast-strobe rate), 5 = pulse both sync (both wings in phase, fast-strobe rate), 6 = flicker both independent (each wing independently-seeded irregular flicker) (`led_pattern_from_id()`, `device/mcu/src/led.h`); unrecognized → steady. The three dual-wing patterns only make sense with `channel = 2`; addressed to a single wing they fall through to steady on that one wing. Every pattern is a flash sequence whose on/off spans sum to exactly `duration_ms`, so blocking cost is identical to a steady burst regardless of pattern (ADR 0014). `gain_pct` clamps to `LED_GAIN_MAX_PCT`; the clamp is reported in `ack`. |
| `pulse_ir` | `schema_version, duration_ms: uint16` | `ack: bool` | Gated by the IR MOSFET's own thermal/duty limits (`config.h`); over-duration requests clamp, and the clamp is reported in `ack`, never silently dropped. No `gain_pct` wire field — always driven at `config.h`'s `IR_GAIN_MAX_PCT` internally (see "Actuator gain defaults" below). |
| `get_system_state` | `schema_version` | `battery_v: float, geophone_ok: bool, acoustic_ok: bool, uptime_s: uint32` | Never blocks past one cached-struct read (same struct `report_system_status` pushes periodically) — not a fresh sensor poll. |
| `send_lora_event` | `schema_version, event_class: uint8, confidence: float (0–1), tier: uint8 (0–3), flags: uint8, capture_ref: uint32` | `ack: bool` | Queues one detection event for LoRaWAN uplink (ADR 0031) and returns at once — `ack` means "queued on the MCU", never "delivered": the E5 sends it as a confirmed uplink on FPort 10 once the node is joined and USART1 is free of the DFPlayer (ADR 0029), retries an unacknowledged frame up to 3 times, and re-sends one cut short by a horn fire with the same `seq` so the server can drop the duplicate. `event_class`: 0 = unconfirmed (seismic alert, no camera confirmation), 1 = elephant, 2 = boar, 3 = gunshot, 4 = chainsaw, 5 = elephant call (heard, not seen — never carries `0x01`, because a confirmed sighting is re-sent as 1), 6 = fox; anything else is sent as 0. Codes are append-only and are never renumbered — the same list appears in `device/mcu/src/uplink.h`, `device/mpu/comms/lora_uplink.py` and `web/ingest/src/payload.ts`, pinned against each other by the known-answer vectors in `device/mcu/tests/test_uplink/` and `web/ingest/src/payload.test.ts`. `confidence` is sent as a whole percent. `flags`: 0x01 vision confirmed, 0x02 deterrent fired, 0x04 SAFE_MODE dry run, 0x08 no retreat (the top tier fired and the animal was still there at the end of the retreat tail — the backend raises this to `priority = 'critical'`, ADR 0034). `ack=false` when the MCU queue already holds four undelivered events. Not idempotent — each call is a separate uplink, so the MPU never retries it on timeout (`comms/lora_uplink.py`). |

### Actuator gain defaults

`drive_horn` and `drive_led` each carry an explicit `gain_pct` wire field because deterrence intensity
is a real, call-to-call tunable the MPU-side tier ladder varies (ADR 0014 added it to `drive_led` in
`schema_version 2`; before that the LEDs always ran at `LED_GAIN_MAX_PCT`). `drive_led` also carries
`channel` (which wing, or both since `schema_version 3`) and `pattern_id` (which flash pattern) as
separate axes — brightness, wing, and pattern are independent and none of them selects another.

`pulse_ir` still has no `gain_pct` field, and that remains a deliberate contract decision: it is a
pure on/off illuminator, `IR_GAIN_MAX_PCT` (`config.h`) is `100.0f`, full duty is the only duty it has
ever driven, and no per-pulse variation has an established use case. Its MCU-side adapter
(`device/mcu/src/bridge_handlers.cpp`) requests the config max unconditionally. If a real IR-intensity
requirement shows up, add `gain_pct` to that row as a breaking schema change (bump `schema_version`).

## Same-side function contracts (MCU-internal, not Bridge calls — per `ENGINEERING_CONVENTIONS.md` §1/§2)

- **`read_seismic_window() -> float[N]`** — never blocks past one ADC conversion cycle; returns a
  zero-filled array (not null/exception) on an I²C/ADC timeout, so a transient glitch degrades one STA/LTA
  window rather than crashing the state machine. Backed by ADS1115+INA333 today, STM32 internal ADC via
  LPBAM once Rung 1 lands the swap — one signature, both implementations (`ENGINEERING_CONVENTIONS.md` §1).
- **`read_acoustic_window() -> float[N]`** — same contract shape. What backs it is still open pending the
  Rung 2 bench test in ADR 0009: if LPBAM sustains the mic channel concurrently with the geophone channel,
  this returns the continuously-buffered rolling window feeding the on-MCU classifier (ADR 0009 primary
  design); if that test fails, it returns the comparator-triggered capture instead (pre-trigger buffer if
  achievable, else post-trigger, per ADR 0006 §2a — the documented fallback). One contract, two possible
  backing implementations, resolved at Rung 2, not here.
- **`drive_horn`, `drive_led`, `pulse_ir` (MCU-side implementation, distinct from the Bridge wrapper above)**
  — each is a direct actuator driver satisfying the Bridge handler's contract: never blocks past the
  commanded duration, always returns/acks even on a GPIO-level fault (logged, not thrown).

## Open items this schema surfaces, not resolved here

- Exact wake latency for `report_footfall_event` / `report_acoustic_event` reaching a genuinely *suspended*
  (not just idle) MPU is ADR 0008's open bench item — this schema assumes the wake path works, it doesn't
  prove it.
- `capture_ref`'s indexing scheme (how MCU SRAM ring-buffers map to a stable reference the MPU can pull
  later) isn't designed yet — a Rung 2 build-session task, not a Rung 1 blocker.
