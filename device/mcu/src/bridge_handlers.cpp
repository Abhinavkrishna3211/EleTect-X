#include "bridge_handlers.h"

#include "Arduino.h"
#include "config.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "mac.h"

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

bool bridge_drive_horn(uint8_t schema_version, float gain_pct, uint16_t duration_ms,
                       uint8_t track_id) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("drive_horn", schema_version);
  }
  const horn_request req = {duration_ms, gain_pct, track_id};
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

bool bridge_send_lora_event(uint8_t schema_version, uint8_t event_class, float confidence,
                            uint8_t tier, uint8_t flags, uint32_t capture_ref) {
  if (schema_version != BRIDGE_SCHEMA_VERSION) {
    log_schema_mismatch("send_lora_event", schema_version);
  }
#if LORA_ENABLED
  uplink_event ev{};
  ev.event_class = event_class;
  ev.confidence = confidence;
  ev.tier = tier;
  ev.flags = flags;
  ev.capture_ref = capture_ref;
  return lora_queue_event(ev);
#else
  (void)event_class;
  (void)confidence;
  (void)tier;
  (void)flags;
  (void)capture_ref;
  return false;
#endif
}
