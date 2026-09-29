// Manual bench fire-test harness - maps a single Serial byte to one direct
// call into horn.h/led.h/ir.h, for hardware bring-up verification before any
// decision logic (fusion, bandit, Bridge wiring) sits on top of the
// actuators. Human-triggered only: nothing here fires without a keystroke,
// and no Bridge.provide() registration happens (docs/specs/
// mcu-fire-test-harness.md's scope boundary).

#ifndef FIRE_TEST_H
#define FIRE_TEST_H

#include <stdint.h>

// One serial-command byte maps to exactly one bench actuator target, or to
// no target at all. Pure function, no hardware calls, no side effects -
// this is the one piece of the harness that's host-testable without a
// board, same discipline as rule_gate.h's pure core (ENGINEERING_CONVENTIONS.md 4).
//
// kDfplayerAt is the raw-AT console mode added for the horn bring-up
// (docs/decisions - ADR superseding 0015 Decision A): typing 'a' reads one
// more line from Serial and forwards it verbatim to DFPLAYER_SERIAL, printing
// whatever comes back. It exists to run the AT/AT+QUERY probes Stage B of the
// bring-up needs and that no other harness path can send.
//
// kListen is Stage C's track-identification mode: typing 'l' reads a track
// number and calls horn_debug_listen(), which runs the same fire/stop
// sequence as kHorn but bypasses rule_gate_apply() entirely (no cooldown, no
// HORN_BURST_MAX_MS clamp) so a whole clip can play long enough to identify
// by ear. kHorn stays on the real drive_horn()/rule_gate path for verifying
// production timing/cooldown behavior (Stage D) - the two are deliberately
// different code paths, not a duplicate.
//
// kListenByFile is kListen's by-name counterpart: typing 'f' reads a FAT
// filename instead of a track number and calls horn_debug_listen_file(),
// which selects the file with AT+PLAYFILE rather than AT+PLAYNUM. Added
// because AT+QUERY's index/filename readback proved unreliable, so a
// by-index identification can't be pinned to a specific file with
// confidence - playing an exact known filename can.
enum class fire_test_target {
  kNone,
  kHorn,
  kLedWingLeft,
  kLedWingRight,
  kIr,
  kDfplayerAt,
  kListen,
  kListenByFile,
  kHelp
};

// No precondition - total over every char value, including whitespace/
// newline bytes a Serial Monitor's line terminator sends. Cannot fail: an
// unrecognized byte resolves to kNone, never an error. Never blocks.
fire_test_target fire_test_parse_command(char c);

// One-time setup: prints the command menu once. No precondition, cannot
// fail, never blocks.
void fire_test_init();

// Call once per loop() iteration; safe to call whether or not a byte is
// waiting. Non-blocking when Serial has nothing available. When a byte
// resolves to kHorn/kLedWingLeft/kLedWingRight/kIr, blocks for that actuator's own
// resolved fire duration because it calls the real driver function directly
// (drive_horn/drive_led/pulse_ir - up to ~3.15s in the horn case, see
// horn.h/led.h/ir.h's own blocking notes); geophone_service()/lora_service()
// in the same loop() iteration are starved for that window, same as any
// other actuator fire. kDfplayerAt blocks up to FIRE_TEST_AT_LINE_TIMEOUT_MS
// waiting for the human to finish typing a command line, then up to
// FIRE_TEST_AT_REPLY_TIMEOUT_MS waiting for the DFPlayer's reply - both
// bounded, same convention as the actuator durations above. Cannot fail
// outright: an unrecognized byte, a cooldown-refused request, or an AT
// timeout prints the menu, an allowed=false ack, or a timeout notice rather
// than crashing or hanging past the bounded durations above.
void fire_test_service(uint32_t now_ms);

#endif  // FIRE_TEST_H
