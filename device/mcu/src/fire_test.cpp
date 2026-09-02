#include "fire_test.h"

#include "Arduino.h"
#include "config.h"
#include "horn.h"
#include "ir.h"
#include "led.h"

namespace {

void print_menu() {
  Serial.println("[firetest] commands: 1=horn 2=led_wing_left 3=led_wing_right 4=ir ?=help");
  Serial.println(
      "[firetest] cooldowns are real (horn 30s / led 20s / ir 5s) - a "
      "repeat within that window prints allowed=false, that is the gate "
      "working, not a bug");
}

// Shared ack-print for horn_ack/led_ack/ir_ack - same four fields
// (duration_ms, gain_pct, clamped, allowed) on all three, per rule_gate.h's
// common contract. Prints the full ack, not just allowed/clamped, per
// KNOWN_GAPS.md's note that a bare bool is too lossy to bench-verify against.
template <typename Ack>
void print_ack(const char *label, const Ack &ack) {
  Serial.print("[firetest] ");
  Serial.print(label);
  Serial.print(" allowed=");
  Serial.print(ack.allowed);
  Serial.print(" duration_ms=");
  Serial.print(ack.duration_ms);
  Serial.print(" gain_pct=");
  Serial.print(ack.gain_pct);
  Serial.print(" clamped=");
  Serial.println(ack.clamped);
}

}  // namespace

fire_test_target fire_test_parse_command(char c) {
  switch (c) {
    case '1':
      return fire_test_target::kHorn;
    case '2':
      return fire_test_target::kLedWingLeft;
    case '3':
      return fire_test_target::kLedWingRight;
    case '4':
      return fire_test_target::kIr;
    case '?':
      return fire_test_target::kHelp;
    default:
      return fire_test_target::kNone;
  }
}

void fire_test_init() { print_menu(); }

void fire_test_service(uint32_t now_ms) {
  if (!Serial.available()) {
    return;
  }

  const char c = static_cast<char>(Serial.read());
  const fire_test_target target = fire_test_parse_command(c);

  // Each branch below blocks for its actuator's resolved duration (see
  // fire_test.h's contract) - acceptable here because this whole harness is
  // bench-only and human-triggered, never compiled into a field build
  // (FIRE_TEST_HARNESS defaults to 0, config.h).
  switch (target) {
    case fire_test_target::kHorn: {
      const horn_request req = {FIRE_TEST_HORN_DURATION_MS, FIRE_TEST_HORN_GAIN_PCT,
                                FIRE_TEST_HORN_TRACK_ID};
      print_ack("horn", drive_horn(req, now_ms));
      break;
    }
    case fire_test_target::kLedWingLeft: {
      // Bench harness always fires the steady pattern - it verifies wiring
      // and polarity, not the ADR 0014 pattern shapes (those are exercised
      // by the host tests, tests/test_led).
      const led_request req = {led_channel::kWingLeft, led_pattern::kSteady,
                                FIRE_TEST_LED_DURATION_MS, FIRE_TEST_LED_GAIN_PCT};
      print_ack("led_wing_left", drive_led(req, now_ms));
      break;
    }
    case fire_test_target::kLedWingRight: {
      const led_request req = {led_channel::kWingRight, led_pattern::kSteady,
                                FIRE_TEST_LED_DURATION_MS, FIRE_TEST_LED_GAIN_PCT};
      print_ack("led_wing_right", drive_led(req, now_ms));
      break;
    }
    case fire_test_target::kIr: {
      const ir_request req = {FIRE_TEST_IR_DURATION_MS, FIRE_TEST_IR_GAIN_PCT};
      print_ack("ir", pulse_ir(req, now_ms));
      break;
    }
    case fire_test_target::kHelp:
    case fire_test_target::kNone:
      print_menu();
      break;
  }
}
