// Tests for uart_share.cpp's USART1 time-share between the DFPlayer PRO and
// the LoRa-E5 through a 74HC4053 (ADR 0029).
//
// Runs under both PlatformIO envs and checks the behaviour each one should
// have: `native` (LORA_ENABLED 1) must route, re-open at the right baud and
// drop the outgoing module's leftover RX bytes on every switch;
// `native_dfplayer_only` (LORA_ENABLED 0) must leave the select pin alone and
// refuse LoRa.

#include <unity.h>

#include "Arduino.h"
#include "config.h"
#include "horn.h"
#include "uart_share.h"

void setUp() {
  hostshim::reset();
  while (UART_SHARE_SERIAL.available() > 0) {
    UART_SHARE_SERIAL.read();
  }
  UART_SHARE_SERIAL.host_reset_begin_count();
  uart_share_init();
}

void tearDown() {}

static size_t select_pin_writes() {
  size_t n = 0;
  for (const auto &w : hostshim::pin_writes()) {
    if (w.pin == UART_SHARE_SELECT_PIN) {
      ++n;
    }
  }
  return n;
}

// --- pure helpers (both envs) -----------------------------------------------

static void test_select_level_per_owner(void) {
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_DFPLAYER, uart_share_select_level(uart_owner::kDfplayer));
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_LORA, uart_share_select_level(uart_owner::kLora));
  TEST_ASSERT_NOT_EQUAL(uart_share_select_level(uart_owner::kDfplayer),
                        uart_share_select_level(uart_owner::kLora));
}

static void test_baud_per_owner(void) {
  TEST_ASSERT_EQUAL_UINT32(DFPLAYER_UART_BAUD, uart_share_baud(uart_owner::kDfplayer));
  TEST_ASSERT_EQUAL_UINT32(LORA_UART_BAUD, uart_share_baud(uart_owner::kLora));
}

static void test_init_opens_the_port_for_the_dfplayer(void) {
  TEST_ASSERT_TRUE(uart_share_owner() == uart_owner::kDfplayer);
  TEST_ASSERT_EQUAL_UINT32(DFPLAYER_UART_BAUD, UART_SHARE_SERIAL.host_baud());
  TEST_ASSERT_EQUAL_UINT32(1, UART_SHARE_SERIAL.host_begin_count());
  TEST_ASSERT_EQUAL_UINT32(0, uart_share_switch_count());
}

static void test_acquiring_the_current_owner_does_nothing(void) {
  const size_t writes_before = select_pin_writes();
  TEST_ASSERT_TRUE(uart_share_acquire(uart_owner::kDfplayer));
  TEST_ASSERT_EQUAL_UINT32(1, UART_SHARE_SERIAL.host_begin_count());
  TEST_ASSERT_EQUAL_UINT32(0, uart_share_switch_count());
  TEST_ASSERT_EQUAL_UINT32(writes_before, select_pin_writes());
}

#if UART_SHARE_ENABLED

// --- share enabled (native) ---------------------------------------------------

static void test_init_drives_select_to_the_dfplayer(void) {
  TEST_ASSERT_EQUAL_UINT32(1, select_pin_writes());
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_DFPLAYER, hostshim::pin_state(UART_SHARE_SELECT_PIN));
}

static void test_switch_to_lora_routes_and_reopens_at_lora_baud(void) {
  TEST_ASSERT_TRUE(uart_share_acquire(uart_owner::kLora));
  TEST_ASSERT_TRUE(uart_share_owner() == uart_owner::kLora);
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_LORA, hostshim::pin_state(UART_SHARE_SELECT_PIN));
  TEST_ASSERT_EQUAL_UINT32(LORA_UART_BAUD, UART_SHARE_SERIAL.host_baud());
  TEST_ASSERT_EQUAL_UINT32(2, UART_SHARE_SERIAL.host_begin_count());
  TEST_ASSERT_EQUAL_UINT32(1, uart_share_switch_count());
}

static void test_switch_back_restores_dfplayer_route_and_baud(void) {
  uart_share_acquire(uart_owner::kLora);
  TEST_ASSERT_TRUE(uart_share_acquire(uart_owner::kDfplayer));
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_DFPLAYER, hostshim::pin_state(UART_SHARE_SELECT_PIN));
  TEST_ASSERT_EQUAL_UINT32(DFPLAYER_UART_BAUD, UART_SHARE_SERIAL.host_baud());
  TEST_ASSERT_EQUAL_UINT32(2, uart_share_switch_count());
}

static void test_switch_moves_select_and_waits_the_settle_delay(void) {
  // The last pin write of a switch is the select line, and the settle delay
  // is actually spent (virtual millis() in the host build).
  const unsigned long before_ms = millis();
  uart_share_acquire(uart_owner::kLora);
  const auto &writes = hostshim::pin_writes();
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_PIN, writes.back().pin);
  TEST_ASSERT_GREATER_OR_EQUAL_UINT32(UART_SHARE_SWITCH_SETTLE_MS, millis() - before_ms);
}

static void test_switch_drops_the_previous_modules_leftover_bytes(void) {
  UART_SHARE_SERIAL.host_feed("OK\r\n");  // DFPlayer's last ack, never read
  uart_share_acquire(uart_owner::kLora);
  TEST_ASSERT_EQUAL_INT(0, UART_SHARE_SERIAL.available());
}

static void test_horn_fire_takes_the_port_back_from_lora(void) {
  uart_share_acquire(uart_owner::kLora);
  horn_init();  // re-runs uart_share_init(); hand the port to LoRa again below
  uart_share_acquire(uart_owner::kLora);
  UART_SHARE_SERIAL.host_reset_bytes_written();

  const horn_ack ack = drive_horn({/*duration_ms=*/500, /*gain_pct=*/50.0f, /*track_id=*/1}, 1000);

  TEST_ASSERT_TRUE(ack.allowed);
  TEST_ASSERT_TRUE(uart_share_owner() == uart_owner::kDfplayer);
  TEST_ASSERT_EQUAL_INT(UART_SHARE_SELECT_DFPLAYER, hostshim::pin_state(UART_SHARE_SELECT_PIN));
  TEST_ASSERT_EQUAL_UINT32(DFPLAYER_UART_BAUD, UART_SHARE_SERIAL.host_baud());
  TEST_ASSERT_GREATER_THAN_UINT32(0, UART_SHARE_SERIAL.host_bytes_written());
}

#else

// --- share disabled (native_dfplayer_only) -----------------------------------

static void test_disabled_never_touches_the_select_pin(void) {
  uart_share_acquire(uart_owner::kDfplayer);
  uart_share_acquire(uart_owner::kLora);
  TEST_ASSERT_EQUAL_UINT32(0, select_pin_writes());
}

static void test_disabled_refuses_lora_and_keeps_the_dfplayer(void) {
  TEST_ASSERT_FALSE(uart_share_acquire(uart_owner::kLora));
  TEST_ASSERT_TRUE(uart_share_owner() == uart_owner::kDfplayer);
  TEST_ASSERT_EQUAL_UINT32(DFPLAYER_UART_BAUD, UART_SHARE_SERIAL.host_baud());
  TEST_ASSERT_EQUAL_UINT32(1, UART_SHARE_SERIAL.host_begin_count());
}

#endif

int main(int, char **) {
  UNITY_BEGIN();
  RUN_TEST(test_select_level_per_owner);
  RUN_TEST(test_baud_per_owner);
  RUN_TEST(test_init_opens_the_port_for_the_dfplayer);
  RUN_TEST(test_acquiring_the_current_owner_does_nothing);
#if UART_SHARE_ENABLED
  RUN_TEST(test_init_drives_select_to_the_dfplayer);
  RUN_TEST(test_switch_to_lora_routes_and_reopens_at_lora_baud);
  RUN_TEST(test_switch_back_restores_dfplayer_route_and_baud);
  RUN_TEST(test_switch_moves_select_and_waits_the_settle_delay);
  RUN_TEST(test_switch_drops_the_previous_modules_leftover_bytes);
  RUN_TEST(test_horn_fire_takes_the_port_back_from_lora);
#else
  RUN_TEST(test_disabled_never_touches_the_select_pin);
  RUN_TEST(test_disabled_refuses_lora_and_keeps_the_dfplayer);
#endif
  return UNITY_END();
}
