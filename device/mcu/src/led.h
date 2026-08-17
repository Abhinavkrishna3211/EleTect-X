// Deterrent LED pod driver - drives LED_WHITE_PIN and LED_BLUE_PIN through
// the shared rule-gate clamp/cooldown core (rule_gate.h).

#ifndef ACTUATORS_LED_H
#define ACTUATORS_LED_H

#include <cstdint>

enum class led_channel { kWhite, kBlue };

struct led_request {
  led_channel channel;
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

// Drives the requested channel for the resolved duration at the resolved
// gain, subject to that channel's own independent cooldown counter (white
// and blue deter separately - one firing must not gate the other). Blocks
// for the resolved duration_ms (analogWrite then delay then off) - the
// reflex loop calling this must expect that, same caveat as horn.h's
// drive_horn.
led_ack drive_led(led_request req, uint32_t now_ms);

#endif  // ACTUATORS_LED_H
