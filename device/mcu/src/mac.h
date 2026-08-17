// Grove LoRa-E5 AT-command OTAA join state machine (ADR 0002, IN865 only -
// 868 MHz is illegal in India, CONTEXT.md 8).
//
// Non-blocking: lora_service() is polled from loop() and advances one step
// per call, so a slow or unresponsive module never stalls the reflex loop.
// See mac.cpp for the AT command sequence and its source citation.

#ifndef LORA_MAC_H
#define LORA_MAC_H

#include <cstdint>

enum class lora_join_state {
  kIdle,
  kProbing,
  kReadingDevEui,
  kSettingMode,
  kSettingRegion,
  kSettingAppEui,
  kLoadingKey,
  kJoining,
  kJoined,
  kFailed,
};

// One-time setup: opens LORA_SERIAL at LORA_UART_BAUD. Call once from
// setup(). Does not block on the module responding.
void lora_init();

// Advances the join state machine by at most one step; call every loop()
// iteration. Handles per-command timeout and bounded retry with backoff
// internally - never blocks for LORA_JOIN_TIMEOUT_MS in one call.
void lora_service(uint32_t now_ms);

// Current join state, for state_machine.cpp / report_system_status.
lora_join_state lora_get_state();

// True once OTAA join has succeeded. Mirrors report_system_status's
// lora_joined field (schema.md).
bool lora_joined();

#endif  // LORA_MAC_H
