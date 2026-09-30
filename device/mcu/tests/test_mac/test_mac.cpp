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

#include <cstring>

#include "Arduino.h"
#include "config.h"
#include "mac.h"
#include "uart_share.h"

void setUp() {
  hostshim::reset();
  while (LORA_SERIAL.available() > 0) {
    LORA_SERIAL.read();
  }
  uart_share_init();
  lora_init();
  lora_set_status_source(nullptr);
  LORA_SERIAL.host_reset_tx();
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
  lora_service(*t);  // kLoadingKey -> kSettingPort
  if (target == lora_join_state::kSettingPort) return;

  LORA_SERIAL.host_feed("+PORT: 10\r\n");
  *t += 10;
  lora_service(*t);  // kSettingPort -> kJoining
}

// Drives a fresh machine all the way to kJoined.
static void drive_to_joined(uint32_t *t) {
  drive_to_state(lora_join_state::kJoining, t);
  LORA_SERIAL.host_feed("+JOIN: Done\r\n");
  *t += 10;
  lora_service(*t);
}

// Services the machine once per fed line, a few extra times over, so a
// multi-line reply is fully consumed.
static void service_lines(uint32_t *t, int calls) {
  for (int i = 0; i < calls; ++i) {
    *t += 10;
    lora_service(*t);
  }
}

static bool tx_contains(const char *needle) {
  return std::strstr(LORA_SERIAL.host_tx(), needle) != nullptr;
}

static uplink_event sample_event() {
  uplink_event ev{};
  ev.event_class = static_cast<uint8_t>(uplink_event_class::kElephant);
  ev.confidence = 0.87f;
  ev.tier = 2;
  ev.flags = UPLINK_EVENT_FLAG_VISION_CONFIRMED | UPLINK_EVENT_FLAG_DETERRENT_FIRED;
  ev.capture_ref = 0x01020304u;
  return ev;
}

// sample_event() with seq 0, as uplink_at_command() renders it.
static const char kSampleEventCmd[] = "AT+CMSGHEX=\"12000157020301020304\"";

static uplink_status sample_status(uint32_t now_ms) {
  uplink_status st{};
  st.flags = UPLINK_STATUS_FLAG_GEOPHONE_OK;
  st.battery_mv = UPLINK_BATTERY_UNKNOWN;
  st.uptime_s = now_ms / 1000u;
  return st;
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

  // "AT+ID=DevEui" -> "+ID: DevEui, ..." (manual sec 4.3) - the value
  // itself is not checked.
  LORA_SERIAL.host_feed("+ID: DevEui, 01:23:45:67:89:AB:CD:EF\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSettingMode,
               "kReadingDevEui must advance on its +ID: DevEui response");

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
  assert_state(lora_join_state::kSettingPort,
               "kLoadingKey must advance on its real +KEY: response");

  // "AT+PORT=10" -> "+PORT: 10" (manual sec 4.11).
  LORA_SERIAL.host_feed("+PORT: 10\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kJoining,
               "kSettingPort must advance on its real +PORT: response");

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

  // No valid response ever arrives. kSettingMode re-sends its command for
  // up to LORA_JOIN_MAX_RETRIES timeouts, staying in kSettingMode each time.
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

static void test_horn_taking_the_port_mid_step_restarts_from_the_probe(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingRegion, &t);
  assert_state(lora_join_state::kSettingRegion, "setup: must reach kSettingRegion");
  TEST_ASSERT_TRUE(uart_share_owner() == uart_owner::kLora);

  // A horn fire claims USART1 while AT+DR=IN865 is outstanding. The E5's
  // "+DR:" reply goes to a disconnected wire; whatever sits in the buffer
  // afterwards is not it.
  uart_share_acquire(uart_owner::kDfplayer);
  LORA_SERIAL.host_feed("+DR: IN865 DR0 SF12BW125\r\n");

  t += 10;
  lora_service(t);
  TEST_ASSERT_TRUE_MESSAGE(uart_share_owner() == uart_owner::kLora,
                           "lora_service() must take the port back");
  assert_state(lora_join_state::kProbing,
               "a step interrupted by the horn must restart from the AT "
               "probe, not act on a buffer that may hold the wrong reply");
  TEST_ASSERT_EQUAL_UINT32(LORA_UART_BAUD, LORA_SERIAL.host_baud());
}

static void test_joined_and_failed_states_leave_the_port_with_the_dfplayer(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingMode, &t);
  for (uint8_t retry = 0; retry < LORA_JOIN_MAX_RETRIES + 1; ++retry) {
    t += LORA_AT_TIMEOUT_MS + 1;
    lora_service(t);
  }
  assert_state(lora_join_state::kFailed, "setup: must reach kFailed");

  uart_share_acquire(uart_owner::kDfplayer);
  t += 1;
  lora_service(t);
  TEST_ASSERT_TRUE_MESSAGE(uart_share_owner() == uart_owner::kDfplayer,
                           "waiting out a backoff must not pull the port from the DFPlayer");
}

static void test_timed_out_step_resends_its_command(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kSettingMode, &t);
  LORA_SERIAL.host_reset_tx();

  t += LORA_AT_TIMEOUT_MS + 1;
  lora_service(t);
  TEST_ASSERT_TRUE_MESSAGE(tx_contains("AT+MODE=LWOTAA"),
                           "a retry must put the command back on the wire, not just "
                           "wait again for a reply that will never come");
}

static void test_joined_already_counts_as_joined(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kJoining, &t);
  // Manual sec 4.24: an E5 that kept its session across an MCU reset.
  LORA_SERIAL.host_feed("+JOIN: Joined already\r\n");
  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kJoined, "\"Joined already\" must count as joined");
}

static void test_join_failed_backs_off_then_resends_join(void) {
  uint32_t t = 1000;
  drive_to_state(lora_join_state::kJoining, &t);
  LORA_SERIAL.host_feed("+JOIN: Join failed\r\n+JOIN: Done\r\n");
  t += 10;
  lora_service(t);
  LORA_SERIAL.host_reset_tx();

  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kJoining, "a failed join must stay in kJoining");
  TEST_ASSERT_FALSE_MESSAGE(tx_contains("AT+JOIN"),
                            "the trailing Done after a failure must not be read as a join, "
                            "and JOIN must not be re-sent before the backoff");

  t += LORA_JOIN_BACKOFF_BASE_MS * 2;
  lora_service(t);
  TEST_ASSERT_TRUE_MESSAGE(tx_contains("AT+JOIN"), "JOIN must be re-sent after the backoff");
  assert_state(lora_join_state::kJoining, "still joining after the re-send");
}

static void test_event_queued_before_join_goes_out_after_it(void) {
  uint32_t t = 1000;
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  drive_to_joined(&t);
  TEST_ASSERT_FALSE_MESSAGE(tx_contains("CMSGHEX"), "nothing may be sent before the join");
  assert_state(lora_join_state::kJoined, "setup: must reach kJoined");

  t += 10;
  lora_service(t);
  assert_state(lora_join_state::kSending, "a queued frame must go out once joined");
  TEST_ASSERT_TRUE_MESSAGE(tx_contains(kSampleEventCmd),
                           "an event must go out as a confirmed uplink with its encoded bytes");
  TEST_ASSERT_TRUE_MESSAGE(lora_joined(), "lora_joined() must stay true while sending");
}

static void test_acked_event_counts_as_sent(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  service_lines(&t, 1);
  assert_state(lora_join_state::kSending, "setup: must be sending");

  // Manual sec 4.8 worked example.
  LORA_SERIAL.host_feed(
      "+CMSGHEX: Start\r\n+CMSGHEX: Wait ACK\r\n+CMSGHEX: ACK Received\r\n"
      "+CMSGHEX: RXWIN1, RSSI -45, SNR 9.0\r\n+CMSGHEX: Done\r\n");
  service_lines(&t, 6);
  assert_state(lora_join_state::kJoined, "a finished send must return to kJoined");
  TEST_ASSERT_EQUAL_UINT32(1, lora_uplinks_sent());
  TEST_ASSERT_EQUAL_UINT8(0, lora_queue_depth());
}

static void test_unacked_event_is_retried_then_dropped(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));

  for (uint8_t attempt = 1; attempt <= LORA_UPLINK_MAX_ATTEMPTS; ++attempt) {
    LORA_SERIAL.host_reset_tx();
    t += LORA_UPLINK_RETRY_BASE_MS * LORA_UPLINK_MAX_ATTEMPTS;
    lora_service(t);
    TEST_ASSERT_TRUE_MESSAGE(tx_contains(kSampleEventCmd),
                             "each attempt must re-send the same frame, same seq");
    LORA_SERIAL.host_feed("+CMSGHEX: Start\r\n+CMSGHEX: Wait ACK\r\n+CMSGHEX: Done\r\n");
    service_lines(&t, 3);
    assert_state(lora_join_state::kJoined, "an unacked send must return to kJoined");
  }
  TEST_ASSERT_EQUAL_UINT32(0, lora_uplinks_sent());
  TEST_ASSERT_EQUAL_UINT32(1, lora_uplinks_dropped());
  TEST_ASSERT_EQUAL_UINT8(0, lora_queue_depth());
}

static void test_unacked_event_waits_before_retry(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  service_lines(&t, 1);
  LORA_SERIAL.host_feed("+CMSGHEX: Done\r\n");
  service_lines(&t, 1);
  LORA_SERIAL.host_reset_tx();

  service_lines(&t, 1);
  TEST_ASSERT_FALSE_MESSAGE(tx_contains("CMSGHEX"), "a retry must wait out its delay");
  TEST_ASSERT_EQUAL_UINT8(1, lora_queue_depth());
}

static void test_not_joined_error_rejoins_and_keeps_the_frame(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  service_lines(&t, 1);

  LORA_SERIAL.host_feed("+CMSGHEX: Please join network first\r\n");
  service_lines(&t, 1);
  assert_state(lora_join_state::kProbing, "a lost session must restart the join");
  TEST_ASSERT_EQUAL_UINT8(1, lora_queue_depth());
  TEST_ASSERT_EQUAL_UINT32(0, lora_uplinks_dropped());
}

static void test_horn_mid_send_resends_the_same_frame(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  service_lines(&t, 1);
  assert_state(lora_join_state::kSending, "setup: must be sending");

  uart_share_acquire(uart_owner::kDfplayer);
  LORA_SERIAL.host_feed("+CMSGHEX: Done\r\n");  // lost on the far side of the switch
  LORA_SERIAL.host_reset_tx();
  service_lines(&t, 1);
  TEST_ASSERT_TRUE_MESSAGE(tx_contains(kSampleEventCmd),
                           "the interrupted frame must go out again with the same seq");
  assert_state(lora_join_state::kSending, "the re-send must be in flight");

  // The interruption is not charged: a full LORA_UPLINK_MAX_ATTEMPTS unacked
  // sends are still needed before the frame is dropped.
  for (uint8_t attempt = 1; attempt < LORA_UPLINK_MAX_ATTEMPTS; ++attempt) {
    LORA_SERIAL.host_feed("+CMSGHEX: Done\r\n");
    service_lines(&t, 1);
    t += LORA_UPLINK_RETRY_BASE_MS * LORA_UPLINK_MAX_ATTEMPTS;
    lora_service(t);
  }
  TEST_ASSERT_EQUAL_UINT32(0, lora_uplinks_dropped());
  TEST_ASSERT_EQUAL_UINT8(1, lora_queue_depth());
}

static void test_status_goes_out_after_join_and_on_the_heartbeat(void) {
  uint32_t t = 1000;
  lora_set_status_source(sample_status);
  drive_to_joined(&t);
  LORA_SERIAL.host_reset_tx();

  service_lines(&t, 1);
  TEST_ASSERT_TRUE_MESSAGE(tx_contains("AT+MSGHEX=\"1100"),
                           "a status must go out, unconfirmed, right after the join");
  LORA_SERIAL.host_feed("+MSGHEX: Start\r\n+MSGHEX: Done\r\n");
  service_lines(&t, 2);
  TEST_ASSERT_EQUAL_UINT32(1, lora_uplinks_sent());

  LORA_SERIAL.host_reset_tx();
  t += LORA_STATUS_INTERVAL_MS / 2;
  service_lines(&t, 1);
  TEST_ASSERT_FALSE_MESSAGE(tx_contains("MSGHEX"), "no status before the interval");

  t += LORA_STATUS_INTERVAL_MS;
  service_lines(&t, 1);
  TEST_ASSERT_TRUE_MESSAGE(tx_contains("AT+MSGHEX=\"1101"),
                           "the next status must go out on the heartbeat, next seq");
}

static void test_full_queue_event_evicts_a_status(void) {
  const uplink_status st = sample_status(0);
  TEST_ASSERT_TRUE(lora_queue_status(st));
  TEST_ASSERT_TRUE(lora_queue_status(st));
  TEST_ASSERT_EQUAL_UINT8_MESSAGE(1, lora_queue_depth(),
                                  "a newer status must replace a queued one");

  for (uint8_t i = 1; i < LORA_UPLINK_QUEUE_LEN; ++i) {
    TEST_ASSERT_TRUE(lora_queue_event(sample_event()));
  }
  TEST_ASSERT_EQUAL_UINT8(LORA_UPLINK_QUEUE_LEN, lora_queue_depth());
  TEST_ASSERT_TRUE_MESSAGE(lora_queue_status(st),
                           "a full queue still takes a status that replaces the queued one");
  TEST_ASSERT_EQUAL_UINT8(LORA_UPLINK_QUEUE_LEN, lora_queue_depth());

  TEST_ASSERT_TRUE_MESSAGE(lora_queue_event(sample_event()),
                           "an event must evict the queued status");
  TEST_ASSERT_EQUAL_UINT32(1, lora_uplinks_dropped());
  TEST_ASSERT_FALSE_MESSAGE(lora_queue_status(st), "a status must not displace an event");
  TEST_ASSERT_FALSE_MESSAGE(lora_queue_event(sample_event()),
                            "a queue of events only must refuse a new one");
}

static void test_joined_with_nothing_to_send_leaves_the_port(void) {
  uint32_t t = 1000;
  drive_to_joined(&t);
  uart_share_acquire(uart_owner::kDfplayer);
  service_lines(&t, 3);
  TEST_ASSERT_TRUE_MESSAGE(uart_share_owner() == uart_owner::kDfplayer,
                           "an idle, joined radio must leave the port with the DFPlayer");
}

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_happy_path_full_join_sequence);
  RUN_TEST(test_setting_mode_does_not_advance_on_bare_ok);
  RUN_TEST(test_setting_region_does_not_advance_on_bare_ok);
  RUN_TEST(test_loading_key_does_not_advance_on_bare_ok);
  RUN_TEST(test_timed_out_step_retries_then_fails_after_max_retries);
  RUN_TEST(test_failed_state_backs_off_then_retries_from_idle);
  RUN_TEST(test_horn_taking_the_port_mid_step_restarts_from_the_probe);
  RUN_TEST(test_joined_and_failed_states_leave_the_port_with_the_dfplayer);
  RUN_TEST(test_timed_out_step_resends_its_command);
  RUN_TEST(test_joined_already_counts_as_joined);
  RUN_TEST(test_join_failed_backs_off_then_resends_join);
  RUN_TEST(test_event_queued_before_join_goes_out_after_it);
  RUN_TEST(test_acked_event_counts_as_sent);
  RUN_TEST(test_unacked_event_is_retried_then_dropped);
  RUN_TEST(test_unacked_event_waits_before_retry);
  RUN_TEST(test_not_joined_error_rejoins_and_keeps_the_frame);
  RUN_TEST(test_horn_mid_send_resends_the_same_frame);
  RUN_TEST(test_status_goes_out_after_join_and_on_the_heartbeat);
  RUN_TEST(test_full_queue_event_evicts_a_status);
  RUN_TEST(test_joined_with_nothing_to_send_leaves_the_port);
  return UNITY_END();
}
