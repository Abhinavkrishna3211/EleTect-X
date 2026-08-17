// AT command sequence source: Seeed Studio, "LoRa-E5 AT Command
// Specification V1.0" PDF
// (https://files.seeedstudio.com/products/317990687/res/LoRa-E5+AT+Command+Specification_V1.0+.pdf).
// Checked line-by-line against that manual's text layer (pdftotext -layout):
// section 4.23 (MODE), 4.13 (DR), 3.9 (Band Specific Limitation), 4.20
// (KEY), 4.3 (ID), and 4.24 (JOIN). Exact command/response strings below are
// quoted from the manual; see each state's comment for the section cited.
//
// One deviation from the original ticket for this file: the JOIN success
// string is "+JOIN: Done" (per 4.24's worked example - "+JOIN: Starting" /
// "+JOIN: NORMAL" / "+JOIN: NetID ... DevAddr ..." / "+JOIN: Done"), not
// "Network joined". The string "Network joined" does not appear anywhere in
// this manual's text; "+JOIN: Join failed" does appear verbatim and is
// unchanged. Flagging since this contradicts secondary-source tutorials -
// worth a second look if a real join sequence prints something else.
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
      // "AT" - bare probe command. Response confirmed in manual sec 5
      // (Error Code) worked examples as "+AT: OK", which contains "OK".
      send_command("AT", now_ms);
      g_state = lora_join_state::kProbing;
      break;

    case lora_join_state::kProbing:
      if (poll_line() && rx_contains("OK")) {
        // "AT+ID=DevEui" confirmed, manual sec 4.3 (ID).
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
        // Response is "+ID: DevEui, xx:xx:..." (manual sec 4.3) - any
        // complete line confirms the module replied, no need to match it.
        send_command("AT+MODE=LWOTAA", now_ms);
        g_state = lora_join_state::kSettingMode;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kReadingDevEui, now_ms);
      }
      break;

    case lora_join_state::kSettingMode:
      // Response confirmed, manual sec 4.23 (MODE): "+MODE: LWOTAA" -
      // does NOT contain "OK", so this must not gate on rx_contains("OK").
      if (poll_line() && rx_contains("+MODE: LWOTAA")) {
        // "AT+DR=IN865" confirmed, manual sec 4.13.2 (Data Rate Scheme) -
        // "band" may be a band name such as IN865.
        send_command("AT+DR=IN865", now_ms);
        g_state = lora_join_state::kSettingRegion;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingMode, now_ms);
      }
      break;

    case lora_join_state::kSettingRegion:
      // Response confirmed, manual sec 4.13.2: "+DR: IN865 DR0 ..." -
      // does NOT contain "OK", so gate on the command's own "+DR:" prefix.
      if (poll_line() && rx_contains("+DR:")) {
        // No channel-mask step here: manual sec 3.9.1 (US915/AU915/CN470
        // Channel Limitation) restricts AT+CH/AT+RXWIN1 use to those three
        // regions only - IN865 is not listed and needs no explicit channel
        // command, so this goes straight to setting AppEui.
        // "AT+ID=AppEui,<eui>" confirmed, manual sec 4.3 (ID) - quoted,
        // per the set-example "AT+ID=AppEui, "0123456789ABCDEF"".
        char cmd[64];
        std::snprintf(cmd, sizeof(cmd), "AT+ID=AppEui,\"%s\"", LORA_APP_EUI);
        send_command(cmd, now_ms);
        g_state = lora_join_state::kSettingAppEui;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingRegion, now_ms);
      }
      break;

    case lora_join_state::kSettingAppEui:
      // Response confirmed, manual sec 4.3 (ID) set-example return:
      // "+ID: AppEui, xx:xx:xx:xx:xx:xx:xx:xx".
      if (poll_line() && rx_contains("+ID: AppEui")) {
        // AppKey is loaded from the gitignored secrets.h, never logged.
        // "AT+KEY=APPKEY,<key>" confirmed, manual sec 4.20 (KEY) - the
        // key value must be quoted per the worked example
        // "AT+KEY=APPKEY, "2B7E151628AED2A6ABF7158809CF4F3C"".
        char cmd[96];
        std::snprintf(cmd, sizeof(cmd), "AT+KEY=APPKEY,\"%s\"", LORA_APP_KEY);
        send_command(cmd, now_ms);
        g_state = lora_join_state::kLoadingKey;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kSettingAppEui, now_ms);
      }
      break;

    case lora_join_state::kLoadingKey:
      // Response confirmed, manual sec 4.20 (KEY): "+KEY: APPKEY <key>" -
      // does NOT contain "OK", so gate on the command's own "+KEY:" prefix.
      if (poll_line() && rx_contains("+KEY:")) {
        // "AT+JOIN" with no arguments confirmed, manual sec 4.24 (JOIN).
        send_command("AT+JOIN", now_ms);
        g_state = lora_join_state::kJoining;
      } else if (step_timed_out(now_ms)) {
        enter_failed_or_retry(lora_join_state::kLoadingKey, now_ms);
      }
      break;

    case lora_join_state::kJoining:
      // Confirmed, manual sec 4.24 (JOIN) worked example: success prints
      // "+JOIN: Starting" / "+JOIN: NORMAL" / "+JOIN: NetID ... DevAddr
      // ..." / "+JOIN: Done"; failure prints "+JOIN: Join failed". The
      // string "Network joined" does not appear anywhere in the manual -
      // do not gate on it, or this state can never observe success.
      if (poll_line() && rx_contains("+JOIN: Done")) {
        g_state = lora_join_state::kJoined;
        g_retry_count = 0;
      } else if (poll_line() && rx_contains("+JOIN: Join failed")) {
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
