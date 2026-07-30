#include "led.h"

#include "Arduino.h"
#include "rule_gate.h"
#include "config.h"

namespace {

const gate_limits kLedLimits = {
    /*burst_max_ms=*/LED_BURST_MAX_MS,
    /*cooldown_ms=*/LED_COOLDOWN_MS,
    /*gain_max_pct=*/LED_GAIN_MAX_PCT,
};

// Independent cooldown state per channel - white and blue must not gate each
// other.
struct channel_state {
  int pin;
  uint32_t last_fire_ms;
  bool has_fired_before;
};

channel_state g_white = {LED_WHITE_PIN, 0, false};
channel_state g_blue = {LED_BLUE_PIN, 0, false};

channel_state &state_for(led_channel channel) {
  return (channel == led_channel::kWhite) ? g_white : g_blue;
}

// gain_pct (0-100) -> analogWrite duty (0-255).
uint8_t gain_to_duty(float gain_pct) {
  const float clamped = (gain_pct < 0.0f) ? 0.0f : (gain_pct > 100.0f ? 100.0f : gain_pct);
  return static_cast<uint8_t>((clamped / 100.0f) * 255.0f);
}

}  // namespace

void led_init() {
  pinMode(LED_WHITE_PIN, OUTPUT);
  pinMode(LED_BLUE_PIN, OUTPUT);
  digitalWrite(LED_WHITE_PIN, LOW);
  digitalWrite(LED_BLUE_PIN, LOW);
}

led_ack drive_led(led_request req, uint32_t now_ms) {
  channel_state &state = state_for(req.channel);

  const gate_request gate_req = {req.duration_ms, req.gain_pct};
  const gate_result gate = rule_gate_apply(gate_req, kLedLimits, state.last_fire_ms,
                                            now_ms, state.has_fired_before);

  led_ack ack{};
  ack.duration_ms = gate.duration_ms;
  ack.gain_pct = gate.gain_pct;
  ack.clamped = gate.clamped;
  ack.allowed = gate.allowed;

  if (!gate.allowed) {
    return ack;
  }

  analogWrite(state.pin, gain_to_duty(gate.gain_pct));
  delay(gate.duration_ms);
  analogWrite(state.pin, 0);

  state.last_fire_ms = now_ms;
  state.has_fired_before = true;
  return ack;
}
