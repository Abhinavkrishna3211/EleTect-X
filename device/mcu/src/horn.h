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
// rule_gate_apply()'s clamp-and-cooldown. Blocks for four
// DFPLAYER_AT_COMMAND_GAP_MS send gaps plus HORN_AMP_ENABLE_DELAY_MS plus the
// resolved duration - all bounded, documented delays, not unbounded hardware
// waits. At the HORN_BURST_MAX_MS clamp that is ~3.8 s, which is the figure
// the reflex loop calling this must budget for.
horn_ack drive_horn(horn_request req, uint32_t now_ms);

// Bench-only debug helper: runs the identical fire/stop sequence as
// drive_horn(), but bypasses rule_gate_apply() entirely - no cooldown check,
// no HORN_BURST_MAX_MS clamp - so a Stage C track-identification listen can
// run long enough to hear a whole clip. Never called outside fire_test.cpp's
// FIRE_TEST_HARNESS-gated harness ('l' command); not a production fire path.
void horn_debug_listen(uint8_t track_id, float gain_pct, uint16_t duration_ms);

// Same contract as horn_debug_listen(), but selects the file by exact FAT
// filename (AT+PLAYFILE=/<filename>) instead of FAT-order index (AT+PLAYNUM).
// Exists because AT+QUERY's index/filename readback proved unreliable on this
// unit (HANDOVER.md) - playing a known filename directly is the only way to
// pin an identification to a specific file rather than a hard-to-verify FAT
// slot. filename excludes the leading '/'. Same bench-only, FIRE_TEST_HARNESS
// -gated caveat as horn_debug_listen().
void horn_debug_listen_file(const char *filename, float gain_pct, uint16_t duration_ms);

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

// Same contract for "AT+PLAYFILE=/<filename>\r\n" (filename excludes the
// leading '/' - it is prepended here to match the DFR0768's absolute-path
// requirement). Content filenames run long (Freesound source names easily
// exceed 60 chars), so callers must size buf accordingly - this only fails
// (false, buf[0] left at NUL) if buf_len is too small for the whole command.
bool horn_at_playfile_command(const char *filename, char *buf, size_t buf_len);

// Same contract for "AT+PLAYMODE=<n>\r\n" (DFR0768: 1 single-loop, 2 all-loop,
// 3 play-once-then-pause, 4 random, 5 folder-loop). The horn wants mode 3 so a
// burst plays exactly once and stops itself; the module does not reliably keep
// this across a power cycle (DFRobot forum "DFPlayer Pro Playmode Resets") and
// a single send is not verified to land (dfplayer_send() does not check for an
// OK ack), so it is re-sent before every fire rather than assumed to stick.
bool horn_at_playmode_command(uint8_t mode, char *buf, size_t buf_len);

// Same contract for "AT+PROMPT=ON\r\n" / "AT+PROMPT=OFF\r\n". Sent OFF before
// every fire (same not-verified-to-stick reasoning as horn_at_playmode_command)
// to suppress the module's built-in confirmation beep, which would otherwise
// play through the SUH-15 ahead of the deterrence clip.
bool horn_at_prompt_command(bool enabled, char *buf, size_t buf_len);

#endif  // ACTUATORS_HORN_H
