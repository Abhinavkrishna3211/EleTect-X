// setup()/loop() shell wiring the reflex-layer subsystems together.
// Bridge.begin()/Bridge.update() are unconditional, production
// infrastructure as of 2026-08-14 - not gated behind SEISMIC_DEBUG_STREAM_RAW
// the way they used to be. That flag still exists and still gates its own
// bench-only raw-sample relay (geophone.cpp), but Bridge itself is no
// longer bench-only: state_machine.cpp's kSensing case needs a real
// Bridge.notify("report_footfall_event", ...) reachable in every field
// build, or every trigger goes right back to producing a bare console
// timestamp and nothing else (docs/KNOWN_GAPS.md's high-severity
// "Raw seismic trigger data does not reach the MPU" entry, 14 Aug). This is
// the resolution to the decision this file's own comment used to defer -
// "decide how the gate should really read once an actuator RPC goes live" -
// see docs/KNOWN_GAPS.md for the full writeup.
//
// device/mpu/bridge/schema.md's MPU->MCU handlers (drive_horn, drive_led,
// pulse_ir, get_system_state, send_lora_alert) have real adapters in
// bridge_handlers.cpp. drive_led and pulse_ir were registered in earlier
// hardware sessions; drive_horn joined them this session (HOME_TEST_MODE
// plan prerequisite 2). get_system_state/send_lora_alert stay deliberately
// commented out - see docs/KNOWN_GAPS.md for why that is deferred to a
// hardware session, one function at a time. Bridge.begin()/Bridge.update()
// running unconditionally does not change that discipline: it makes the
// notify direction reachable, it does not register any provide() handler.

#include "Arduino.h"
#include "Arduino_RouterBridge.h"
#include "bridge_handlers.h"
#include "config.h"
#include "fire_test.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "mac.h"
#include "state_machine.h"

void setup() {
  Serial.begin(CONSOLE_BAUD);

#if HOME_TEST_MODE
  // Loud on purpose - see config.h's HOME_TEST_MODE comment. This line must
  // be the first thing a human sees when opening the console, because the
  // one failure mode this exists to prevent is a board shipped to the field
  // with this flag still on.
  Serial.println("[mode] *** HOME_TEST_MODE - BACKYARD TEST BUILD - NOT FOR FIELD DEPLOYMENT ***");
#else
  Serial.println("[mode] field build (HOME_TEST_MODE=0)");
#endif

  Bridge.begin();

  // get_system_state/send_lora_alert below are NOT REGISTERED - see
  // bridge_handlers.h and docs/KNOWN_GAPS.md. Each line wires one MPU->MCU
  // function from device/mpu/bridge/schema.md to its adapter in
  // bridge_handlers.cpp.
  // docs/DEVICE_DEVELOPMENT_WORKFLOW.md 3 / ENGINEERING_CONVENTIONS.md 8:
  // registering an additional Bridge.provide() has broken every
  // previously-working one on the same sketch in this project's own
  // history - uncomment exactly ONE line per hardware session, flash,
  // and confirm every already-registered function (including
  // debug_stream_raw_seismic_sample, geophone.cpp) still works before
  // uncommenting the next. Never uncomment more than one at a time, and
  // never as part of a routine sync-to-board.sh push.
  //
  // drive_horn registered this session (HOME_TEST_MODE plan prerequisite 2),
  // source-level only - this line was uncommented and pushed to the board's
  // on-disk sketch/ tree, but the flash-and-verify step this discipline
  // requires (arduino-app-cli app restart, then confirm drive_led/pulse_ir
  // still work) never ran; it was interrupted before any reflash happened.
  // See HANDOVER.md's 6 Sept section and docs/KNOWN_GAPS.md for the exact
  // stopping point - do not treat this registration as hardware-verified
  // until that gate actually runs. Bridge.begin()/Bridge.update() are
  // unconditional now (see this file's top comment), so that is no longer
  // what gates these four - only the one-at-a-time hardware-verification
  // discipline above does.
  Bridge.provide("drive_horn", bridge_drive_horn);
  Bridge.provide("drive_led", bridge_drive_led);
  Bridge.provide("pulse_ir", bridge_pulse_ir);
  // Bridge.provide("get_system_state", bridge_get_system_state);
  // Bridge.provide("send_lora_alert", bridge_send_lora_alert);

#if FIRE_TEST_HARNESS
  fire_test_init();
#endif

  geophone_init();
  horn_init();
  led_init();
  ir_init();
#if LORA_ENABLED
  lora_init();
#endif
  state_machine_init();
}

void loop() {
  const uint32_t now_ms = millis();

  Bridge.update();

#if FIRE_TEST_HARNESS
  fire_test_service(now_ms);
#endif

  // Serviced every iteration regardless of reflex state: the geophone ring
  // buffer must keep filling even while the state machine sits in EVENT or
  // COOLDOWN, and the LoRa join state machine must keep advancing
  // independently of sensing.
  geophone_service();
#if LORA_ENABLED
  lora_service(now_ms);
#endif

  state_machine_tick(now_ms);
}
