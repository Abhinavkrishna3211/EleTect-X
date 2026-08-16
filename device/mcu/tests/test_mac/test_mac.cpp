// Behavioral tests for mac.cpp's Grove LoRa-E5 OTAA join state machine
// (ENGINEERING_CONVENTIONS.md 4) - covers the "OK"-vs-"+PREFIX" bug fix
// (KNOWN_GAPS.md's "AT command syntax and response strings in lora/mac.cpp"
// entry): kSettingMode/kSettingRegion/kLoadingKey must gate on the module's
// real +MODE:/+DR:/+KEY:-prefixed responses, not the literal substring "OK",
// which those three responses never contain.
//
// mac.cpp talks to real hardware over LORA_SERIAL - this drives it through
// the host HardwareSerial stub's host_feed() (hostshim/HardwareSerial.h),
// scripting each AT response exactly as the real E5 would send it, and
// lora_service()'s own now_ms parameter to control simulated time
// deterministically, same approach as test_geophone's advance_millis() use.
//
// Uses the LORA_SERIAL macro (config.h) rather than hardcoding Serial1, so
// these tests stay correct regardless of which HardwareSerial object
// LORA_SERIAL resolves to (see KNOWN_GAPS.md's open Serial-vs-Serial1
// entry).

#include <unity.h>

#include "Arduino.h"
#include "config.h"
#include "mac.h"

void setUp() {
  hostshim::reset();
  while (LORA_SERIAL.available() > 0) {
    LORA_SERIAL.read();
  }
  lora_init();
}

void tearDown() {}

static void assert_state(lora_join_state expected, const char *msg) {
  TEST_ASSERT_TRUE_MESSAGE(lora_get_state() == expected, msg);
}

// Drives the state machine from a fresh kIdle through valid, scripted
// responses up to (but not including) the response that would leave
// `target` - so a test can feed its own response once there and observe
// just that step's gate, without re-deriving the whole preceding chain.
// Mirrors each state's real AT command/response pairing exactly as mac.cpp
// documents it (manual sections cited in mac.cpp's own comments).
static void drive_to_state(lora_join_state target, uint32_t *t) {
  lora_service(*t);  // kIdle -> kProbing (unconditional, no response needed)
  if (target == lora_join_state::kProbing) return;

  LORA_SERIAL.host_feed("+AT: OK\r\n");
  *t += 10;
  lora_service(*t);  // kProbing -> kReadingDevEui
  if (target == lora_join_state::kReadingDevEui) return;

  LORA_SERIAL.host_feed("+ID: DevEui, 01:23:45:67:89:AB:CD:EF\r\n");
  *t += 10;
  lora_service(*t);  // kReadingDevEui -> kSettingMode
  if (target == lora_join_state::kSettingMode) return;

  LORA_SERIAL.host_feed("+MODE: LWOTAA\r\n");
  *t += 10;
  lora_service(*t);  // kSettingMode -> kSettingRegion
  if (target == lora_join_state::kSettingRegion) return;

  LORA_SERIAL.host_feed("+DR: IN865 DR0 SF12BW125\r\n");
  *t += 10;
  lora_service(*t);  // kSettingRegion -> kSettingAppEui
  if (target == lora_join_state::kSettingAppEui) return;

  LORA_SERIAL.host_feed("+ID: AppEui, 01:23:45:67:89:AB:CD:EF\r\n");
  *t += 10;
  lora_service(*t);  // kSettingAppEui -> kLoadingKey
  if (target == lora_join_state::kLoadingKey) return;

  LORA_SERIAL.host_feed("+KEY: APPKEY 2B7E151628AED2A6ABF7158809CF4F3C\r\n");
  *t += 10;
  lora_service(*t);  // kLoadingKey -> kJoining
}

static void test_happy_path_full_join_sequence(void) {
  uint32_t t = 1000;

  lora_service(t);  // kIdle -> kProbing
  assert_state(lora_join_state::kProbing,
               "kIdle must unconditionally send AT and advance to kProbing "
               "on the very first service() call");

  // "AT" -> "+AT: OK" (manual sec 5, Error Code worked examples) - this is
  // the one real response that DOES contain "OK", so kProbing's bare
  // rx_contains("OK") check is correct here.
  LORA_SERIAL.host_feed("+AT: OK\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kReadingDevEui,
               "kProbing must advance once a line containing \"OK\" arrives");

  // "AT+ID=DevEui" -> "+ID: DevEui, ..." (manual sec 4.3) - any complete
  // line confirms the module replied; DevEUI content is not checked.
  LORA_SERIAL.host_feed("+ID: DevEui, 01:23:45:67:89:AB:CD:EF\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingMode,
               "kReadingDevEui must advance on any complete response line");

  // "AT+MODE=LWOTAA" -> "+MODE: LWOTAA" (manual sec 4.23) - contains no
  // "OK" substring at all.
  LORA_SERIAL.host_feed("+MODE: LWOTAA\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingRegion,
               "kSettingMode must advance on its real +MODE: response");

  // "AT+DR=IN865" -> "+DR: IN865 DR0 ..." (manual sec 4.13.2).
  LORA_SERIAL.host_feed("+DR: IN865 DR0 SF12BW125\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingAppEui,
               "kSettingRegion must advance on its real +DR: response");

  // "AT+ID=AppEui,\"...\"" -> "+ID: AppEui, ..." (manual sec 4.3).
  LORA_SERIAL.host_feed("+ID: AppEui, 01:23:45:67:89:AB:CD:EF\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kLoadingKey,
               "kSettingAppEui must advance on its real +ID: AppEui response");

  // "AT+KEY=APPKEY,\"...\"" -> "+KEY: APPKEY ..." (manual sec 4.20).
  LORA_SERIAL.host_feed("+KEY: APPKEY 2B7E151628AED2A6ABF7158809CF4F3C\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kJoining,
               "kLoadingKey must advance on its real +KEY: response");

  // "AT+JOIN" -> "... +JOIN: Done" (manual sec 4.24 worked example).
  LORA_SERIAL.host_feed("+JOIN: Done\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kJoined,
               "kJoining must reach kJoined on \"+JOIN: Done\"");
  TEST_ASSERT_TRUE_MESSAGE(lora_joined(),
                            "lora_joined() must mirror the kJoined state");
}

// Regression test for the fixed OK-vs-+PREFIX bug: these three steps must
// NOT be fooled by a bare "OK" the way the original code was - each of
// their real E5 responses never contains the substring "OK" at all, so a
// gate that (incorrectly) checked rx_contains("OK") would hang forever
// against real hardware, exactly the bug this session's fix corrected.

static void test_setting_mode_does_not_advance_on_bare_ok(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingMode, &t);
  assert_state(lora_join_state::kSettingMode, "setup: must reach kSettingMode");

  LORA_SERIAL.host_feed("OK\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingMode,
               "a bare \"OK\" must NOT advance kSettingMode - only the real "
               "\"+MODE: LWOTAA\" response may (regression guard for the "
               "OK-vs-+PREFIX bug)");
}

static void test_setting_region_does_not_advance_on_bare_ok(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingRegion, &t);
  assert_state(lora_join_state::kSettingRegion, "setup: must reach kSettingRegion");

  LORA_SERIAL.host_feed("OK\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingRegion,
               "a bare \"OK\" must NOT advance kSettingRegion - only a "
               "\"+DR:\"-prefixed response may (regression guard for the "
               "OK-vs-+PREFIX bug)");
}

static void test_loading_key_does_not_advance_on_bare_ok(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kLoadingKey, &t);
  assert_state(lora_join_state::kLoadingKey, "setup: must reach kLoadingKey");

  LORA_SERIAL.host_feed("OK\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kLoadingKey,
               "a bare \"OK\" must NOT advance kLoadingKey - only a "
               "\"+KEY:\"-prefixed response may (regression guard for the "
               "OK-vs-+PREFIX bug)");
}

static void test_timed_out_step_retries_then_fails_after_max_retries(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingMode, &t);
  assert_state(lora_join_state::kSettingMode, "setup: must reach kSettingMode");

  // No valid response ever arrives. kSettingMode retries in place
  // (enter_failed_or_retry(kSettingMode, ...)) for up to
  // LORA_JOIN_MAX_RETRIES timeouts, staying in kSettingMode each time.
  for (uint8_t retry = 0; retry < LORA_JOIN_MAX_RETRIES; ++retry) {
    t += LORA_AT_TIMEOUT_MS + 1;
    lora_service(t);
    assert_state(lora_join_state::kSettingMode,
                 "a timed-out step within the retry budget must retry in "
                 "place, not give up early");
  }

  // One more timeout exceeds the budget and the machine gives up.
  t += LORA_AT_TIMEOUT_MS + 1;
  lora_service(t);
  assert_state(lora_join_state::kFailed,
               "exceeding LORA_JOIN_MAX_RETRIES must land the machine in "
               "kFailed, not retry forever");
}

static void test_failed_state_backs_off_then_retries_from_idle(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingMode, &t);

  // Drive straight into kFailed, same as the retry-budget test above.
  for (uint8_t retry = 0; retry < LORA_JOIN_MAX_RETRIES + 1; ++retry) {
    t += LORA_AT_TIMEOUT_MS + 1;
    lora_service(t);
  }
  assert_state(lora_join_state::kFailed, "setup: must reach kFailed");

  // Backoff has not elapsed yet - kFailed must hold, not bail out early.
  t += 1;
  lora_service(t);
  assert_state(lora_join_state::kFailed,
               "kFailed must not exit before its own backoff window elapses");

  // A backoff window comfortably larger than any possible
  // LORA_JOIN_BACKOFF_BASE_MS * (retry_count + 1) has now elapsed - the
  // node must not be stranded in kFailed forever.
  t += 10UL * LORA_JOIN_BACKOFF_BASE_MS * (LORA_JOIN_MAX_RETRIES + 1);
  lora_service(t);
  assert_state(lora_join_state::kIdle,
               "kFailed must fall back to kIdle once its backoff window "
               "elapses, so a transient gateway/module issue does not "
               "strand the node without ever probing again");

  // kIdle immediately re-sends "AT" and moves on, same as a cold start -
  // confirms the sequence actually restarts, not just parks in kIdle.
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kProbing,
               "after backoff, the machine must actually restart the join "
               "sequence from the top");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_happy_path_full_join_sequence);
  RUN_TEST(test_setting_mode_does_not_advance_on_bare_ok);
  RUN_TEST(test_setting_region_does_not_advance_on_bare_ok);
  RUN_TEST(test_loading_key_does_not_advance_on_bare_ok);
  RUN_TEST(test_timed_out_step_retries_then_fails_after_max_retries);
  RUN_TEST(test_failed_state_backs_off_then_retries_from_idle);
  return UNITY_END();
}
