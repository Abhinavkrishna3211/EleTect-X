// Horn deterrence driver - sole owner of AUDIO_TRIGGER_PIN,
// HORN_AMP_ENABLE_PIN, and the DFPLAYER_SERIAL AT-command link (config.h).
// No other file may touch either pin or that stream.
//
// See horn.cpp for the fire/stop sequencing rationale (ADR 0003, ADR 0015).

#ifndef ACTUATORS_HORN_H
#define ACTUATORS_HORN_H

#include <cstddef>
#include <cstdint>

// Request to sound the horn for up to duration_ms at up to gain_pct of the
// channel's software-limited gain ceiling (HORN_GAIN_MAX_PCT), playing the
// DFPlayer content at index track_id (AT+PLAYNUM; ADR 0015 Decision B, the
// tier-to-content map lives on the MPU in cognition/config.py). track_id is
// not subject to any MCU clamp - it is a content selector, not a limit - so
// horn_ack does not echo it back.
struct horn_request {
  uint16_t duration_ms;
  float gain_pct;
  uint8_t track_id;
};

// Ack, mirroring gate_result: the caller must inspect this rather than assume
// the request landed as sent. clamped means the values were reduced to fit
// ADR 0003's burst/gain caps and still executed; allowed=false means the
// horn is in cooldown and nothing fired.
struct horn_ack {
  uint16_t duration_ms;
  float gain_pct;
  bool clamped;
  bool allowed;
};

// One-time setup: configures AUDIO_TRIGGER_PIN and HORN_AMP_ENABLE_PIN as
// outputs, amp held in shutdown. Call once from setup().
void horn_init();

// Runs the fire/stop sequence documented at the top of horn.cpp, subject to
// rule_gate_apply()'s clamp-and-cooldown. Blocks for HORN_AMP_ENABLE_DELAY_MS
// (a bounded, documented delay - not an unbounded/hardware wait) plus the
// resolved duration; the reflex loop calling this must expect that.
horn_ack drive_horn(horn_request req, uint32_t now_ms);

// --- Pure DFPlayer helpers (ADR 0015 Decision F) -----------------------------
// No Serial/hardware dependency - the host-testable core, mirroring
// footfall_probability_from_ratio()'s precedent. Unity-tested in
// tests/test_horn_dfplayer.

// Maps a wire gain_pct (0-100, already HORN_GAIN_MAX_PCT-clamped upstream) to
// a DFPlayer AT+VOL level in [0, DFPLAYER_VOL_MAX], rounded to nearest.
uint8_t horn_dfplayer_volume_from_gain_pct(float gain_pct);

// Formats "AT+VOL=<n>\r\n" into buf. Returns false (and leaves buf untouched
// past a NUL at [0]) if buf_len cannot hold the whole string plus its NUL,
// rather than emitting a truncated command the DFPlayer would reject.
bool horn_at_vol_command(uint8_t dfplayer_vol, char *buf, size_t buf_len);

// Same contract for "AT+PLAYNUM=<n>\r\n".
bool horn_at_playnum_command(uint8_t track_id, char *buf, size_t buf_len);

#endif  // ACTUATORS_HORN_H
