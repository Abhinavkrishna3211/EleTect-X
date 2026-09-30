// Grove LoRa-E5 AT-command OTAA join state machine (ADR 0002, IN865 only -
// 868 MHz is illegal in India, CONTEXT.md 8).
//
// Non-blocking: lora_service() is polled from loop() and advances one step
// per call, so a slow or unresponsive module never stalls the reflex loop.
// See mac.cpp for the AT command sequence and its source citation.

#ifndef LORA_MAC_H
#define LORA_MAC_H

#include <cstdint>

#include "uplink.h"

enum class lora_join_state {
  kIdle,
  kProbing,
  kReadingDevEui,
  kSettingMode,
  kSettingRegion,
  kSettingAppEui,
  kLoadingKey,
  kSettingPort,
  kJoining,
  kJoined,   // on the network; sends queued uplinks from here
  kSending,  // one AT+(C)MSGHEX exchange in flight
  kFailed,
};

// Resets the join state machine and empties the uplink queue. The port
// itself is opened by uart_share_init(). Does not block on the module.
void lora_init();

// Advances the state machine by at most one step; call every loop()
// iteration. Handles per-command timeout and bounded retry with backoff
// internally - never blocks for LORA_JOIN_TIMEOUT_MS in one call.
void lora_service(uint32_t now_ms);

// Current join state, for state_machine.cpp / report_system_status.
lora_join_state lora_get_state();

// True once OTAA join has succeeded, including while a frame is being sent.
// Mirrors report_system_status's lora_joined field (schema.md).
bool lora_joined();

// Queues a detection event as a confirmed uplink (ADR 0031). Returns false
// if the queue is full of events already. Safe to call before the join
// completes - the frame waits for it.
bool lora_queue_event(const uplink_event &ev);

// Queues a status frame as an unconfirmed uplink. Returns false if the queue
// is full. lora_service() calls this itself on the heartbeat once a status
// source is set; exposed for tests and for an on-demand status.
bool lora_queue_status(const uplink_status &st);

// Where the heartbeat gets its status fields. Set once from setup(); with
// none set, no heartbeat is sent.
void lora_set_status_source(uplink_status (*source)(uint32_t now_ms));

// Frames waiting for the radio, including one in flight.
uint8_t lora_queue_depth();

// Frames the radio confirmed sent (ACKed, for a confirmed frame) and frames
// given up on, since lora_init(). For the console and tests.
uint32_t lora_uplinks_sent();
uint32_t lora_uplinks_dropped();

#endif  // LORA_MAC_H
