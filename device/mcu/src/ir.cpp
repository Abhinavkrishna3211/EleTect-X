#include "ir.h"

#include "Arduino.h"
#include "rule_gate.h"
#include "config.h"

namespace {

const gate_limits kIrLimits = {
    /*burst_max_ms=*/IR_PULSE_MAX_MS,
    /*cooldown_ms=*/IR_MIN_INTERVAL_MS,
    /*gain_max_pct=*/IR_GAIN_MAX_PCT,
};

uint32_t g_last_fire_ms = 0;
bool g_has_fired_before = false;

uint8_t gain_to_duty(float gain_pct) {
  const float clamped = (gain_pct < 0.0f) ? 0.0f : (gain_pct > 100.0f ? 100.0f : gain_pct);
  return static_cast<uint8_t>((clamped / 100.0f) * 255.0f);
}

}  // namespace

void ir_init() {
  pinMode(IR_ILLUMINATOR_PIN, OUTPUT);
  digitalWrite(IR_ILLUMINATOR_PIN, LOW);
}

ir_ack pulse_ir(ir_request req, uint32_t now_ms) {
  const gate_request gate_req = {req.duration_ms, req.gain_pct};
  const gate_result gate = rule_gate_apply(gate_req, kIrLimits, g_last_fire_ms, now_ms,
                                            g_has_fired_before);

  ir_ack ack{};
  ack.duration_ms = gate.duration_ms;
  ack.gain_pct = gate.gain_pct;
  ack.clamped = gate.clamped;
  ack.allowed = gate.allowed;

  if (!gate.allowed) {
    return ack;
  }

  analogWrite(IR_ILLUMINATOR_PIN, gain_to_duty(gate.gain_pct));
  delay(gate.duration_ms);
  analogWrite(IR_ILLUMINATOR_PIN, 0);

  g_last_fire_ms = now_ms;
  g_has_fired_before = true;
  return ack;
}
