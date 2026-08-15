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
// device/mpu/bridge/schema.md's MCU-side handlers (drive_horn, drive_led,
// pulse_ir, geophone_ok) still are not registered with Bridge.provide() -
// see docs/KNOWN_GAPS.md for why that is deliberately deferred to a
// hardware session. Bridge.begin()/Bridge.update() running unconditionally
// does not change that discipline: it makes the notify direction reachable,
// it does not register any provide() handler.

#include "Arduino.h"
#include "Arduino_RouterBridge.h"
#include "config.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "mac.h"
#include "state_machine.h"

void setup() {
  Serial.begin(CONSOLE_BAUD);

  Bridge.begin();

  geophone_init();
  horn_init();
  led_init();
  ir_init();
  lora_init();
  state_machine_init();
}

void loop() {
  const uint32_t now_ms = millis();

  Bridge.update();

  // Serviced every iteration regardless of reflex state: the geophone ring
  // buffer must keep filling even while the state machine sits in EVENT or
  // COOLDOWN, and the LoRa join state machine must keep advancing
  // independently of sensing.
  geophone_service();
  lora_service(now_ms);

  state_machine_tick(now_ms);
}
