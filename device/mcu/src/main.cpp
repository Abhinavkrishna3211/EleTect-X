// setup()/loop() shell wiring the reflex-layer subsystems together. No
// production Bridge wiring here - device/mpu/bridge/schema.md's MCU-side
// handlers exist as callable functions (drive_horn, drive_led, pulse_ir,
// geophone_ok) but are not yet registered with Bridge.provide() - see
// docs/KNOWN_GAPS.md for why that is deliberately deferred to a hardware
// session. The Bridge.begin()/Bridge.update() calls below exist only to
// support SEISMIC_DEBUG_STREAM_RAW's bench-only Bridge.notify() path
// (geophone.cpp) and are compiled out entirely at flag=0, so this carve-out
// never reaches the field build.

#include "Arduino.h"
#include "config.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "mac.h"
#include "state_machine.h"

#if SEISMIC_DEBUG_STREAM_RAW
#include "Arduino_RouterBridge.h"
#endif

void setup() {
  Serial.begin(CONSOLE_BAUD);

#if SEISMIC_DEBUG_STREAM_RAW
  Bridge.begin();
#endif

  geophone_init();
  horn_init();
  led_init();
  ir_init();
  lora_init();
  state_machine_init();
}

void loop() {
  const uint32_t now_ms = millis();

#if SEISMIC_DEBUG_STREAM_RAW
  Bridge.update();
#endif

  // Serviced every iteration regardless of reflex state: the geophone ring
  // buffer must keep filling even while the state machine sits in EVENT or
  // COOLDOWN, and the LoRa join state machine must keep advancing
  // independently of sensing.
  geophone_service();
  lora_service(now_ms);

  state_machine_tick(now_ms);
}
