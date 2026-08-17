// IR illuminator driver - drives IR_ILLUMINATOR_PIN for night-vision capture,
// through the shared rule-gate clamp/cooldown core (rule_gate.h).
//
// IR_MIN_INTERVAL_MS enforces the MOSFET's duty-cycle thermal limit
// (config.h) - it is passed to rule_gate.h as the cooldown, reusing the same
// clamp-and-ack contract the other actuators use.

#ifndef ACTUATORS_IR_H
#define ACTUATORS_IR_H

#include <cstdint>

struct ir_request {
  uint16_t duration_ms;
  float gain_pct;
};

struct ir_ack {
  uint16_t duration_ms;
  float gain_pct;
  bool clamped;
  bool allowed;
};

// One-time setup: configures IR_ILLUMINATOR_PIN as a PWM output, off.
void ir_init();

// Pulses the illuminator for the resolved duration at the resolved gain,
// subject to IR_MIN_INTERVAL_MS between pulses. Blocks for the resolved
// duration_ms (analogWrite then delay then off) - the reflex loop calling
// this must expect that, same caveat as horn.h's drive_horn.
ir_ack pulse_ir(ir_request req, uint32_t now_ms);

#endif  // ACTUATORS_IR_H
