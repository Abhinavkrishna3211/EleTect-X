// USART1 (D0/D1) time-share between the DFPlayer PRO and the LoRa-E5 through
// a 74HC4053 analog switch (ADR 0029).
//
// USART1 is the only UART this board exposes on any header, and both modules
// need one. The 74HC4053 routes the MCU's TX/RX to exactly one module at a
// time; UART_SHARE_SELECT_PIN picks which. This file is the sole owner of
// that pin and of every Serial1.begin() call - horn.cpp and mac.cpp ask for
// the port through uart_share_acquire() and never reconfigure it themselves.
//
// Arbitration is by call order, not by a scheduler: the reflex loop is single
// threaded and a horn fire is a blocking sequence, so whoever calls acquire()
// holds the port until someone else does. The horn always wins - a fire takes
// the port on the spot, even mid-LoRa-transaction. The E5's reply to whatever
// it was answering is lost (its TX is disconnected while deselected), and
// mac.cpp restarts the interrupted join from the AT probe without charging a
// retry. A lost AT reply costs a few seconds of join progress; a delayed horn
// costs a deterrence.
//
// In a DFPlayer-only build (LORA_ENABLED 0), init opens Serial1 at
// DFPLAYER_UART_BAUD, the select pin is never touched, acquire(kDfplayer) is
// a no-op and acquire(kLora) refuses.

#ifndef UART_SHARE_H
#define UART_SHARE_H

#include <cstdint>

enum class uart_owner : uint8_t {
  kDfplayer = 0,
  kLora = 1,
};

// Pure helpers - no I/O, host-tested.
int uart_share_select_level(uart_owner owner);
uint32_t uart_share_baud(uart_owner owner);

// One-time setup from setup(): drives the select line to the DFPlayer (when
// enabled) and opens Serial1 at the DFPlayer's baud. The DFPlayer is the boot
// owner so a first fire never pays for a switch.
void uart_share_init();

// Routes USART1 to `owner` if it is not already there: waits for any queued
// TX to finish, moves the select line, re-opens Serial1 at that module's baud
// and drops whatever the previous module left in the RX buffer. Returns false
// only when the share is disabled and `owner` is not the DFPlayer.
bool uart_share_acquire(uart_owner owner);

uart_owner uart_share_owner();

// Incremented on every actual switch. Lets a caller holding a multi-step
// exchange (mac.cpp) tell that the port was taken away in between.
uint32_t uart_share_switch_count();

#endif  // UART_SHARE_H
