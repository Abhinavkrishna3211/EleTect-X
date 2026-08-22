// Bridge RPC adapter functions - one per MPU->MCU function in
// device/mpu/bridge/schema.md's second table (drive_horn, drive_led,
// pulse_ir, get_system_state, send_lora_alert). Each adapter converts the
// flat scalar Bridge call signature schema.md defines into this file's real
// actuator/sensor calls (horn.h/led.h/ir.h/geophone.h) and back into the
// flat return shape schema.md specifies. Named bridge_* rather than
// reusing the schema names directly: horn.h/led.h/ir.h already define
// drive_horn/drive_led/pulse_ir as the real actuator-struct functions,
// and Bridge.provide()'s registered name (a string, e.g. "drive_horn")
// is decoupled from the C++ symbol bound to it - so the C++ names here
// differ from the wire names on purpose, not by accident.
//
// NOT REGISTERED. device/mcu/src/main.cpp intentionally leaves every
// Bridge.provide() call for these five commented out - see main.cpp's
// own comment and docs/DEVICE_DEVELOPMENT_WORKFLOW.md 3 for why:
// registering an additional Bridge.provide() has broken every
// previously-working one on the same sketch in this project's own
// history, so each of the five below must be enabled and
// hardware-verified one at a time, in a live session with a human
// present, never as a batch. Do not add a Bridge.provide() call for any
// of these outside of that.

#ifndef BRIDGE_HANDLERS_H
#define BRIDGE_HANDLERS_H

#include <cstdint>

#include "led.h"

// Pure mapping from drive_led's wire pattern_id onto this MCU's real LED
// channel enum - host-testable in isolation (tests/test_bridge_handlers),
// same functional-core/imperative-shell split fire_test.cpp's
// fire_test_parse_command() uses (ENGINEERING_CONVENTIONS.md 2).
//
// INVENTED: schema.md's drive_led row carries only pattern_id and
// duration_ms, no gain_pct and no explicit channel selector - neither
// exists in the schema today, so this mapping (0 -> white, 1 -> blue,
// anything else -> white) is a placeholder pending real pattern design,
// not a resolved contract. See docs/KNOWN_GAPS.md.
led_channel led_channel_for_pattern_id(uint8_t pattern_id);

// MPU -> MCU: request a horn deterrence burst (schema.md: drive_horn).
// Precondition: none - a schema_version mismatch is logged, not
// rejected, since this is a synchronous call the MPU is already blocked
// waiting on (services.config.BRIDGE_CALL_TIMEOUT_S) and still needs a
// real ack either way, same reasoning services/reflex_loop.py documents
// for the MCU->MPU direction. Never blocks past drive_horn()'s own
// contract (horn.h): the physical burst duration plus
// HORN_AMP_ENABLE_DELAY_MS, both bounded, not a hardware wait.
//
// Returns: the ack's `allowed` field - true if the horn fired (with any
// out-of-bounds gain_pct/duration_ms clamped by rule_gate_apply(), not
// rejected), false if refused because the horn is still in
// HORN_COOLDOWN_MS. schema.md's drive_horn returns a bare bool, so the
// resolved (possibly clamped) duration_ms/gain_pct the ack also carries
// is not passed back over Bridge - only logged locally. This mirrors
// fire_test.cpp's own print_ack(), the only other place these acks are
// currently surfaced.
bool bridge_drive_horn(uint8_t schema_version, float gain_pct, uint16_t duration_ms);

// MPU -> MCU: request an LED deterrence burst (schema.md: drive_led).
// Same schema_version handling as bridge_drive_horn. Never blocks past
// drive_led()'s own contract (led.h): the resolved duration_ms.
//
// gain_pct is not part of schema.md's drive_led row - this adapter
// requests LED_GAIN_MAX_PCT (config.h) for every call, the same
// "request the protocol/config max, let the existing clamp resolve it"
// placeholder policy device/mpu/services/reflex_loop.py documents for
// its own horn request, rather than inventing a second unreviewed
// mid-range figure. See docs/KNOWN_GAPS.md.
//
// Returns: the ack's `allowed` field, same convention as
// bridge_drive_horn.
bool bridge_drive_led(uint8_t schema_version, uint8_t pattern_id, uint16_t duration_ms);

// MPU -> MCU: request an IR illuminator pulse (schema.md: pulse_ir).
// Same schema_version handling as bridge_drive_horn. Never blocks past
// pulse_ir()'s own contract (ir.h): the resolved duration_ms.
//
// gain_pct is not part of schema.md's pulse_ir row either - this adapter
// requests IR_GAIN_MAX_PCT (config.h) for every call, same "request the
// config max, let the existing clamp resolve it" placeholder policy as
// bridge_drive_led's gain_pct above. See docs/KNOWN_GAPS.md.
//
// Returns: the ack's `allowed` field, same convention as
// bridge_drive_horn.
bool bridge_pulse_ir(uint8_t schema_version, uint16_t duration_ms);

// Flat return shape matching bridge/rpc.py's SystemState dataclass and
// schema.md's get_system_state row, field order identical.
struct bridge_system_state {
  float battery_v;
  bool geophone_ok;
  bool acoustic_ok;
  uint32_t uptime_s;
};

// MPU -> MCU: read cached system state (schema.md: get_system_state).
// Same schema_version handling as bridge_drive_horn. Never blocks past
// one geophone_ok() read and one millis() read - no fresh sensor poll,
// per schema.md's own "cached-struct read" contract.
//
// battery_v and acoustic_ok are honest placeholders, not live readings -
// no battery-monitor driver/ADC pin exists in config.h yet, and no
// acoustic subsystem exists on this MCU at all yet. See
// bridge_handlers.cpp and docs/KNOWN_GAPS.md.
bridge_system_state bridge_get_system_state(uint8_t schema_version);

// MPU -> MCU: request a direct gunshot alert uplink (schema.md:
// send_lora_alert, ADR 0007 5's anti-poaching path). Same schema_version
// handling as bridge_drive_horn.
//
// STUB: no real LoRa transport exists yet - the Grove E5 module does not
// join (mac.h exposes only lora_init()/lora_service()/lora_get_state()/
// lora_joined(), no uplink-send primitive; see docs/KNOWN_GAPS.md's 18 Aug
// entry). This handler only logs the request and always returns false -
// ack therefore means "queued/logged", never "delivered", until a real
// uplink exists. Never touches mac.cpp.
bool bridge_send_lora_alert(uint8_t schema_version, float confidence, uint32_t capture_ref);

#endif  // BRIDGE_HANDLERS_H
