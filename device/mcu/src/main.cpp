// setup()/loop() shell wiring the reflex-layer subsystems together. No
// Bridge wiring here - device/mpu/bridge/schema.md's MCU-side handlers exist
// as callable functions (drive_horn, drive_led, pulse_ir, geophone_ok) but
// are not yet registered with Bridge.provide() - see docs/KNOWN_GAPS.md for
// why that is deliberately deferred to a hardware session.

#include "Arduino.h"
#include "config.h"
#include "geophone.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "mac.h"
#include "state_machine.h"

void setup() {
  Serial.begin(CONSOLE_BAUD);

  geophone_init();
  horn_init();
  led_init();
  ir_init();
  lora_init();
  state_machine_init();
}

void loop() {
  const uint32_t now_ms = millis();

  // Serviced every iteration regardless of reflex state: the geophone ring
  // buffer must keep filling even while the state machine sits in EVENT or
  // COOLDOWN, and the LoRa join state machine must keep advancing
  // independently of sensing.
  geophone_service();
  lora_service(now_ms);

  state_machine_tick(now_ms);
}
