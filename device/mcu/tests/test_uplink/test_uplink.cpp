// Known-answer tests for uplink.cpp's payload encoders (ADR 0031). The same
// vectors are checked by the ingest decoder's tests
// (web/ingest/src/payload.test.ts), so a change to the byte layout has to
// break both sides at once.

#include <unity.h>

#include <cmath>
#include <cstring>

#include "uplink.h"

void setUp() {}

void tearDown() {}

static void test_event_known_answer(void) {
  uplink_event ev{};
  ev.event_class = static_cast<uint8_t>(uplink_event_class::kElephant);
  ev.confidence = 0.87f;
  ev.tier = 2;
  ev.flags = UPLINK_EVENT_FLAG_VISION_CONFIRMED | UPLINK_EVENT_FLAG_DETERRENT_FIRED;
  ev.capture_ref = 0x01020304u;

  uint8_t out[UPLINK_EVENT_LEN];
  TEST_ASSERT_EQUAL_UINT(UPLINK_EVENT_LEN, uplink_encode_event(ev, 5, out, sizeof(out)));
  const uint8_t expected[] = {0x12, 0x05, 0x01, 0x57, 0x02, 0x03, 0x01, 0x02, 0x03, 0x04};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, sizeof(expected));
}

static void test_status_known_answer(void) {
  uplink_status st{};
  st.flags = UPLINK_STATUS_FLAG_GEOPHONE_OK | UPLINK_STATUS_FLAG_HOME_TEST;
  st.battery_mv = 3712;
  st.uptime_s = 86400;

  uint8_t out[UPLINK_STATUS_LEN];
  TEST_ASSERT_EQUAL_UINT(UPLINK_STATUS_LEN, uplink_encode_status(st, 200, out, sizeof(out)));
  const uint8_t expected[] = {0x11, 0xC8, 0x03, 0x0E, 0x80, 0x00, 0x01, 0x51, 0x80};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, sizeof(expected));
}

static void test_status_unknown_battery(void) {
  uplink_status st{};
  st.battery_mv = UPLINK_BATTERY_UNKNOWN;
  uint8_t out[UPLINK_STATUS_LEN];
  uplink_encode_status(st, 0, out, sizeof(out));
  TEST_ASSERT_EQUAL_HEX8(0xFF, out[3]);
  TEST_ASSERT_EQUAL_HEX8(0xFF, out[4]);
}

static void test_event_fields_are_clamped(void) {
  uplink_event ev{};
  ev.event_class = 42;
  ev.confidence = 1.7f;
  ev.tier = 9;
  uint8_t out[UPLINK_EVENT_LEN];
  uplink_encode_event(ev, 0, out, sizeof(out));
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, out[2], "an unknown class goes out as unconfirmed");
  TEST_ASSERT_EQUAL_UINT8(100, out[3]);
  TEST_ASSERT_EQUAL_UINT8(3, out[4]);

  ev.confidence = -0.2f;
  uplink_encode_event(ev, 0, out, sizeof(out));
  TEST_ASSERT_EQUAL_UINT8(0, out[3]);

  ev.confidence = std::nanf("");
  uplink_encode_event(ev, 0, out, sizeof(out));
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(0, out[3], "NaN confidence must not become a number");

  ev.confidence = 0.005f;
  uplink_encode_event(ev, 0, out, sizeof(out));
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(1, out[3], "confidence rounds, not truncates");
}

static void test_short_buffer_is_refused(void) {
  uplink_event ev{};
  uplink_status st{};
  uint8_t out[UPLINK_EVENT_LEN];
  TEST_ASSERT_EQUAL_UINT(0, uplink_encode_event(ev, 0, out, UPLINK_EVENT_LEN - 1));
  TEST_ASSERT_EQUAL_UINT(0, uplink_encode_status(st, 0, out, UPLINK_STATUS_LEN - 1));
  TEST_ASSERT_EQUAL_UINT(0, uplink_encode_event(ev, 0, nullptr, UPLINK_EVENT_LEN));
}

static void test_at_command_rendering(void) {
  const uint8_t payload[] = {0x12, 0x00, 0xAB};
  char out[32];
  TEST_ASSERT_TRUE(uplink_at_command(payload, sizeof(payload), true, out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("AT+CMSGHEX=\"1200AB\"", out);
  TEST_ASSERT_TRUE(uplink_at_command(payload, sizeof(payload), false, out, sizeof(out)));
  TEST_ASSERT_EQUAL_STRING("AT+MSGHEX=\"1200AB\"", out);

  // "AT+MSGHEX=\"" (11) + 6 hex + closing quote + NUL = 19; one short is
  // refused.
  TEST_ASSERT_TRUE(uplink_at_command(payload, sizeof(payload), false, out, 19));
  TEST_ASSERT_FALSE(uplink_at_command(payload, sizeof(payload), false, out, 18));
  TEST_ASSERT_FALSE(uplink_at_command(payload, 0, false, out, sizeof(out)));
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_event_known_answer);
  RUN_TEST(test_status_known_answer);
  RUN_TEST(test_status_unknown_battery);
  RUN_TEST(test_event_fields_are_clamped);
  RUN_TEST(test_short_buffer_is_refused);
  RUN_TEST(test_at_command_rendering);
  return UNITY_END();
}
