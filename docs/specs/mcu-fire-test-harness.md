# Spec — MCU manual fire-test harness

Status: ready to build. Written by the planning session, 14 Aug, against the actual current state of
`device/mcu/src/` (not generic advice — every convention below is copied from code already in the repo).
Build exactly this; if something here conflicts with a file you're looking at, the real file wins and
the conflict should be logged in `docs/KNOWN_GAPS.md`, not silently resolved either way.

## Why this exists

`horn.cpp`, `led.cpp`, `ir.cpp` are real, complete drivers — nobody has fired any of them on real
hardware yet. Before any decision logic (fusion, bandit, Bridge wiring) gets layered on top, someone
needs to confirm the horn, LEDs, and IR illuminator physically switch on command. This harness is a
serial-command bench tool for exactly that: type a character in App Lab's Serial Monitor, one actuator
fires once, the full ack prints back. Nothing autonomous, nothing Bridge-registered — a human has to
type the command each time, which is the point: it cannot fire anything unattended.

## Scope boundary — read this before writing any code

This harness calls `drive_horn()`, `drive_led()`, `pulse_ir()` **directly as C++ functions**. It does
**not** touch `Bridge.provide()`. `docs/KNOWN_GAPS.md` and `device/mpu/bridge/rpc.py`'s module
docstring both document that Bridge registration for these three functions is deliberately deferred to
its own hardware session, one function at a time, because a past registration attempt broke every
previously-working Bridge function on the same sketch. Do not register anything with Bridge as part of
this feature. If that temptation comes up, stop and flag it instead.

## Files to add

Both files are new, flat in `device/mcu/src/` — per ADR 0010, `src/` has no subfolders and every file
sits at the same depth with plain `#include "whatever.h"`. Don't create a subfolder for this.

- `device/mcu/src/fire_test.h`
- `device/mcu/src/fire_test.cpp`
- `device/mcu/tests/test_fire_test/test_fire_test.cpp` (new test directory, mirrors `test_rule_gate/`)

## `fire_test.h` — public surface

```cpp
#ifndef FIRE_TEST_H
#define FIRE_TEST_H

#include <stdint.h>

// One serial-command byte maps to exactly one bench actuator target, or to
// no target at all. Pure function, no hardware calls, no side effects -
// this is the one piece of the harness that's host-testable without a
// board, same discipline as rule_gate.h's pure core (ENGINEERING_CONVENTIONS.md 4).
enum class fire_test_target { kNone, kHorn, kLedWhite, kLedBlue, kIr, kHelp };

fire_test_target fire_test_parse_command(char c);

void fire_test_init();
void fire_test_service(uint32_t now_ms);

#endif  // FIRE_TEST_H
```

## `fire_test.cpp` — behavior

Command map (single ASCII digit per actuator, kept deliberately unambiguous — no letter overlaps with
anything else the firmware prints or expects):

| Key | Target | Default request |
|---|---|---|
| `1` | Horn | `duration_ms=FIRE_TEST_HORN_DURATION_MS, gain_pct=FIRE_TEST_HORN_GAIN_PCT` |
| `2` | LED white | `duration_ms=FIRE_TEST_LED_DURATION_MS, gain_pct=FIRE_TEST_LED_GAIN_PCT` |
| `3` | LED blue | same constants as white, different channel |
| `4` | IR | `duration_ms=FIRE_TEST_IR_DURATION_MS, gain_pct=FIRE_TEST_IR_GAIN_PCT` |
| `?` | — | prints the command menu, fires nothing |

`fire_test_parse_command()` is a plain `switch` on the char, no I/O, returns the enum — this is the
function `test_fire_test.cpp` exercises directly.

`fire_test_service(uint32_t now_ms)`:
1. `if (!Serial.available()) return;` — non-blocking poll, same shape as `geophone_service()`'s
   per-loop-iteration style in `main.cpp`.
2. Read one byte, call `fire_test_parse_command()`.
3. On `kHorn`/`kLedWhite`/`kLedBlue`/`kIr`: build the request struct from the table above, call the
   real driver function (`drive_horn`, `drive_led`, `pulse_ir` — exact signatures already in
   `horn.h`/`led.h`/`ir.h`, don't redeclare them), then print the **full ack**, not just true/false:

   ```cpp
   Serial.print("[firetest] horn allowed=");
   Serial.print(ack.allowed);
   Serial.print(" duration_ms=");
   Serial.print(ack.duration_ms);
   Serial.print(" gain_pct=");
   Serial.print(ack.gain_pct);
   Serial.print(" clamped=");
   Serial.println(ack.clamped);
   ```

   This follows the `[tag] key=value key=value` convention used by `log_trigger()` in
   `state_machine.cpp`, and directly addresses the KNOWN_GAPS note that `ack: bool` alone is too lossy
   to be useful — the harness's whole job is to make clamped/allowed/actual-values visible.
4. On `kHelp` or unrecognized byte: print the four-line command menu.

**Cooldown is expected to refuse repeated commands — this is not a bug.** `rule_gate_apply()` already
enforces `HORN_COOLDOWN_MS=30000`, `LED_COOLDOWN_MS=20000`, `IR_MIN_INTERVAL_MS=5000` per actuator.
Pressing `1` twice inside 30s will print `allowed=false` the second time. Say so explicitly in the
printed menu (`? ` output) so whoever's running the test doesn't think it's broken.

**This call blocks.** `horn.cpp`'s fire sequence is a blocking `delay()` chain (up to
`HORN_BURST_MAX_MS=3000` plus the amp-enable delay); `led.cpp`/`ir.cpp` block for their own
`duration_ms`. During a manual fire-test command, `geophone_service()` and `lora_service()` in the same
`loop()` iteration are blocked too, for up to ~3.15s in the horn case. Acceptable for a bench-only,
human-triggered tool — call this out as a one-line comment in `fire_test.cpp`, don't silently leave it
implicit the way a reviewer would have to go find out for themselves.

## Bench-safe default values — add to `config.h`'s bench-flags block

Same section as `SEISMIC_DEBUG_STREAM_RAW` and friends, same banner discipline (must default to a form
that's safe to ship, rationale comment, "confirm before `sync-to-board.sh`"):

```c
// Manual fire-test harness - serial-command-triggered single fire of
// horn/LED/IR for hardware bring-up verification. Human types a digit into
// App Lab's Serial Monitor; nothing fires without that keystroke, so this
// has no autonomous trigger path. Still gated to 0 by default: the point of
// field builds is that bench-only surface area doesn't exist in them.
#define FIRE_TEST_HARNESS 0

// Bench defaults - short and conservative, real safety backstop is still
// rule_gate_apply()'s per-actuator caps (HORN_GAIN_MAX_PCT etc.), these are
// just sane starting points for a desk-bench test, not a duplicate limit.
#define FIRE_TEST_HORN_DURATION_MS 500   // well under HORN_BURST_MAX_MS=3000
#define FIRE_TEST_HORN_GAIN_PCT 30.0f    // under HORN_GAIN_MAX_PCT=60, desk-volume not field-volume
#define FIRE_TEST_LED_DURATION_MS 1000
#define FIRE_TEST_LED_GAIN_PCT 50.0f
#define FIRE_TEST_IR_DURATION_MS 200     // under IR_PULSE_MAX_MS=500
#define FIRE_TEST_IR_GAIN_PCT 100.0f     // IR is invisible, thermal is the only real constraint
```

## Wiring into `main.cpp`

Same `#if`/`#endif` shape already used for `SEISMIC_DEBUG_STREAM_RAW`'s `Bridge.begin()`/`Bridge.update()`
carve-out — don't invent a different gating style:

```cpp
void setup() {
  Serial.begin(CONSOLE_BAUD);
#if SEISMIC_DEBUG_STREAM_RAW
  Bridge.begin();
#endif
#if FIRE_TEST_HARNESS
  fire_test_init();
#endif
  geophone_init();
  horn_init();
  led_init();
  ir_init();
  lora_init();
  state_machine_init();
}

void loop() {
  const uint32_t now_ms = millis();
#if SEISMIC_DEBUG_STREAM_RAW
  Bridge.update();
#endif
#if FIRE_TEST_HARNESS
  fire_test_service(now_ms);
#endif
  geophone_service();
  lora_service(now_ms);
  state_machine_tick(now_ms);
}
```

`fire_test_init()` can be a no-op or just print the command menu once at boot — your call, keep it
small either way.

## Tests — `test_fire_test/test_fire_test.cpp`

Only `fire_test_parse_command()` is host-testable (it's pure — no `Serial`, no hardware, matches the
"pure core" testing discipline `test_rule_gate.cpp` already follows). The actual fire behavior can only
be verified live on the board via App Lab's browser Serial Monitor — **not** `arduino-cli monitor`,
which ADR 0010's addendum confirms delivers zero bytes even for an unconditional periodic print. Don't
try to test the live fire path from a host build; it's a hardware-session task, not a `pio test` task.

Match `test_rule_gate.cpp`'s exact shape: `#include <unity.h>` first, empty `setUp()`/`tearDown()`,
`static void test_<behavior>(void)` names, `_MESSAGE` assertion variants, every test explicitly listed
in `main()`. Minimum coverage:

- `test_digit_1_maps_to_horn`
- `test_digit_2_maps_to_led_white`
- `test_digit_3_maps_to_led_blue`
- `test_digit_4_maps_to_ir`
- `test_question_mark_maps_to_help`
- `test_unrecognized_byte_maps_to_none`
- `test_whitespace_and_newline_bytes_map_to_none` (Serial Monitor sends a line terminator — make sure
  `\n`/`\r` don't get mis-parsed as a command)

Run with `pio test -e native` from `device/mcu/`, same as the existing suite.

## Docs to update as part of this change

- `docs/KNOWN_GAPS.md`: add a line noting the fire-test harness now exists as the intended mechanism to
  bench-measure `HORN_AMP_ENABLE_DELAY_MS` (currently invented, per the existing gap entry) and to
  sanity-check the provisional burst/cooldown constants — don't mark those gaps closed, just note the
  tool now exists to close them.
- Commit message, Conventional Commits, e.g. `feat(mcu): add serial fire-test harness for horn/led/ir bench verification`.
- No AI/assistant attribution anywhere — commit message, code comments, this spec's own presence
  nowhere referenced in-repo. Standard repo-wide rule, not new to this feature.

## Verification checklist before calling this done

1. `pio test -e native` passes, all seven `test_fire_test` cases plus the existing suite green.
2. `pio run -e native` (or whatever the field-target env is) compiles with `FIRE_TEST_HARNESS 0` —
   confirms the flag truly compiles out, not just logically disabled.
3. Flip to `FIRE_TEST_HARNESS 1` locally, confirm it also compiles.
4. Flash via App Lab (per ADR 0010, the only real flash path), open App Lab's browser Serial Monitor,
   type `1`, confirm the horn fires and the `[firetest]` ack line prints. Repeat for `2`, `3`, `4`.
   Press `1` twice within 30s, confirm the second attempt prints `allowed=false` — that's the cooldown
   gate working, not a failure.
5. Set `FIRE_TEST_HARNESS` back to `0` before this ever goes near `scripts/sync-to-board.sh` for a
   node headed to the field.
