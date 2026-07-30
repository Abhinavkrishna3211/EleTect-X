// AT command sequence source: Seeed Studio, "Grove - LoRa-E5 / LoRa-E5 AT
// Command Specification" (Seeed wiki page for the Grove LoRa-E5 module,
// PDF linked from https://wiki.seeedstudio.com/Grove_LoRa_E5_New_Version/).
// This file has NOT been checked line-by-line against that manual - it was
// written from memory of typical AT-command LoRaWAN modules and the general
// shape of the E5's command set. Every command below is marked either
// verified (checked against the manual) or UNVERIFIED against AT manual.
// Do not flash this without opening the manual and correcting exact
// spelling, argument format, and expected response strings first
// (docs/KNOWN_GAPS.md).
//
// IN865 only (ADR 0002) - 868 MHz is illegal in India (CONTEXT.md 8).
// Never logs LORA_APP_KEY.

#include "mac.h"

#include <cstdio>
#include <cstring>

#include "Arduino.h"
#include "config.h"
#include "secrets.h"

namespace {

lora_join_state g_state = lora_join_state::kIdle;
uint32_t g_step_start_ms = 0;
uint8_t g_retry_count = 0;

char g_rx_buf[LORA_RESPONSE_MAX_LEN];
size_t g_rx_len = 0;

// Sends one AT command line and resets the per-step response buffer/timer.
// duration/response bytes are drained by poll_line() on later service()
// calls - this never blocks waiting for a reply.
void send_command(const char *cmd, uint32_t now_ms) {
  g_rx_len = 0;
  g_rx_buf[0] = '\0';
  LORA_SERIAL.print(cmd);
  LORA_SERIAL.print("\r\n");
  g_step_start_ms = now_ms;
}

// Drains any bytes the E5 has sent since the last call into g_rx_buf.
// Returns true once a full line (terminated by '\n') has been captured.
// Non-blocking: reads only what is already in the UART's RX buffer.
bool poll_line() {
  while (LORA_SERIAL.available() > 0 && g_rx_len + 1 < LORA_RESPONSE_MAX_LEN) {
    const char c = static_cast<char>(LORA_SERIAL.read());
    g_rx_buf[g_rx_len++] = c;
    g_rx_buf[g_rx_len] = '\0';
    if (c == '\n') {
      return true;
    }
  }
  return false;
}

bool rx_contains(const char *needle) {
  return std::strstr(g_rx_buf, needle) != nullptr;
}

bool step_timed_out(uint32_t now_ms) {
  return (now_ms - g_step_start_ms) > LORA_AT_TIMEOUT_MS;
}

// Backoff wait before a retried step - separate from the per-command
// timeout above (LORA_JOIN_BACKOFF_BASE_MS * retry count, per config.h).
bool backoff_elapsed(uint32_t now_ms) {
  const uint32_t backoff_ms =
      LORA_JOIN_BACKOFF_BASE_MS * (static_cast<uint32_t>(g_retry_count) + 1u);
  return (now_ms - g_step_start_ms) > backoff_ms;
}

void enter_failed_or_retry(lora_join_state retry_target, uint32_t now_ms) {
  ++g_retry_count;
  if (g_retry_count > LORA_JOIN_MAX_RETRIES) {
    g_state = lora_join_state::kFailed;
    return;
  }
  g_state = retry_target;
  g_step_start_ms = now_ms;
}

}  // namespace

void lora_init() {
  LORA_SERIAL.begin(LORA_UART_BAUD);
  g_state = lora_join_state::kIdle;
  g_retry_count = 0;
  g_rx_len = 0;
}

void lora_service(uint32_t now_ms) {
  switch (g_state) {
    case lora_join_state::kIdle:
      // "AT" - bare probe command, every AT-command modem accepts this.
      // UNVERIFIED against AT manual: exact expected response ("+AT: OK" vs
      // plain "OK").
      send_command("AT", now_ms);
      g_state = lora_join_state::kProbing;
      break;

    case lora_join_state::kProbing:
      if (poll_line() && rx_contains("OK")) {
        // UNVERIFIED against AT manual: "AT+ID=DevEui" is a guess at the
        // token; some E5 firmware revisions use "AT+ID=DEVEUI" instead.
        send_command("AT+ID=DevEui", now_ms);
        g_state = lora_join_state::kReadingDevEui;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kIdle, now_ms);
      }
      break;

    case lora_join_state::kReadingDevEui:
      if (poll_line()) {
        // DevEUI is not secret - fine to have reached the RX buffer, but it
        // is read and discarded here rather than logged, since this step
        // exists only to confirm the module is alive and addressable.
        // UNVERIFIED against AT manual: "AT+MODE=LWOTAA" token/casing.
        send_command("AT+MODE=LWOTAA", now_ms);
        g_state = lora_join_state::kSettingMode;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kReadingDevEui, now_ms);
      }
      break;

    case lora_join_state::kSettingMode:
      if (poll_line() && rx_contains("OK")) {
        // UNVERIFIED against AT manual: "AT+DR=IN865" is a guess - the
        // region-select command may instead be "AT+DR=<index>" preceded by
        // a separate region-select command entirely. Must be confirmed
        // before this joins a real IN865 gateway.
        send_command("AT+DR=IN865", now_ms);
        g_state = lora_join_state::kSettingRegion;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingMode, now_ms);
      }
      break;

    case lora_join_state::kSettingRegion:
      if (poll_line() && rx_contains("OK")) {
        // UNVERIFIED against AT manual: "AT+CH=NUM,0-2" channel-mask
        // syntax and whether IN865's default channel plan even needs an
        // explicit mask set.
        send_command("AT+CH=NUM,0-2", now_ms);
        g_state = lora_join_state::kSettingChannelMask;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingRegion, now_ms);
      }
      break;

    case lora_join_state::kSettingChannelMask:
      if (poll_line() && rx_contains("OK")) {
        // AppKey is loaded from the gitignored secrets.h, never logged.
        // UNVERIFIED against AT manual: "AT+KEY=APPKEY,<key>" token.
        char cmd[96];
        std::snprintf(cmd, sizeof(cmd), "AT+KEY=APPKEY,%s", LORA_APP_KEY);
        send_command(cmd, now_ms);
        g_state = lora_join_state::kLoadingKey;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingChannelMask, now_ms);
      }
      break;

    case lora_join_state::kLoadingKey:
      if (poll_line() && rx_contains("OK")) {
        // UNVERIFIED against AT manual: "AT+JOIN" with no arguments for a
        // default-parameters OTAA join.
        send_command("AT+JOIN", now_ms);
        g_state = lora_join_state::kJoining;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kLoadingKey, now_ms);
      }
      break;

    case lora_join_state::kJoining:
      // UNVERIFIED against AT manual: "+JOIN: Network joined" success
      // string and "+JOIN: Join failed" failure string - both guesses at
      // the E5's actual join-result reporting format.
      if (poll_line() && rx_contains("Network joined")) {
        g_state = lora_join_state::kJoined;
        g_retry_count = 0;
      } else if (poll_line() && rx_contains("Join failed")) {
        enter_failed_or_retry(lora_join_state::kSettingMode, now_ms);
      } else if ((now_ms - g_step_start_ms) > LORA_JOIN_TIMEOUT_MS) {
        enter_failed_or_retry(lora_join_state::kSettingMode, now_ms);
      }
      break;

    case lora_join_state::kJoined:
      // Nothing to do - uplinks are a later build call (schema.md's
      // report_* notify functions aren't wired to the LoRa transport yet).
      break;

    case lora_join_state::kFailed:
      // Bounded retry budget exhausted. Wait out a full backoff window,
      // then give the whole sequence one more try from the top - a
      // transient gateway/module issue should not permanently strand the
      // node without ever probing again.
      if (backoff_elapsed(now_ms)) {
        g_retry_count = 0;
        g_state = lora_join_state::kIdle;
      }
      break;
  }
}

lora_join_state lora_get_state() { return g_state; }

bool lora_joined() { return g_state == lora_join_state::kJoined; }
