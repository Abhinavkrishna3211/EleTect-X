// Known-answer tests for bridge_handlers.cpp's one pure piece,
// led_channel_from_wire() (ENGINEERING_CONVENTIONS.md 4), plus
// bridge_send_lora_alert(). The other four bridge_* adapters call real
// actuator/sensor code (drive_horn/drive_led/pulse_ir/geophone_ok) already
// covered by their own drivers and rule_gate's tests; they are not
// registered with Bridge.provide() anywhere (see bridge_handlers.h), so
// there is no live wire input to test them against yet, host or hardware.
// bridge_send_lora_alert has no such underlying driver to defer to - it is
// pure logging plus an unconditional false - so it is tested directly here.

#include <unity.h>

#include "bridge_handlers.h"
#include "led.h"

void setUp() {}
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
  TEST_ASSERT_FALSE_MESSAGE(bridge_send_lora_alert(3, 0.9f, 42),
                             "no real transport exists yet - ack must always be false");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_channel_0_maps_to_wing_left);
  RUN_TEST(test_channel_1_maps_to_wing_right);
  RUN_TEST(test_channel_2_maps_to_wing_both);
  RUN_TEST(test_unrecognized_channel_maps_to_wing_left);
  RUN_TEST(test_send_lora_alert_always_acks_false);
  return UNITY_END();
}
