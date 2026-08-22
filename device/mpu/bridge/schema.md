# Bridge RPC schema

Source of truth for the MCU↔MPU function boundary (`ENGINEERING_CONVENTIONS.md` §6). Both sides are
hand-written against this table, not against each other's code. Every payload carries `schema_version:
uint8 = 1` as its first field; bump on any breaking field change, never reuse a version number.

Two Bridge primitives, both confirmed against Arduino's own reference Bricks this session, not assumed:
`Bridge.call(name, args) -> return_value` is synchronous request/response — caller blocks until a response
or timeout. `Bridge.notify(name, args)` is fire-and-forget — no return value, caller does not block. Use
`notify` for MCU→MPU event pushes (the MCU must not stall on MPU wake state); use `call` for MPU→MCU
actuator commands (the MPU needs to know the action actually executed before deciding what happens next).

## MCU → MPU (STM32 notifies; MPU provides the handler)

| Function | Args | MCU-side behavior | MPU-side notes |
|---|---|---|---|
| `report_footfall_event` | `schema_version, probability: float, sta_lta_ratio: float, feature_vector: float[8]` | Fires once per geophone STA/LTA threshold crossing that also clears the on-MCU EI footfall model's confidence gate. Non-blocking — MCU continues its reflex loop regardless of MPU wake state. | If the MPU is suspended, this notify is what triggers wake (ADR 0008); Bridge's own reconnect/queue behavior handles the transport, this schema doesn't re-implement it. |
| `report_acoustic_event` | `schema_version, class_label: enum{gunshot, chainsaw, vehicle, animal_call, ambient}, confidence: float, capture_ref: uint32` | Fires once per on-MCU acoustic classifier crossing its confidence threshold (ADR 0009 primary path) or once per comparator-gated burst classification (ADR 0006 fallback) — same event shape either way. `capture_ref` indexes the raw window in MCU SRAM so the MPU can pull it via `read_acoustic_window()` if it wants raw audio, not just the label. | Gunshot routes to a direct LoRa alert, bypassing elephant-presence fusion entirely (ADR 0007 §5) — that routing is MPU-side logic; this field exists to make it possible without re-classifying. |
| `report_system_status` | `schema_version, battery_v: float, geophone_ok: bool, acoustic_ok: bool, lora_joined: bool, uptime_s: uint32` | Fires on a slow periodic timer (proposed: every 10 min), independent of any trigger, so the dashboard has a heartbeat during quiet periods. | A missed status for >2× the period is the stale-node signal — that logic lives in `web/backend`, not here. |

## MPU → MCU (MPU calls; STM32 provides the handler)

| Function | Args | Return | MCU-side failure behavior |
|---|---|---|---|
| `drive_horn` | `schema_version, gain_pct: float (0–100), duration_ms: uint16` | `ack: bool` | MCU enforces its own burst-duration cap and cooldown (ADR 0003) regardless of what's requested — an out-of-bounds request is clamped, not rejected, and `ack` reports the values actually used. Never blocks past the physical burst duration. |
| `drive_led` | `schema_version, pattern_id: uint8, duration_ms: uint16` | `ack: bool` | Same cooldown/cap discipline as `drive_horn`, independent counters. No `gain_pct` wire field — always driven at `config.h`'s `LED_GAIN_MAX_PCT` internally (see "Actuator gain defaults" below). |
| `pulse_ir` | `schema_version, duration_ms: uint16` | `ack: bool` | Gated by the IR MOSFET's own thermal/duty limits (`config.h`); over-duration requests clamp, and the clamp is reported in `ack`, never silently dropped. No `gain_pct` wire field — always driven at `config.h`'s `IR_GAIN_MAX_PCT` internally (see "Actuator gain defaults" below). |
| `get_system_state` | `schema_version` | `battery_v: float, geophone_ok: bool, acoustic_ok: bool, uptime_s: uint32` | Never blocks past one cached-struct read (same struct `report_system_status` pushes periodically) — not a fresh sensor poll. |
| `send_lora_alert` | `schema_version, confidence: float, capture_ref: uint32` | `ack: bool` | No real transport exists yet — the Grove E5 is not answering AT probes (`docs/KNOWN_GAPS.md`, 18 Aug entry), so the MCU-side handler only logs the request and always returns `ack=false`. `ack` means "queued/logged on the MCU," never "delivered over the air," until the module joins and a real uplink is wired in. Not idempotent, same as `drive_horn` — never retried on timeout. |

### Actuator gain defaults

`drive_horn` carries an explicit `gain_pct` wire field because horn deterrence intensity is a real,
call-to-call tunable the MPU-side policy needs. `drive_led` and `pulse_ir` do not, and this is a
deliberate contract decision, not an oversight: both are on/off flash-or-illuminate actuators —
`LED_GAIN_MAX_PCT` and `IR_GAIN_MAX_PCT` (`config.h`) are both `100.0f` today, i.e. full duty is the
only duty either has ever driven — and unlike the horn, no per-call variation has any established use
case. `pattern_id` selects *which* LED channel fires (`led_channel_for_pattern_id()`,
`device/mcu/src/bridge_handlers.h`), a separate axis from brightness; it does not and should not also
select gain, since `pulse_ir` has no `pattern_id` to map from and would need its own fixed default
regardless. Both MCU-side adapters (`device/mcu/src/bridge_handlers.cpp`) request their config max
unconditionally. If a real LED/IR intensity requirement shows up, add `gain_pct` to these rows as a
breaking schema change (bump `schema_version`) rather than overloading `pattern_id` — see
`docs/KNOWN_GAPS.md` for the pattern-semantics gap this does *not* resolve (what `pattern_id` values
should mean beyond channel selection).

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
