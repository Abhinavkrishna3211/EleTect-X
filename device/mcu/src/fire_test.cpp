#include "fire_test.h"

#include "Arduino.h"
#include "config.h"
#include "horn.h"
#include "ir.h"
#include "led.h"
#include "uart_share.h"

namespace {

void print_menu() {
  Serial.println(
      "[firetest] commands: 1=horn 2=led_wing_left 3=led_wing_right 4=ir "
      "a=dfplayer_at l=dfplayer_listen_full f=dfplayer_listen_by_filename ?=help");
  Serial.println(
      "[firetest] cooldowns are real (horn 10s / led 8s / ir 5s) - a "
      "repeat within that window prints allowed=false, that is the gate "
      "working, not a bug");
}

// Reads one line from `stream` into buf (stripping a trailing \r and/or \n),
// blocking up to timeout_ms after the last byte arrives. Returns true if a
// newline-terminated line was captured before the timeout, false otherwise
// (buf holds whatever partial bytes arrived either way). Shared by both
// halves of the AT round-trip below - reading the human's typed command and
// reading the DFPlayer's reply are the same operation on two different
// streams.
bool read_line_blocking(Stream &stream, char *buf, size_t buf_len, uint32_t timeout_ms,
                         uint32_t now_ms) {
  size_t len = 0;
  buf[0] = '\0';
  const uint32_t deadline_ms = now_ms + timeout_ms;
  while (millis() < deadline_ms) {
    if (!stream.available()) {
      continue;
    }
    const char c = static_cast<char>(stream.read());
    if (c == '\n') {
      return true;
    }
    if (c == '\r') {
      continue;
    }
    if (len + 1 < buf_len) {
      buf[len++] = c;
      buf[len] = '\0';
    }
  }
  return false;
}

// 'a' command: forward one human-typed line verbatim to the DFPlayer PRO's
// AT link and print whatever comes back. Exists to run the Stage B bring-up
// probes (AT, AT+QUERY=2, AT+QUERY=5, AT+PLAY=PP) that no other harness path
// can send (docs/decisions - ADR superseding 0015 Decision A).
void run_dfplayer_at(uint32_t now_ms) {
  Serial.println("[firetest] dfplayer AT mode - type a command (e.g. AT, AT+QUERY=2) and press enter");

  char line[FIRE_TEST_AT_LINE_MAX_LEN];
  if (!read_line_blocking(Serial, line, sizeof(line), FIRE_TEST_AT_LINE_TIMEOUT_MS, now_ms)) {
    Serial.println("[firetest] dfplayer AT: no command typed (timeout)");
    return;
  }
  if (line[0] == '\0') {
    Serial.println("[firetest] dfplayer AT: empty line, nothing sent");
    return;
  }

  Serial.print("[firetest] dfplayer AT: sending ");
  Serial.println(line);
  uart_share_acquire(uart_owner::kDfplayer);
  DFPLAYER_SERIAL.print(line);
  DFPLAYER_SERIAL.print("\r\n");

  // The DFPlayer PRO can reply with more than one line per command (e.g. a
  // query's data line plus a trailing OK ack, seen in either order on this
  // unit) - reading only the first line risks printing a stale/wrong half
  // of a multi-line reply, and leaves the rest sitting in the RX buffer to
  // be misread as the *next* command's reply. Drain every line that arrives
  // within the reply timeout of the previous one, so a multi-line reply is
  // captured in full and never bleeds into the next command's read.
  char reply[FIRE_TEST_AT_LINE_MAX_LEN];
  uint32_t wait_from_ms = millis();
  int lines_read = 0;
  while (read_line_blocking(DFPLAYER_SERIAL, reply, sizeof(reply), FIRE_TEST_AT_REPLY_TIMEOUT_MS,
                             wait_from_ms)) {
    Serial.print("[firetest] dfplayer AT: reply[");
    Serial.print(lines_read);
    Serial.print("]=");
    Serial.println(reply);
    lines_read++;
    wait_from_ms = millis();
  }
  if (lines_read == 0) {
    if (reply[0] != '\0') {
      Serial.print("[firetest] dfplayer AT: partial reply (no newline before timeout)=");
      Serial.println(reply);
    } else {
      Serial.println("[firetest] dfplayer AT: no reply (timeout)");
    }
  }
}

// Prompts for and reads a single track index (1-5), shared by kHorn and
// kListen. Blank/timeout/garbage falls back to FIRE_TEST_HORN_TRACK_ID rather
// than blocking the whole harness.
uint8_t read_track_id(uint32_t now_ms) {
  Serial.println("[firetest] which track 1-5? (blank/timeout = default)");
  char line[8];
  if (read_line_blocking(Serial, line, sizeof(line), FIRE_TEST_AT_LINE_TIMEOUT_MS, now_ms) &&
      line[0] >= '1' && line[0] <= '5' && line[1] == '\0') {
    return static_cast<uint8_t>(line[0] - '0');
  }
  return FIRE_TEST_HORN_TRACK_ID;
}

// Shared ack-print for horn_ack/led_ack/ir_ack - same four fields
// (duration_ms, gain_pct, clamped, allowed) on all three, per rule_gate.h's
// common contract. Prints the full ack, not just allowed/clamped, per
// KNOWN_GAPS.md's note that a bare bool is too lossy to bench-verify against.
template <typename Ack>
void print_ack(const char *label, const Ack &ack) {
  Serial.print("[firetest] ");
  Serial.print(label);
  Serial.print(" allowed=");
  Serial.print(ack.allowed);
  Serial.print(" duration_ms=");
  Serial.print(ack.duration_ms);
  Serial.print(" gain_pct=");
  Serial.print(ack.gain_pct);
  Serial.print(" clamped=");
  Serial.println(ack.clamped);
}

}  // namespace

fire_test_target fire_test_parse_command(char c) {
  switch (c) {
    case '1':
      return fire_test_target::kHorn;
    case '2':
      return fire_test_target::kLedWingLeft;
    case '3':
      return fire_test_target::kLedWingRight;
    case '4':
      return fire_test_target::kIr;
    case 'a':
      return fire_test_target::kDfplayerAt;
    case 'l':
      return fire_test_target::kListen;
    case 'f':
      return fire_test_target::kListenByFile;
    case '?':
      return fire_test_target::kHelp;
    default:
      return fire_test_target::kNone;
  }
}

void fire_test_init() { print_menu(); }

void fire_test_service(uint32_t now_ms) {
  if (!Serial.available()) {
    return;
  }

  const char c = static_cast<char>(Serial.read());

  // A terminal's Enter key sends the command byte followed by \r and/or \n.
  // Left alone, that trailing byte sits in the RX buffer and gets consumed
  // by whichever read happens next - for 'a' specifically, that is
  // run_dfplayer_at()'s read_line_blocking() call, which sees the leftover
  // \n first and returns an empty line before the human can type the real
  // AT command at all. Draining it here, once, before dispatch fixes every
  // command uniformly. Found live during Stage B bring-up: sending "a\nAT\n"
  // produced "empty line, nothing sent" followed by the menu printing three
  // times as 'A', 'T', '\n' were each re-read as bogus top-level commands.
  while (Serial.available() && (Serial.peek() == '\r' || Serial.peek() == '\n')) {
    Serial.read();
  }

  const fire_test_target target = fire_test_parse_command(c);

  // Each branch below blocks for its actuator's resolved duration (see
  // fire_test.h's contract) - acceptable here because this whole harness is
  // bench-only and human-triggered, never compiled into a field build
  // (FIRE_TEST_HARNESS defaults to 0, config.h).
  switch (target) {
    case fire_test_target::kHorn: {
      // Stage D: real production path (rule_gate cooldown + HORN_BURST_MAX_MS
      // clamp both apply). Prompts for which of the 5 loaded tracks to play -
      // AT+QUERY=5 did not return trustworthy filenames on this unit, so the
      // index->content map has to be confirmed by ear instead.
      const uint8_t track_id = read_track_id(now_ms);
      Serial.print("[firetest] horn: firing track ");
      Serial.println(track_id);
      const horn_request req = {FIRE_TEST_HORN_DURATION_MS, FIRE_TEST_HORN_GAIN_PCT, track_id};
      print_ack("horn", drive_horn(req, now_ms));
      break;
    }
    case fire_test_target::kLedWingLeft: {
      // Bench harness always fires the steady pattern - it verifies wiring
      // and polarity, not the ADR 0014 pattern shapes (those are exercised
      // by the host tests, tests/test_led).
      const led_request req = {led_channel::kWingLeft, led_pattern::kSteady,
                                FIRE_TEST_LED_DURATION_MS, FIRE_TEST_LED_GAIN_PCT};
      print_ack("led_wing_left", drive_led(req, now_ms));
      break;
    }
    case fire_test_target::kLedWingRight: {
      const led_request req = {led_channel::kWingRight, led_pattern::kSteady,
                                FIRE_TEST_LED_DURATION_MS, FIRE_TEST_LED_GAIN_PCT};
      print_ack("led_wing_right", drive_led(req, now_ms));
      break;
    }
    case fire_test_target::kIr: {
      const ir_request req = {FIRE_TEST_IR_DURATION_MS, FIRE_TEST_IR_GAIN_PCT};
      print_ack("ir", pulse_ir(req, now_ms));
      break;
    }
    case fire_test_target::kDfplayerAt:
      run_dfplayer_at(now_ms);
      break;
    case fire_test_target::kListen: {
      // Stage C: identification listen. Bypasses rule_gate_apply() entirely
      // (see horn_debug_listen's contract in horn.h) so the whole clip plays,
      // not just up to HORN_BURST_MAX_MS - this is not the production path
      // and its timing/cooldown behavior means nothing for Stage D.
      const uint8_t track_id = read_track_id(now_ms);
      Serial.print("[firetest] listen: firing track ");
      Serial.print(track_id);
      Serial.println(" (full duration, no cooldown/burst-cap)");
      horn_debug_listen(track_id, FIRE_TEST_HORN_GAIN_PCT, FIRE_TEST_HORN_LISTEN_DURATION_MS);
      Serial.println("[firetest] listen: done");
      break;
    }
    case fire_test_target::kListenByFile: {
      // Stage C, by-name variant of kListen - see kListenByFile's contract
      // in fire_test.h for why this exists alongside the by-index path.
      Serial.println("[firetest] filename (no leading /)? (blank/timeout = nothing sent)");
      char filename[FIRE_TEST_AT_LINE_MAX_LEN];
      if (!read_line_blocking(Serial, filename, sizeof(filename), FIRE_TEST_AT_LINE_TIMEOUT_MS,
                               now_ms) ||
          filename[0] == '\0') {
        Serial.println("[firetest] listen_by_file: no filename typed, nothing sent");
        break;
      }
      Serial.print("[firetest] listen_by_file: firing /");
      Serial.print(filename);
      Serial.println(" (full duration, no cooldown/burst-cap)");
      horn_debug_listen_file(filename, FIRE_TEST_HORN_GAIN_PCT, FIRE_TEST_HORN_LISTEN_DURATION_MS);
      Serial.println("[firetest] listen_by_file: done");
      break;
    }
    case fire_test_target::kHelp:
    case fire_test_target::kNone:
      print_menu();
      break;
  }
}
