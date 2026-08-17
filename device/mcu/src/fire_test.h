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
enum class fire_test_target { kNone, kHorn, kLedWhite, kLedBlue, kIr, kHelp };

// No precondition - total over every char value, including whitespace/
// newline bytes a Serial Monitor's line terminator sends. Cannot fail: an
// unrecognized byte resolves to kNone, never an error. Never blocks.
fire_test_target fire_test_parse_command(char c);

// One-time setup: prints the command menu once. No precondition, cannot
// fail, never blocks.
void fire_test_init();

// Call once per loop() iteration; safe to call whether or not a byte is
// waiting. Non-blocking when Serial has nothing available. When a byte
// resolves to kHorn/kLedWhite/kLedBlue/kIr, blocks for that actuator's own
// resolved fire duration because it calls the real driver function directly
// (drive_horn/drive_led/pulse_ir - up to ~3.15s in the horn case, see
// horn.h/led.h/ir.h's own blocking notes); geophone_service()/lora_service()
// in the same loop() iteration are starved for that window, same as any
// other actuator fire. Cannot fail outright: an unrecognized byte or a
// cooldown-refused request prints the menu or an allowed=false ack rather
// than crashing or hanging past the bounded duration above.
void fire_test_service(uint32_t now_ms);

#endif  // FIRE_TEST_H
