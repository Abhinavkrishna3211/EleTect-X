// See uart_share.h and ADR 0029.

#include "uart_share.h"

#include "Arduino.h"
#include "config.h"

namespace {

uart_owner g_owner = uart_owner::kDfplayer;
uint32_t g_switch_count = 0;

#if UART_SHARE_ENABLED
void drain_rx() {
  while (UART_SHARE_SERIAL.available() > 0) {
    UART_SHARE_SERIAL.read();
  }
}
#endif

}  // namespace

int uart_share_select_level(uart_owner owner) {
  return owner == uart_owner::kLora ? UART_SHARE_SELECT_LORA : UART_SHARE_SELECT_DFPLAYER;
}

uint32_t uart_share_baud(uart_owner owner) {
  return owner == uart_owner::kLora ? LORA_UART_BAUD : DFPLAYER_UART_BAUD;
}

void uart_share_init() {
  g_owner = uart_owner::kDfplayer;
  g_switch_count = 0;
#if UART_SHARE_ENABLED
  pinMode(UART_SHARE_SELECT_PIN, OUTPUT);
  digitalWrite(UART_SHARE_SELECT_PIN, uart_share_select_level(uart_owner::kDfplayer));
#endif
  UART_SHARE_SERIAL.begin(uart_share_baud(uart_owner::kDfplayer));
}

bool uart_share_acquire(uart_owner owner) {
#if UART_SHARE_ENABLED
  if (owner == g_owner) {
    return true;
  }
  // Finish the outgoing module's last command before the switch cuts its RX
  // line, or it receives half an AT string.
  UART_SHARE_SERIAL.flush();
  digitalWrite(UART_SHARE_SELECT_PIN, uart_share_select_level(owner));
  delay(UART_SHARE_SWITCH_SETTLE_MS);
  // DFPlayer and E5 run different bauds (115200 vs 9600), so the port is
  // re-opened for every switch, not just re-routed.
  UART_SHARE_SERIAL.begin(uart_share_baud(owner));
  drain_rx();
  g_owner = owner;
  ++g_switch_count;
  return true;
#else
  return owner == uart_owner::kDfplayer;
#endif
}

uart_owner uart_share_owner() { return g_owner; }

uint32_t uart_share_switch_count() { return g_switch_count; }
