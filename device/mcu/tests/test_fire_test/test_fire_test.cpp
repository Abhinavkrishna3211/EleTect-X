// Known-answer tests for the fire-test harness's pure command parser
// (ENGINEERING_CONVENTIONS.md 4). fire_test_parse_command() is the only
// host-testable piece - fire_test_service()'s actual fire behavior needs
// real hardware, per docs/specs/mcu-fire-test-harness.md.

#include <unity.h>

#include "fire_test.h"

void setUp() {}
void tearDown() {}

static void test_digit_1_maps_to_horn(void) {
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('1') == fire_test_target::kHorn,
                            "'1' must map to kHorn");
}

static void test_digit_2_maps_to_led_white(void) {
  TEST_ASSERT_TRUE_MESSAGE(
      fire_test_parse_command('2') == fire_test_target::kLedWhite,
      "'2' must map to kLedWhite");
}

static void test_digit_3_maps_to_led_blue(void) {
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('3') == fire_test_target::kLedBlue,
                            "'3' must map to kLedBlue");
}

static void test_digit_4_maps_to_ir(void) {
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('4') == fire_test_target::kIr,
                            "'4' must map to kIr");
}

static void test_question_mark_maps_to_help(void) {
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('?') == fire_test_target::kHelp,
                            "'?' must map to kHelp");
}

static void test_unrecognized_byte_maps_to_none(void) {
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('9') == fire_test_target::kNone,
                            "a digit outside 1-4 must map to kNone, not be "
                            "mistaken for a valid target");
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command('x') == fire_test_target::kNone,
                            "an arbitrary letter must map to kNone");
}

static void test_whitespace_and_newline_bytes_map_to_none(void) {
  TEST_ASSERT_TRUE_MESSAGE(
      fire_test_parse_command('\n') == fire_test_target::kNone,
      "a Serial Monitor line-feed terminator must not be mistaken for a "
      "command");
  TEST_ASSERT_TRUE_MESSAGE(
      fire_test_parse_command('\r') == fire_test_target::kNone,
      "a Serial Monitor carriage-return terminator must not be mistaken for "
      "a command");
  TEST_ASSERT_TRUE_MESSAGE(fire_test_parse_command(' ') == fire_test_target::kNone,
                            "a bare space must map to kNone");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_digit_1_maps_to_horn);
  RUN_TEST(test_digit_2_maps_to_led_white);
  RUN_TEST(test_digit_3_maps_to_led_blue);
  RUN_TEST(test_digit_4_maps_to_ir);
  RUN_TEST(test_question_mark_maps_to_help);
  RUN_TEST(test_unrecognized_byte_maps_to_none);
  RUN_TEST(test_whitespace_and_newline_bytes_map_to_none);
  return UNITY_END();
}
