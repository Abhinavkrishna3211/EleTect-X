// Known-answer tests for bridge_handlers.cpp's one pure piece,
// led_channel_for_pattern_id() (ENGINEERING_CONVENTIONS.md 4), plus
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

static void test_pattern_id_0_maps_to_white(void) {
  TEST_ASSERT_TRUE_MESSAGE(led_channel_for_pattern_id(0) == led_channel::kWhite,
                            "pattern_id 0 must map to kWhite");
}

static void test_pattern_id_1_maps_to_blue(void) {
  TEST_ASSERT_TRUE_MESSAGE(led_channel_for_pattern_id(1) == led_channel::kBlue,
                            "pattern_id 1 must map to kBlue");
}

static void test_unrecognized_pattern_id_maps_to_white(void) {
  TEST_ASSERT_TRUE_MESSAGE(
      led_channel_for_pattern_id(2) == led_channel::kWhite,
      "an undefined pattern_id must fall back to kWhite, not be mistaken for kBlue");
  TEST_ASSERT_TRUE_MESSAGE(
      led_channel_for_pattern_id(255) == led_channel::kWhite,
      "the max uint8_t pattern_id must also fall back to kWhite");
}

static void test_send_lora_alert_always_acks_false(void) {
  TEST_ASSERT_FALSE_MESSAGE(bridge_send_lora_alert(1, 0.9f, 42),
                             "no real transport exists yet - ack must always be false");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_pattern_id_0_maps_to_white);
  RUN_TEST(test_pattern_id_1_maps_to_blue);
  RUN_TEST(test_unrecognized_pattern_id_maps_to_white);
  RUN_TEST(test_send_lora_alert_always_acks_false);
  return UNITY_END();
}
