// Known-answer tests for bridge_handlers.cpp's one pure piece,
// led_channel_from_wire() (ENGINEERING_CONVENTIONS.md 4), plus
// bridge_send_lora_alert(). The other four bridge_* adapters call real
// actuator/sensor code (drive_horn/drive_led/pulse_ir/geophone_ok) already
// covered by their own drivers and rule_gate's tests; they are not
// registered with Bridge.provide() anywhere (see bridge_handlers.h), so
// there is no live wire input to test them against yet, host or hardware.
// bridge_send_lora_alert has no such underlying driver to defer to - it is
// pure logging plus an unconditional false - so it is tested directly here.
//
// bridge_drive_horn gets one thin test too: not its gating (that is
// rule_gate's and test_horn's) but its schema_version-4 signature - the
// trailing track_id arg added by ADR 0015 - so a future arg reorder or drop
// fails here rather than silently at the wire.

#include <unity.h>

#include "Arduino.h"
#include "bridge_handlers.h"
#include "config.h"
#include "horn.h"
#include "led.h"

void setUp() { hostshim::reset(); }
void tearDown() {}

static void test_channel_0_maps_to_wing_left(void) {
  TEST_ASSERT_TRUE_MESSAGE(led_channel_from_wire(0) == led_channel::kWingLeft,
                            "wire channel 0 must map to kWingLeft");
}

static void test_channel_1_maps_to_wing_right(void) {
  TEST_ASSERT_TRUE_MESSAGE(led_channel_from_wire(1) == led_channel::kWingRight,
                            "wire channel 1 must map to kWingRight");
}

static void test_channel_2_maps_to_wing_both(void) {
  TEST_ASSERT_TRUE_MESSAGE(led_channel_from_wire(2) == led_channel::kWingBoth,
                            "wire channel 2 must map to kWingBoth (schema_version 3, ADR 0014 E)");
}

static void test_unrecognized_channel_maps_to_wing_left(void) {
  TEST_ASSERT_TRUE_MESSAGE(
      led_channel_from_wire(3) == led_channel::kWingLeft,
      "an undefined channel must fall back to kWingLeft, not be mistaken for another wing");
  TEST_ASSERT_TRUE_MESSAGE(
      led_channel_from_wire(255) == led_channel::kWingLeft,
      "the max uint8_t channel must also fall back to kWingLeft");
}

static void test_send_lora_alert_always_acks_false(void) {
  TEST_ASSERT_FALSE_MESSAGE(bridge_send_lora_alert(4, 0.9f, 42),
                             "no real transport exists yet - ack must always be false");
}

static void test_drive_horn_forwards_track_id_and_fires_then_cools_down(void) {
  horn_init();

  // schema 4 signature: (schema_version, gain_pct, duration_ms, track_id).
  const bool first =
      bridge_drive_horn(BRIDGE_SCHEMA_VERSION, /*gain_pct=*/45.0f,
                        /*duration_ms=*/500, /*track_id=*/2);
  TEST_ASSERT_TRUE_MESSAGE(first, "a first in-bounds horn request must fire");

  // Immediately re-firing is inside HORN_COOLDOWN_MS - the ack must be false.
  const bool second =
      bridge_drive_horn(BRIDGE_SCHEMA_VERSION, /*gain_pct=*/45.0f,
                        /*duration_ms=*/500, /*track_id=*/2);
  TEST_ASSERT_FALSE_MESSAGE(second,
                            "a re-fire within HORN_COOLDOWN_MS must be refused");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_channel_0_maps_to_wing_left);
  RUN_TEST(test_channel_1_maps_to_wing_right);
  RUN_TEST(test_channel_2_maps_to_wing_both);
  RUN_TEST(test_unrecognized_channel_maps_to_wing_left);
  RUN_TEST(test_send_lora_alert_always_acks_false);
  RUN_TEST(test_drive_horn_forwards_track_id_and_fires_then_cools_down);
  return UNITY_END();
}
