#include "bridge_handlers.h"

#include "Arduino.h"
#include "config.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"

namespace {

void log_schema_mismatch(const char *fn, uint8_t got) {
  Serial.print("[bridge] ");
  Serial.print(fn);
  Serial.print(" schema_version mismatch: got ");
  Serial.print(got);
  Serial.print(" expected ");
  Serial.println(BRIDGE_SCHEMA_VERSION);
}

}  // namespace

led_channel led_channel_from_wire(uint8_t channel) {
  // channel 0 = left wing, 1 = right wing, 2 = both wings (schema_version 3,
  // ADR 0014 E - value 2 was the left-wing fallback before that). Its own
  // wire field since ADR 0014 (schema_version 2); before that it was
  // overloaded onto pattern_id.
  switch (channel) {
    case 1:
      return led_channel::kWingRight;
    case 2:
      return led_channel::kWingBoth;
    case 0:
    default:
      return led_channel::kWingLeft;
  }
}

bool bridge_drive_horn(uint8_t schema_version, float gain_pct, uint16_t duration_ms) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("drive_horn", schema_version);
  }
  const horn_request req = {duration_ms, gain_pct};
  return drive_horn(req, millis()).allowed;
}

bool bridge_drive_led(uint8_t schema_version, uint8_t channel, uint8_t pattern_id,
                      float gain_pct, uint16_t duration_ms) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("drive_led", schema_version);
  }
  const led_request req = {led_channel_from_wire(channel), led_pattern_from_id(pattern_id),
                            duration_ms, gain_pct};
  return drive_led(req, millis()).allowed;
}

bool bridge_pulse_ir(uint8_t schema_version, uint16_t duration_ms) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("pulse_ir", schema_version);
  }
  const ir_request req = {duration_ms, IR_GAIN_MAX_PCT};
  return pulse_ir(req, millis()).allowed;
}

bridge_system_state bridge_get_system_state(uint8_t schema_version) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("get_system_state", schema_version);
  }
  bridge_system_state state;
  // No battery-monitor driver or ADC pin exists yet (config.h has no
  // BATTERY_ADC_PIN) - 0.0 is an honest "unknown" sentinel, not a
  // fabricated reading. See docs/KNOWN_GAPS.md.
  state.battery_v = 0.0f;
  state.geophone_ok = geophone_ok();
  // No acoustic subsystem exists on this MCU at all yet - always false
  // until one does. See docs/KNOWN_GAPS.md.
  state.acoustic_ok = false;
  state.uptime_s = millis() / 1000UL;
  return state;
}

bool bridge_send_lora_alert(uint8_t schema_version, float confidence, uint32_t capture_ref) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("send_lora_alert", schema_version);
  }
  // No real LoRa transport exists yet - see bridge_handlers.h. Logged, not
  // sent; always acks false.
  Serial.print("[bridge] [SAFE_MODE] would send direct gunshot alert: confidence=");
  Serial.print(confidence, 3);
  Serial.print(" capture_ref=");
  Serial.println(capture_ref);
  return false;
}
