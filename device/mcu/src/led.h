// Deterrent LED pod driver - drives LED_WING_LEFT_PIN and LED_WING_RIGHT_PIN
// through the shared rule-gate clamp/cooldown core (rule_gate.h). Renamed
// from LED_WHITE_PIN/LED_BLUE_PIN (2026-08-30) to match the real
// 2-wing/2-MOSFET build (each wing mixes both LED colors, switched together)
// rather than the originally-documented per-color channel design.

#ifndef ACTUATORS_LED_H
#define ACTUATORS_LED_H

#include <cstdint>

// kWingBoth (wire value 2, schema_version 3, ADR 0014 E) drives both wings
// inside one drive_led() call - one blocking window, both pins toggled - so
// it blocks for the resolved duration_ms, not twice it. Only the three
// dual-wing patterns below (kSweep/kPulseBothSync/kFlickerBothIndependent)
// are meaningful on it; a single-wing pattern addressed to kWingBoth falls
// through to a plain synchronized on/hold on both pins.
enum class led_channel { kWingLeft, kWingRight, kWingBoth };

// ADR 0014 flash-pattern axis. Wire value is drive_led's pattern_id
// (schema.md); led_pattern_from_id() maps it, falling back to kSteady for
// any unrecognized id so a stale or garbled request still fires the safe
// default rather than nothing. Every pattern runs inside drive_led()'s
// existing blocking window and totals exactly the resolved duration_ms.
// 0-3 are single-wing (drive one pin); 4-6 are dual-wing (drive both pins
// in one window, ADR 0014 E) and expect led_channel::kWingBoth.
enum class led_pattern : uint8_t {
  kSteady = 0,         // on / hold / off - the pre-ADR-0014 behavior
  kSlowPulse = 1,      // LED_SLOW_PULSE_CYCLES whole on/off cycles, ~50% duty
  kFastStrobe = 2,     // LED_FAST_STROBE_HZ strobe across the burst, ~50% duty
  kRandomFlicker = 3,  // irregular on/gap flashes, micros()-seeded at call time
  kSweep = 4,          // both wings antiphase at LED_FAST_STROBE_HZ
  kPulseBothSync = 5,  // both wings in phase at LED_FAST_STROBE_HZ
  kFlickerBothIndependent = 6,  // both wings, independently-seeded kRandomFlicker
};

led_pattern led_pattern_from_id(uint8_t pattern_id);

struct led_request {
  led_channel channel;
  led_pattern pattern;
  uint16_t duration_ms;
  float gain_pct;  // maps to analogWrite() duty cycle, 0-100
};

struct led_ack {
  uint16_t duration_ms;
  float gain_pct;
  bool clamped;
  bool allowed;
};

// One-time setup: configures both LED pins as PWM outputs, off.
void led_init();

// Drives the requested channel with the requested pattern (led_pattern) for
// the resolved duration at the resolved gain, subject to that channel's own
// independent cooldown counter (left wing and right wing deter separately -
// one firing must not gate the other). Blocks for the resolved duration_ms:
// every pattern is a flash sequence whose on- and off-spans sum to exactly
// that duration, so the blocking cost is identical to a kSteady burst
// regardless of pattern (ADR 0014 / docs/KNOWN_GAPS.md). The reflex loop
// calling this must expect that, same caveat as horn.h's drive_horn.
//
// led_channel::kWingBoth drives both pins inside that same single window
// (ADR 0014 E): it is refused if *either* wing is in cooldown, resolves its
// duration/gain against the left wing's gate (both wings clamp identically
// when allowed), updates both wings' cooldown counters on a fire, and still
// blocks for only the resolved duration_ms - not twice it.
led_ack drive_led(led_request req, uint32_t now_ms);

#endif  // ACTUATORS_LED_H
