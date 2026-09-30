// AT command sequence source: Seeed Studio, "LoRa-E5 AT Command
// Specification V1.0" PDF
// (https://files.seeedstudio.com/products/317990687/res/LoRa-E5+AT+Command+Specification_V1.0+.pdf).
// Checked line-by-line against that manual's text layer: sections 4.23
// (MODE), 4.13 (DR), 3.9 (Band Specific Limitation), 4.20 (KEY), 4.3 (ID),
// 4.11 (PORT), 4.24 (JOIN), 4.5-4.8 (MSG/CMSG/MSGHEX/CMSGHEX, including
// 4.5.2's error lines). Exact response strings below are quoted from the
// manual; see each state's comment for the section cited.
//
// The JOIN success string is "+JOIN: Done" (4.24's worked example -
// "+JOIN: Starting" / "+JOIN: NORMAL" / "+JOIN: NetID ... DevAddr ..." /
// "+JOIN: Done"), not "Network joined", which appears nowhere in the manual.
// A failed join prints "+JOIN: Join failed", and the module also ends that
// exchange with a Done line, so the failure is acted on as soon as its own
// line arrives and whatever follows is discarded.
//
// IN865 only (ADR 0002) - 868 MHz is illegal in India (CONTEXT.md 8).
// Never logs LORA_APP_KEY.
//
// LORA_SERIAL is shared with the DFPlayer through a 74HC4053 (uart_share.h,
// ADR 0029). Every state that talks to the E5 claims the port first, and a
// horn fire can take it back at any moment. When that happens with a command
// outstanding, the E5's reply went to a disconnected wire: a join step
// restarts from the bare AT probe, and an uplink goes back to the front of
// the queue and is re-sent with the same seq (ADR 0031) - neither is charged
// as a failure.

#include "mac.h"

#include <cstdio>
#include <cstring>

#include "Arduino.h"
#include "config.h"
#include "secrets.h"
#include "uart_share.h"

namespace {

struct queued_frame {
  uint8_t bytes[LORA_UPLINK_MAX_LEN];
  uint8_t len;
  bool confirmed;
  bool is_event;
  uint8_t attempts;  // failed sends so far
};

lora_join_state g_state = lora_join_state::kIdle;
uint32_t g_step_start_ms = 0;
uint8_t g_retry_count = 0;

// A command is outstanding and its reply has not been seen yet. False while
// a step waits out a backoff before re-sending.
bool g_awaiting = false;
uint32_t g_resend_at_ms = 0;

char g_rx_buf[LORA_RESPONSE_MAX_LEN];
size_t g_rx_len = 0;
bool g_line_ready = false;

// uart_share_switch_count() when the outstanding command went out.
uint32_t g_step_switch_count = 0;

queued_frame g_queue[LORA_UPLINK_QUEUE_LEN];
uint8_t g_queue_len = 0;
uint8_t g_seq = 0;
uint32_t g_next_send_at_ms = 0;
bool g_ack_seen = false;
uint32_t g_sent = 0;
uint32_t g_dropped = 0;

uplink_status (*g_status_source)(uint32_t) = nullptr;
bool g_status_due = false;
uint32_t g_last_status_ms = 0;

// Wrap-safe "now is at or past `at`" for millis() timestamps.
bool due(uint32_t now_ms, uint32_t at_ms) {
  return static_cast<int32_t>(now_ms - at_ms) >= 0;
}

// Sends one AT command line. Drops anything already in the RX buffer first -
// a late line from an earlier exchange must not be read as this command's
// reply - and resets the per-step line buffer and timer. Never blocks
// waiting for a reply; poll_line() drains it on later service() calls.
void send_command(const char *cmd, uint32_t now_ms) {
  while (LORA_SERIAL.available() > 0) {
    LORA_SERIAL.read();
  }
  g_rx_len = 0;
  g_rx_buf[0] = '\0';
  g_line_ready = false;
  LORA_SERIAL.print(cmd);
  LORA_SERIAL.print("\r\n");
  g_step_start_ms = now_ms;
  g_step_switch_count = uart_share_switch_count();
  g_awaiting = true;
}

// Drains whatever the E5 has sent into g_rx_buf and returns true once a
// whole line (up to '\n') is there. One line at a time: the next call starts
// a fresh line, so a multi-line reply such as JOIN's is matched line by line
// rather than piling up until the buffer fills. A line longer than the
// buffer is still consumed to its newline and matched on what fit.
bool poll_line() {
  if (g_line_ready) {
    g_rx_len = 0;
    g_rx_buf[0] = '\0';
    g_line_ready = false;
  }
  while (LORA_SERIAL.available() > 0) {
    const char c = static_cast<char>(LORA_SERIAL.read());
    if (c == '\n') {
      g_line_ready = true;
      return true;
    }
    if (c == '\r') continue;
    if (g_rx_len + 1 < LORA_RESPONSE_MAX_LEN) {
      g_rx_buf[g_rx_len++] = c;
      g_rx_buf[g_rx_len] = '\0';
    }
  }
  return false;
}

bool rx_contains(const char *needle) {
  return std::strstr(g_rx_buf, needle) != nullptr;
}

// The command each join step sends, and the reply prefix that completes it.
// Returns false for states that have no command of their own.
bool join_step_command(lora_join_state state, char *cmd, size_t cap, const char **expect) {
  switch (state) {
    case lora_join_state::kProbing:
      // Manual sec 5 (Error Code) worked examples: "+AT: OK".
      std::snprintf(cmd, cap, "AT");
      *expect = "OK";
      return true;
    case lora_join_state::kReadingDevEui:
      // Manual sec 4.3 (ID): "+ID: DevEui, xx:xx:...". DevEUI is not secret
      // but is not logged either - the step only confirms the module is
      // alive and addressable.
      std::snprintf(cmd, cap, "AT+ID=DevEui");
      *expect = "DevEui";
      return true;
    case lora_join_state::kSettingMode:
      // Manual sec 4.23 (MODE): "+MODE: LWOTAA" - no "OK" in it.
      std::snprintf(cmd, cap, "AT+MODE=LWOTAA");
      *expect = "+MODE: LWOTAA";
      return true;
    case lora_join_state::kSettingRegion:
      // Manual sec 4.13.2 (Data Rate Scheme): "+DR: IN865 DR0 ...". No
      // channel-mask step follows: sec 3.9.1 restricts AT+CH/AT+RXWIN1 to
      // US915/AU915/CN470, and IN865 is not one of them.
      std::snprintf(cmd, cap, "AT+DR=IN865");
      *expect = "+DR:";
      return true;
    case lora_join_state::kSettingAppEui:
      // Manual sec 4.3 (ID), quoted per its set example.
      std::snprintf(cmd, cap, "AT+ID=AppEui,\"%s\"", LORA_APP_EUI);
      *expect = "+ID: AppEui";
      return true;
    case lora_join_state::kLoadingKey:
      // Manual sec 4.20 (KEY): "+KEY: APPKEY <key>". The key comes from the
      // gitignored secrets.h and is never logged.
      std::snprintf(cmd, cap, "AT+KEY=APPKEY,\"%s\"", LORA_APP_KEY);
      *expect = "+KEY:";
      return true;
    case lora_join_state::kSettingPort:
      // Manual sec 4.11 (PORT): "+PORT: <n>". Every (C)MSGHEX after this
      // goes out on it.
      std::snprintf(cmd, cap, "AT+PORT=%d", LORA_UPLINK_FPORT);
      *expect = "+PORT:";
      return true;
    case lora_join_state::kJoining:
      // Manual sec 4.24 (JOIN); replies handled in lora_service().
      std::snprintf(cmd, cap, "AT+JOIN");
      *expect = "+JOIN: Done";
      return true;
    default:
      return false;
  }
}

void start_step(lora_join_state state, uint32_t now_ms) {
  char cmd[96];
  const char *expect = nullptr;
  g_state = state;
  if (join_step_command(state, cmd, sizeof(cmd), &expect)) {
    send_command(cmd, now_ms);
  }
}

lora_join_state next_join_step(lora_join_state state) {
  switch (state) {
    case lora_join_state::kProbing:
      return lora_join_state::kReadingDevEui;
    case lora_join_state::kReadingDevEui:
      return lora_join_state::kSettingMode;
    case lora_join_state::kSettingMode:
      return lora_join_state::kSettingRegion;
    case lora_join_state::kSettingRegion:
      return lora_join_state::kSettingAppEui;
    case lora_join_state::kSettingAppEui:
      return lora_join_state::kLoadingKey;
    case lora_join_state::kLoadingKey:
      return lora_join_state::kSettingPort;
    default:
      return lora_join_state::kJoining;
  }
}

void enter_failed(uint32_t now_ms) {
  g_state = lora_join_state::kFailed;
  g_awaiting = false;
  g_step_start_ms = now_ms;
}

// Charges one failure against the join's retry budget. Within budget the
// same step is re-sent after `delay_ms` (0 = right away); past it the
// machine drops to kFailed and waits out a longer backoff there.
void charge_join_retry(uint32_t now_ms, uint32_t delay_ms) {
  ++g_retry_count;
  if (g_retry_count > LORA_JOIN_MAX_RETRIES) {
    enter_failed(now_ms);
    return;
  }
  if (delay_ms == 0) {
    start_step(g_state, now_ms);
  } else {
    g_awaiting = false;
    g_resend_at_ms = now_ms + delay_ms;
  }
}

void enter_joined(uint32_t now_ms) {
  g_state = lora_join_state::kJoined;
  g_awaiting = false;
  g_retry_count = 0;
  g_next_send_at_ms = now_ms;
  g_status_due = true;
}

void pop_front() {
  for (uint8_t i = 1; i < g_queue_len; ++i) {
    g_queue[i - 1] = g_queue[i];
  }
  if (g_queue_len > 0) --g_queue_len;
}

// The frame at the front of the queue went out and, if confirmed, was
// ACKed.
void finish_send_ok(uint32_t now_ms) {
  pop_front();
  ++g_sent;
  g_state = lora_join_state::kJoined;
  g_awaiting = false;
  g_next_send_at_ms = now_ms;
}

// The front frame failed. `permanent` drops it at once (a length error will
// not fix itself); otherwise it is retried with a growing delay until
// LORA_UPLINK_MAX_ATTEMPTS.
void finish_send_failed(uint32_t now_ms, bool permanent) {
  queued_frame &f = g_queue[0];
  ++f.attempts;
  const uint32_t delay_ms = LORA_UPLINK_RETRY_BASE_MS * f.attempts;
  if (permanent || f.attempts >= LORA_UPLINK_MAX_ATTEMPTS) {
    pop_front();
    ++g_dropped;
  }
  g_state = lora_join_state::kJoined;
  g_awaiting = false;
  g_next_send_at_ms = now_ms + delay_ms;
}

void start_send(uint32_t now_ms) {
  const queued_frame &f = g_queue[0];
  char cmd[16 + 2 * LORA_UPLINK_MAX_LEN];
  if (!uplink_at_command(f.bytes, f.len, f.confirmed, cmd, sizeof(cmd))) {
    // Cannot happen for a frame lora_queue_* accepted; drop rather than
    // wedge the queue on it.
    pop_front();
    ++g_dropped;
    return;
  }
  g_ack_seen = false;
  g_state = lora_join_state::kSending;
  send_command(cmd, now_ms);
}

// Whether this service() call will exchange bytes with the E5 and so needs
// the port. Nothing to send, a backoff wait, or kFailed leave it with the
// DFPlayer (ADR 0029 B.3).
bool needs_port(uint32_t now_ms) {
  switch (g_state) {
    case lora_join_state::kIdle:
    case lora_join_state::kSending:
      return true;
    case lora_join_state::kJoined:
      return g_queue_len > 0 && due(now_ms, g_next_send_at_ms);
    case lora_join_state::kFailed:
      return false;
    default:
      return g_awaiting || due(now_ms, g_resend_at_ms);
  }
}

void service_heartbeat(uint32_t now_ms) {
  if (g_status_source == nullptr || !lora_joined()) return;
  if (!g_status_due && (now_ms - g_last_status_ms) < LORA_STATUS_INTERVAL_MS) return;
  if (lora_queue_status(g_status_source(now_ms))) {
    g_status_due = false;
    g_last_status_ms = now_ms;
  }
}

bool enqueue(const uint8_t *bytes, size_t len, bool confirmed, bool is_event) {
  if (len == 0 || len > LORA_UPLINK_MAX_LEN) return false;

  // The front frame is on the air while kSending; never touch it.
  const uint8_t first_free = g_state == lora_join_state::kSending ? 1 : 0;

  if (!is_event) {
    // One status is enough: a newer one replaces a queued one rather than
    // queueing behind it.
    for (uint8_t i = first_free; i < g_queue_len; ++i) {
      if (!g_queue[i].is_event) {
        for (uint8_t j = i + 1; j < g_queue_len; ++j) g_queue[j - 1] = g_queue[j];
        --g_queue_len;
        break;
      }
    }
  }

  if (g_queue_len >= LORA_UPLINK_QUEUE_LEN) {
    if (!is_event) return false;
    // An event outranks a heartbeat: evict the oldest status.
    uint8_t victim = LORA_UPLINK_QUEUE_LEN;
    for (uint8_t i = first_free; i < g_queue_len; ++i) {
      if (!g_queue[i].is_event) {
        victim = i;
        break;
      }
    }
    if (victim == LORA_UPLINK_QUEUE_LEN) return false;
    for (uint8_t j = victim + 1; j < g_queue_len; ++j) g_queue[j - 1] = g_queue[j];
    --g_queue_len;
    ++g_dropped;
  }

  queued_frame &f = g_queue[g_queue_len++];
  std::memcpy(f.bytes, bytes, len);
  f.len = static_cast<uint8_t>(len);
  f.confirmed = confirmed;
  f.is_event = is_event;
  f.attempts = 0;
  return true;
}

}  // namespace

void lora_init() {
  g_state = lora_join_state::kIdle;
  g_retry_count = 0;
  g_awaiting = false;
  g_rx_len = 0;
  g_rx_buf[0] = '\0';
  g_line_ready = false;
  g_queue_len = 0;
  g_seq = 0;
  g_next_send_at_ms = 0;
  g_sent = 0;
  g_dropped = 0;
  g_status_due = false;
  g_last_status_ms = 0;
}

void lora_service(uint32_t now_ms) {
  service_heartbeat(now_ms);

  if (!needs_port(now_ms)) {
    if (g_state == lora_join_state::kFailed &&
        (now_ms - g_step_start_ms) >
            LORA_JOIN_BACKOFF_BASE_MS * (static_cast<uint32_t>(g_retry_count) + 1u)) {
      // Retry budget spent and a full backoff waited out: start again from
      // the top rather than strand the node unjoined for good.
      g_retry_count = 0;
      g_state = lora_join_state::kIdle;
    }
    return;
  }
  if (!uart_share_acquire(uart_owner::kLora)) {
    return;
  }
  if (g_awaiting && uart_share_switch_count() != g_step_switch_count) {
    // The horn had the port since this command went out - its reply is
    // gone. Not a failure of the E5, so nothing is charged.
    g_awaiting = false;
    if (g_state == lora_join_state::kSending) {
      g_state = lora_join_state::kJoined;
      g_next_send_at_ms = now_ms;
    } else {
      g_state = lora_join_state::kIdle;
    }
  }

  switch (g_state) {
    case lora_join_state::kIdle:
      start_step(lora_join_state::kProbing, now_ms);
      break;

    case lora_join_state::kJoined:
      start_send(now_ms);
      break;

    case lora_join_state::kSending:
      // Manual sec 4.5-4.8: "+MSGHEX: Start" ... "+MSGHEX: Done", with
      // "+CMSGHEX: ACK Received" before Done when a confirmed frame was
      // acknowledged, and the sec 4.5.2 error lines in place of Done.
      if (poll_line()) {
        if (rx_contains("ACK Received")) {
          g_ack_seen = true;
        } else if (rx_contains("Please join network first")) {
          // The E5 lost its session (a module reset, most likely). The
          // frame stays at the front and goes out after the rejoin.
          g_awaiting = false;
          g_retry_count = 0;
          start_step(lora_join_state::kProbing, now_ms);
        } else if (rx_contains("Length error")) {
          finish_send_failed(now_ms, true);
        } else if (rx_contains("busy") || rx_contains("No free channel") ||
                   rx_contains("No band") || rx_contains("DR error")) {
          finish_send_failed(now_ms, false);
        } else if (rx_contains("MSGHEX: Done")) {
          if (g_queue[0].confirmed && !g_ack_seen) {
            finish_send_failed(now_ms, false);
          } else {
            finish_send_ok(now_ms);
          }
        }
      } else if ((now_ms - g_step_start_ms) > LORA_UPLINK_TIMEOUT_MS) {
        finish_send_failed(now_ms, false);
      }
      break;

    case lora_join_state::kFailed:
      break;

    case lora_join_state::kJoining:
      if (!g_awaiting) {
        start_step(g_state, now_ms);
      } else if (poll_line()) {
        if (rx_contains("+JOIN: Done") || rx_contains("Joined already")) {
          enter_joined(now_ms);
        } else if (rx_contains("Join failed") || rx_contains("busy")) {
          charge_join_retry(now_ms,
                            LORA_JOIN_BACKOFF_BASE_MS * (static_cast<uint32_t>(g_retry_count) + 1u));
        }
      } else if ((now_ms - g_step_start_ms) > LORA_JOIN_TIMEOUT_MS) {
        charge_join_retry(now_ms, 0);
      }
      break;

    default: {
      // kProbing .. kSettingPort: one command, one expected reply.
      char cmd[96];
      const char *expect = nullptr;
      join_step_command(g_state, cmd, sizeof(cmd), &expect);
      if (!g_awaiting) {
        start_step(g_state, now_ms);
      } else if (poll_line()) {
        if (rx_contains(expect)) {
          start_step(next_join_step(g_state), now_ms);
        }
      } else if ((now_ms - g_step_start_ms) > LORA_AT_TIMEOUT_MS) {
        charge_join_retry(now_ms, 0);
      }
      break;
    }
  }
}

lora_join_state lora_get_state() { return g_state; }

bool lora_joined() {
  return g_state == lora_join_state::kJoined || g_state == lora_join_state::kSending;
}

bool lora_queue_event(const uplink_event &ev) {
  uint8_t bytes[LORA_UPLINK_MAX_LEN];
  const size_t len = uplink_encode_event(ev, g_seq, bytes, sizeof(bytes));
  if (!enqueue(bytes, len, true, true)) return false;
  ++g_seq;
  return true;
}

bool lora_queue_status(const uplink_status &st) {
  uint8_t bytes[LORA_UPLINK_MAX_LEN];
  const size_t len = uplink_encode_status(st, g_seq, bytes, sizeof(bytes));
  if (!enqueue(bytes, len, false, false)) return false;
  ++g_seq;
  return true;
}

void lora_set_status_source(uplink_status (*source)(uint32_t now_ms)) {
  g_status_source = source;
}

uint8_t lora_queue_depth() { return g_queue_len; }

uint32_t lora_uplinks_sent() { return g_sent; }

uint32_t lora_uplinks_dropped() { return g_dropped; }
