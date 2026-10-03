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
  // The trailing FF FF is the age field left unset: the encoder has no clock,
  // and mac.cpp stamps it at transmit.
  const uint8_t expected[] = {0x12, 0x05, 0x01, 0x57, 0x02, 0x03,
                              0x01, 0x02, 0x03, 0x04, 0xFF, 0xFF};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, sizeof(expected));
}

static void test_set_event_age(void) {
  uplink_event ev{};
  ev.event_class = static_cast<uint8_t>(uplink_event_class::kElephant);
  uint8_t out[UPLINK_EVENT_LEN];
  uplink_encode_event(ev, 1, out, sizeof(out));

  TEST_ASSERT_TRUE(uplink_set_event_age(out, UPLINK_EVENT_LEN, 3600));
  TEST_ASSERT_EQUAL_HEX8(0x0E, out[10]);
  TEST_ASSERT_EQUAL_HEX8(0x10, out[11]);

  // Zero is a real age, not "unset".
  TEST_ASSERT_TRUE(uplink_set_event_age(out, UPLINK_EVENT_LEN, 0));
  TEST_ASSERT_EQUAL_HEX8(0x00, out[10]);
  TEST_ASSERT_EQUAL_HEX8(0x00, out[11]);

  // Saturates rather than wrapping: a frame stuck for a week must not report
  // itself as fresh.
  TEST_ASSERT_TRUE(uplink_set_event_age(out, UPLINK_EVENT_LEN, 999999u));
  TEST_ASSERT_EQUAL_HEX8(0xFF, out[10]);
  TEST_ASSERT_EQUAL_HEX8(0xFE, out[11]);

  // Only full-length event frames have the field.
  uplink_status st{};
  uint8_t stat[UPLINK_STATUS_LEN];
  uplink_encode_status(st, 1, stat, sizeof(stat));
  TEST_ASSERT_FALSE(uplink_set_event_age(stat, UPLINK_STATUS_LEN, 10));
  TEST_ASSERT_FALSE(uplink_set_event_age(out, UPLINK_EVENT_LEN - 1, 10));
  TEST_ASSERT_FALSE(uplink_set_event_age(nullptr, UPLINK_EVENT_LEN, 10));
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

static void test_no_retreat_event_known_answer(void) {
  // The classes and the flag appended for ADR 0034: fox as a deterrence
  // target, and "fired the top tier and the animal stayed". Pinned as its
  // own vector rather than folded into the one above, because the byte the
  // server keys "send a person" off is worth failing on by itself.
  uplink_event ev{};
  ev.event_class = static_cast<uint8_t>(uplink_event_class::kFox);
  ev.confidence = 0.50f;
  ev.tier = 3;
  ev.flags = UPLINK_EVENT_FLAG_VISION_CONFIRMED | UPLINK_EVENT_FLAG_DETERRENT_FIRED |
             UPLINK_EVENT_FLAG_NO_RETREAT;
  ev.capture_ref = 0u;

  uint8_t out[UPLINK_EVENT_LEN];
  TEST_ASSERT_EQUAL_UINT(UPLINK_EVENT_LEN, uplink_encode_event(ev, 7, out, sizeof(out)));
  const uint8_t expected[] = {0x12, 0x07, 0x06, 0x32, 0x03, 0x0B,
                              0x00, 0x00, 0x00, 0x00, 0xFF, 0xFF};
  TEST_ASSERT_EQUAL_HEX8_ARRAY(expected, out, sizeof(expected));
}

static void test_every_named_class_survives_encoding(void) {
  // UPLINK_EVENT_CLASS_MAX is the only thing stopping a new class from
  // being silently flattened to kUnconfirmed, and it is a #define sitting
  // several lines away from the enum it bounds. This is what notices when
  // the next class is appended and the bound is not raised with it.
  const uplink_event_class classes[] = {
      uplink_event_class::kUnconfirmed, uplink_event_class::kElephant,
      uplink_event_class::kBoar,        uplink_event_class::kGunshot,
      uplink_event_class::kChainsaw,    uplink_event_class::kElephantCall,
      uplink_event_class::kFox,
  };
  for (uplink_event_class value : classes) {
    uplink_event ev{};
    ev.event_class = static_cast<uint8_t>(value);
    uint8_t out[UPLINK_EVENT_LEN];
    uplink_encode_event(ev, 0, out, sizeof(out));
    TEST_ASSERT_EQUAL_UINT8_MESSAGE(static_cast<uint8_t>(value), out[2],
                                    "a named class must not flatten to kUnconfirmed");
  }
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
  RUN_TEST(test_no_retreat_event_known_answer);
  RUN_TEST(test_set_event_age);
  RUN_TEST(test_every_named_class_survives_encoding);
  RUN_TEST(test_status_known_answer);
  RUN_TEST(test_status_unknown_battery);
  RUN_TEST(test_event_fields_are_clamped);
  RUN_TEST(test_short_buffer_is_refused);
  RUN_TEST(test_at_command_rendering);
  return UNITY_END();
}
