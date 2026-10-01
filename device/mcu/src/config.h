// EleTect X - MCU configuration.
//
// Single source of every pin assignment, threshold, gain, cooldown and cap on
// the reflex layer (ENGINEERING_CONVENTIONS.md 2). No magic numbers live in
// logic files; if a number matters, it is named here with the reason it holds
// that value.
//
// Pin assignments come from hardware/references/UNO_Q_PINOUT_REFERENCE.md,
// which is a transcription of Arduino's own ABX00162 pinout PDF. Nothing here
// uses the JMISC or JMEDIA advanced headers: they are 1.8 V board-edge
// connectors that need a carrier board we do not have, so they are physically
// inaccessible.

#ifndef CONFIG_H
#define CONFIG_H

// Per-unit overrides. A node can carry a config_local.h next to this file
// (gitignored, never synced over by scripts/sync-to-board.sh) to override any
// #ifndef-guarded default below without editing the shared tree.
#if defined(__has_include)
#if __has_include("config_local.h")
#include "config_local.h"
#endif
#endif

#include <stdint.h>

// ---------------------------------------------------------------------------
// Geophone front-end - ADS1115 + INA333 bench stand-in, on I2C2
// ---------------------------------------------------------------------------
// The field design samples the INA333 output on the STM32's own ADC through
// LPBAM (ADR 0009). Until that lands, an ADS1115 breakout carries the same
// signal over I2C. Both satisfy one contract, read_seismic_window(), and
// nothing above the driver knows which is underneath
// (ENGINEERING_CONVENTIONS.md 1).
//
// Wiring is plain male-female jumpers to the breakout's 0.1" pin header, not
// the Qwiic connector.
//
// Moved off D20/D21 (I2C2, PB10/PB11) onto A4/A5 (I2C3, PC1/PC0) during the
// horn bring-up: the DFPlayer PRO's AT-command link needs a real hardware
// UART, and usart3 - the only one the board overlay routes to a free header
// pin pair - is pinned to exactly D20/D21 (see DFPLAYER_SERIAL below). I2C3
// was free and is enabled in the same overlay, so the geophone moved rather
// than the DFPlayer link, which has no alternative pin pair. This leaves the
// Qwiic connector's I2C4 (PD12/PD13) free for the BME280/MPU-6050 later, same
// as before.
#define GEOPHONE_I2C_SDA_PIN 18  // PC1, A4, I2C3_SDA
#define GEOPHONE_I2C_SCL_PIN 19  // PC0, A5, I2C3_SCL

// `Wire2` is I2C3. The arduino:zephyr core declares Wire/Wire1/Wire2/... in
// the order listed by the board overlay's
// `zephyr,user { i2cs = <&i2c2>, <&i2c4>, <&i2c3>; }`
// (arduino_uno_q_stm32u585xx.overlay): i2c2 is `Wire`, i2c4 is `Wire1`, i2c3
// is `Wire2`. The overlay's i2c3 node pins `i2c3_scl_pc0`/`i2c3_sda_pc1` -
// exactly A5/A4 - confirming this mapping independently of the pin numbers
// above. Re-run the stomp test after this move and confirm continuous,
// plausible, varying ADS1115 differential readings before trusting anything
// downstream - a wrong bus fails every I2C transaction and produces no
// ring-buffer writes at all, the same signature the pre-move `Wire` mapping
// was confirmed against on 2026-08-14.
#define GEOPHONE_I2C_BUS Wire2

// 0x48 is the ADS1115 address with ADDR tied to GND - the breakout's default.
#define ADS1115_I2C_ADDRESS 0x48

// 400 kHz fast mode: at 250 SPS the bus is idle almost all the time, but the
// faster clock keeps each conversion read short enough that the I2C timeout
// below can stay tight.
#define GEOPHONE_I2C_CLOCK_HZ 400000UL

// ADS1115 register addresses and config-register fields (datasheet 9.6).
#define ADS1115_REG_CONVERSION 0x00
#define ADS1115_REG_CONFIG 0x01

#define ADS1115_CFG_OS_SINGLE 0x8000        // start a single conversion
#define ADS1115_CFG_MUX_DIFF_0_1 0x0000     // differential AIN0 - AIN1
#define ADS1115_CFG_PGA_2048MV 0x0400       // +/-2.048 V full scale
#define ADS1115_CFG_MODE_CONTINUOUS 0x0000  // free-running, not single-shot
#define ADS1115_CFG_DR_250SPS 0x00A0        // 250 samples per second
#define ADS1115_CFG_COMP_DISABLE 0x0003     // comparator off, ALERT/RDY unused

// ---------------------------------------------------------------------------
// Seismic bench-only debug flags - MUST be 0 before any field sync
// ---------------------------------------------------------------------------
// Every flag in this section exists to support a bench characterization
// session (the INA333 REF-bias check, or a later Part C2 sensitivity/
// waveform-capture pass) and has no role in the field-deployed reflex
// behaviour. All four must read 0 before running scripts/sync-to-board.sh
// against a node that is actually going in the ground - device/mcu/README.md
// documents the sync/re-sync procedure that flips them back.

// When 1, ADS1115_CONFIG_WORD below samples AIN0 single-ended against board
// GND (ADS1115 datasheet 9.6.3, MUX=100) instead of the field differential
// AIN0-AIN1 pair - ADS1115_CFG_MUX_DIFF_0_1 itself is untouched either way.
// This is the INA333 REF-bias bench check (device/mcu/README.md): with VIN+
// shorted to VIN-, differential mode already rejects the INA333's own bias
// rail, so it cannot show whether that bias is centered; single-ended mode
// reads VOUT directly against GND instead, which is the absolute bias level
// the check needs. Left at 0, ADS1115_CFG_MUX_ACTIVE below resolves to
// ADS1115_CFG_MUX_DIFF_0_1 and the field wiring is unaffected.
#define GEOPHONE_DEBUG_SINGLE_ENDED_AIN0 0

// When 1: state_machine.cpp prints sta/lta/ratio every
// SEISMIC_DEBUG_PRINT_INTERVAL_MS regardless of whether a trigger fires, and
// every existing [trigger] event additionally dumps the raw window buffer as
// CSV volts (scripts/plot_seismic_window.py renders the dump). Both are for
// the later Part C2 sensitivity-characterization pass, not the REF-bias
// check above - independent of GEOPHONE_DEBUG_SINGLE_ENDED_AIN0, either flag
// can be 1 without the other. Left at 0 in the field: the reflex loop
// already prints [trigger] on its own schedule, and a periodic print on top
// of that has no consumer.
#define SEISMIC_DEBUG_VERBOSE 0

// When 1: geophone.cpp prints one raw volts reading per line, gated to
// SEISMIC_SAMPLE_RATE_HZ (not SEISMIC_DEBUG_PRINT_INTERVAL_MS - that 200 ms
// cadence would give a 5 Hz trace, useless for eyeballing a 2-50 Hz
// waveform live). This is pitch/demo tooling: scripts/live_seismic_plot.py
// parses this stream for its top (raw volts) panel and is meant to be run
// with SEISMIC_DEBUG_VERBOSE also set to 1, whose [seismic] sta/lta/ratio
// line feeds the script's bottom panel - the two flags are independent but
// designed to be combined for that script specifically. Wire format is a
// parser contract: exactly one line per sample, bare float, 6 decimals,
// nothing else -
//
//   -0.001250
//
// No [tag] prefix (every other line this firmware prints starts with one,
// so an unprefixed float is already unambiguous) and no timestamp (the host
// script times arrival itself); a label would only cost bytes on a stream
// that already runs continuously at up to SEISMIC_SAMPLE_RATE_HZ. 6 decimals
// matches log_window_csv's existing precision and is what it takes to
// resolve ADS1115_LSB_VOLTS's 62.5 uV LSB - 4 decimals would quantize away
// 3 of every 4 LSB steps. Left at 0 in the field: no consumer, and this
// flag must never read 1 on a node headed for the field, same as the other
// flags in this section.
//
// Second delivery path, same flag: geophone.cpp also pushes every
// SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES-th sample to the MPU over
// Bridge.notify() (device/mpu/main.py's debug_stream_raw_seismic_sample
// handler re-prints it in the same wire format on the MPU's own stdout, so
// `docker logs -f eletect-x-main-1` piped into live_seismic_plot.py's stdin
// mode is a live alternative to the Serial console). This is genuinely a
// second delivery mechanism for the same samples, not a second stream - the
// existing Serial.println path above is untouched. Bridge.notify() is
// fire-and-forget (Arduino_RouterBridge's bridge.h grabs a write mutex and
// returns after a one-way send, never waiting on an MPU reply the way
// Bridge.call() does - confirmed by reading bridge.h directly, not assumed),
// so this cannot stall the reflex loop on an MPU round trip.
#define SEISMIC_DEBUG_STREAM_RAW 0

// Bridge-notify decimation for the second delivery path above: push every
// Nth sample, not every sample. No measured Bridge.notify() RTT backs this
// number - the ping bench (device/mpu/bench/ping) that would measure it has
// never been run against hardware (device/mpu/README.md: "Status: pending
// hardware"), so this is not a tuned value (KNOWN_GAPS). 10 (~25 Hz at the
// nominal 250 SPS SEISMIC_SAMPLE_RATE_HZ) is chosen as a conservative
// default: lighter on the Bridge call than the full sample rate, and
// visually indistinguishable on live_seismic_plot.py's scrolling window.
#define SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES 10

// Rate limit shared by both bench prints above (GEOPHONE_DEBUG_SINGLE_ENDED_
// AIN0's [bias-check] line and SEISMIC_DEBUG_VERBOSE's periodic [seismic]
// line) - fast enough to watch a reading settle at the bench, slow enough
// not to flood a 115200-baud console that other subsystems log to as well.
// INVENTED - no bench session has confirmed this cadence yet (KNOWN_GAPS).
// Not used by SEISMIC_DEBUG_STREAM_RAW above, which gates to
// SEISMIC_SAMPLE_RATE_HZ instead - see that flag's own comment.
#define SEISMIC_DEBUG_PRINT_INTERVAL_MS 200

#if GEOPHONE_DEBUG_SINGLE_ENDED_AIN0
#define ADS1115_CFG_MUX_ACTIVE 0x4000  // single-ended AIN0 vs GND, MUX=100
#else
#define ADS1115_CFG_MUX_ACTIVE ADS1115_CFG_MUX_DIFF_0_1
#endif

// Differential AIN0-AIN1 measures the INA333 output against its own reference
// pin, so the mid-rail bias the instrumentation amp sits on cancels instead of
// eating half the ADC range.
//
// +/-2.048 V full scale gives 62.5 uV per LSB across a differential swing the
// INA333's gain is set to keep inside 2 V. The wider +/-4.096 V range would
// throw away a bit of resolution for headroom the signal never uses.
#define ADS1115_CONFIG_WORD                                            \
  (ADS1115_CFG_MUX_ACTIVE | ADS1115_CFG_PGA_2048MV |                   \
   ADS1115_CFG_MODE_CONTINUOUS | ADS1115_CFG_DR_250SPS |               \
   ADS1115_CFG_COMP_DISABLE)

// Volts per LSB at the +/-2.048 V PGA setting: 2.048 / 32768.
#define ADS1115_LSB_VOLTS 0.0000625f

// 250 SPS is the lowest ADS1115 data rate that still clears Nyquist for the
// 2-50 Hz seismic band (CONTEXT.md 3) with real margin - 5x the top of the
// band, not the bare 2x. Slower rates would alias the 50 Hz edge; faster ones
// burn I2C bandwidth and power for detail the band-pass has already removed.
#define SEISMIC_SAMPLE_RATE_HZ 250

// 512 samples = 2.048 s at 250 SPS. Long enough to hold both the STA and LTA
// windows below with room for the trigger to land inside the window; short
// enough that a snapshot copy costs 2 KB of SRAM, not 20.
#define SEISMIC_WINDOW_SAMPLES 512

// A single I2C transaction that has not completed in 10 ms has failed, not
// stalled: at 400 kHz a 2-byte read is ~100 us, so this is 100x margin. On
// expiry read_seismic_window() returns a zero-filled array and clears
// geophone_ok, per the contract in device/mpu/bridge/schema.md.
#define GEOPHONE_I2C_TIMEOUT_MS 10

// If the ring buffer has not taken on a full window's worth of fresh samples
// within 1.5x the time that should take, the sampler is not keeping up and the
// window is stale. Same failure response as a hard I2C timeout: zero-filled
// array, geophone_ok cleared, event logged - a degraded window rather than a
// crashed state machine (ENGINEERING_CONVENTIONS.md 7). 3384 ms = 512 samples
// / 226.98 Hz (the same measured field-flag rate STA_SAMPLES/LTA_SAMPLES
// below are grounded against, not the nominal 250 Hz) * 1.5, matching this
// comment's own formula - see docs/KNOWN_GAPS.md's 2026-08-14 entry.
#define GEOPHONE_WINDOW_STALE_MS 3384

// ---------------------------------------------------------------------------
// Camera-labelled seismic capture (ADR 0035)
// ---------------------------------------------------------------------------
// When 1: geophone.cpp streams every accepted ADC sample to the MPU in
// batches over Bridge.notify("report_seismic_batch") (seismic_capture.h), so
// the MPU can store the raw ground motion and let the camera label it
// afterwards. This is the dataset the species-specific footfall model was
// deferred for want of - CONTEXT.md 3 - and it is collected on every vision
// watch, including the sub-threshold ones, because an animal too light to
// trigger STA/LTA is itself the training signal.
//
// Distinct from SEISMIC_DEBUG_STREAM_RAW above, which is bench tooling: that
// one decimates to a human-watchable rate and sends one float per notify for
// a live plot. This one is lossless, batched, carries the sample index so
// gaps are detectable, and is meant to run unattended for whole nights.
//
// Left at 0 until a live session registers the MPU-side handler. The MPU can
// only receive this once device/mpu/main.py's Bridge.provide() for it is
// uncommented, and that is one registration per hardware session under
// docs/DEVICE_DEVELOPMENT_WORKFLOW.md 3 - the same gate get_system_state and
// report_acoustic_event are already waiting behind. Streaming into a handler
// that is not registered would spend link budget to produce
// "method not available" and nothing else.
//
// Guarded so platformio.ini's native_seismic_capture env (and config_local.h)
// can force it on. That env exists for one reason: at 0 the Bridge.notify()
// call in geophone.cpp is not compiled at all, so without a build that sets
// this the only line that actually puts a batch on the wire would never see
// a compiler.
#ifndef SEISMIC_CAPTURE_ENABLED
#define SEISMIC_CAPTURE_ENABLED 0
#endif

// Samples per Bridge.notify(). Three constraints meet here:
//
//  - It must fit BRIDGE_MAX_MESSAGE_BYTES, which seismic_capture.h's
//    seismic_capture_encoded_bytes() static_asserts. At 32 the worst-case
//    notify is 133 of the 256 bytes available.
//  - It must not crowd the actuator calls off lpuart1. 32 samples is 128 ms
//    at SEISMIC_SAMPLE_RATE_HZ, so ~7.8 notifies/s at 133 B = ~1.0 kB/s, or
//    about 9% of the 115200 bps link - leaving the drive_horn/drive_led acks
//    mid-encounter the headroom they need.
//  - It should divide SEISMIC_WINDOW_SAMPLES evenly (16 batches per window),
//    so a batch boundary never falls inside a window boundary and the MPU's
//    stitching has one alignment case instead of two.
//
// 64 also fits the first two (227 B worst case, ~5% of the link) and halves
// the notify count, so it is the tempting choice. It is not taken, because
// the two numbers above are *arithmetic*, not measurements: nothing in this
// repo has ever encoded a Bridge message and counted the bytes, and the
// penalty for being wrong is not an error - an oversized notify is dropped
// silently, so a few bytes of drift would present as a geophone that simply
// stopped reporting, discovered at the bench weeks later with the nights of
// data already gone. 32 buys 123 bytes of margin for 1% more link, which is
// the right side of that trade until someone measures a real frame.
#define SEISMIC_CAPTURE_BATCH_SAMPLES 32

// ---------------------------------------------------------------------------
// Manual fire-test harness - MUST be 0 before any field sync
// ---------------------------------------------------------------------------
// Serial-command-triggered single fire of horn/LED/IR for hardware bring-up
// verification (docs/specs/mcu-fire-test-harness.md). Human types a digit
// into App Lab's Serial Monitor; nothing fires without that keystroke, so
// this has no autonomous trigger path. Still gated to 0 by default, same
// discipline as the seismic bench flags above: the point of field builds is
// that bench-only surface area doesn't exist in them.
//
// Set to 1 for the horn bring-up session (adds the raw-AT console mode,
// fire_test.cpp) - MUST be back to 0 before any field sync.
//
// 7 Sept, system audit: reset to 0. No MCU reflash is planned for tonight's
// test (only device/mpu Python files are pushed via scp to the bind-mounted
// /app tree), so this had no live effect either way - closing it now just
// clears a real, previously-flagged-but-unexecuted HANDOVER.md todo before
// it can be forgotten and shipped in a future flash.
#define FIRE_TEST_HARNESS 0

// Bench defaults - short and conservative. The real safety backstop is still
// rule_gate_apply()'s per-actuator caps (HORN_GAIN_MAX_PCT etc. above); these
// are just sane starting points for a desk-bench test, not a duplicate
// limit.
#define FIRE_TEST_HORN_DURATION_MS 2500  // long enough to identify the clip by ear; still under HORN_BURST_MAX_MS=3000
#define FIRE_TEST_HORN_GAIN_PCT 30.0f     // under HORN_GAIN_MAX_PCT=60, desk-volume not field-volume - reset from the 25% by-ear-identification bring-up value per HOME_TEST_MODE plan prerequisite 3. A 6 Sept gain-staging trial (60 w/ VOL_L turned down) and a same-day DFPlayer-direct-to-horn isolation test (10, then 4 for track 4/5 at night) both ran temporarily off this default - reverted after each. The isolation test was decisive: all 5 tracks played clean (no siren, no hum) straight off DFPlayer's own onboard amp with the TPA3116/XH-M543 fully out of the circuit, so both artifacts are isolated to that amp board, not DFPlayer/UNO Q/horn/wiring. Only the fire_test.cpp console harness reads this constant, drive_horn's Bridge path always takes gain_pct from the caller
#define FIRE_TEST_HORN_LISTEN_DURATION_MS 15000  // 'l' command only (horn_debug_listen) - generous ceiling for any clip length; DFPLAYER_PLAYMODE_SINGLE stops the module itself once the track ends, so holding the amp open longer than the clip just plays silence, not a repeat
#define FIRE_TEST_HORN_TRACK_ID 1        // default track if the harness's track prompt times out/is skipped; AT+PLAYNUM index, content TBD by ear (AT+QUERY=5 unreliable on this unit)
#define FIRE_TEST_LED_DURATION_MS 1000
#define FIRE_TEST_LED_GAIN_PCT 50.0f
#define FIRE_TEST_IR_DURATION_MS 200     // under IR_PULSE_MAX_MS=500
#define FIRE_TEST_IR_GAIN_PCT 100.0f     // IR is invisible, thermal is the only real constraint

// Raw-AT console mode (fire_test.cpp 'a' command, horn bring-up). Bounded
// waits, same convention as the actuator durations above: long enough for a
// human to type a short AT line and for the DFR0768 to answer, short enough
// that a dropped connection doesn't hang the harness indefinitely.
#define FIRE_TEST_AT_LINE_TIMEOUT_MS 15000UL
#define FIRE_TEST_AT_REPLY_TIMEOUT_MS 1000UL
#define FIRE_TEST_AT_LINE_MAX_LEN 96  // Freesource content filenames run long -
                                      // "AT+PLAYFILE=/788025__realsquink__intense-angry-bee-swarm-stereo.wav"
                                      // alone is 67 chars; 64 silently truncated it (dropped ".wav"),
                                      // producing a malformed path the module ack'd OK without acting on

// ---------------------------------------------------------------------------
// HOME_TEST_MODE - backyard test build ONLY - MUST be 0 before any field sync
// ---------------------------------------------------------------------------
// Second operating mode for a supervised one-night backyard wild-boar test.
// This is NOT a field flag and must never read 1 on a node headed for the
// field, same discipline as every other flag in this file marked that way.
//
// The MPU half of this toggle is HOME_TEST_MODE in
// device/mpu/services/config.py (env-var-backed there, since the MPU has an
// environment to read and the goal is that nobody ships to the field still
// in test mode). The two flags are deliberately INDEPENDENT - no new
// cross-process command syncs them. Building a new MCU<->MPU protocol under
// time pressure to keep two flags in lockstep would be a bigger reliability
// risk on the night this matters than the two flags ever were; each side
// just prints which mode it came up in, loudly, at boot, so a mismatch is
// visible on the console rather than silently wrong.
//
// What this flag changes: it turns on the existing bench debug-stream flags
// below, so the STA/LTA feature stream (not just the binary trigger) is
// captured for the whole session, for later offline correlation against the
// MPU's vision detection log. It does NOT touch STA/LTA trigger logic or
// its thresholds (see the STA/LTA section right below - untouched), and it
// does NOT touch the deterrence fire path - drive_horn/drive_led/pulse_ir
// and the tier/rotation logic that picks them are identical in both modes.
#define HOME_TEST_MODE 0

#if HOME_TEST_MODE
// Overrides, in force only in a HOME_TEST_MODE build. Each overrides a bench
// flag defined above in this file - see that flag's own comment for what it
// does and why its field default is 0.

// Full STA/LTA feature stream (sta/lta/ratio), not just the binary trigger.
// Field mode logs [trigger] events only; this is the continuous time series
// tonight's dataset needs to let ml/seismic/'s missing footfall classifier
// be trained against real labelled ground truth instead of a hand-tuned
// ratio threshold.
#undef SEISMIC_DEBUG_VERBOSE
#define SEISMIC_DEBUG_VERBOSE 1

// Raw geophone volts, relayed to the MPU over the existing
// debug_stream_raw_seismic_sample Bridge.notify() path (no new message
// type - see device/mpu/main.py's handler, which appends to a CSV under
// this same flag rather than adding a third provide()). The direct
// Serial.println half of this same flag is separately suppressed below
// (geophone.cpp) because it shares lpuart1 with the Bridge link that
// drive_led/pulse_ir need, and a 250 Hz console flood on that link is not
// something this project has ever run concurrently with a live actuator
// call.
#undef SEISMIC_DEBUG_STREAM_RAW
#define SEISMIC_DEBUG_STREAM_RAW 1

// Denser Bridge relay than the bench default of 10 (~25 Hz): 2 gives
// ~113 Hz at the nominal 250 SPS SEISMIC_SAMPLE_RATE_HZ, still comfortably
// above the STA/LTA band's ~50 Hz edge and half the Bridge traffic of the
// full sample rate, which has never been benchmarked end to end.
#undef SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES
#define SEISMIC_STREAM_BRIDGE_EVERY_N_SAMPLES 2
#endif  // HOME_TEST_MODE

// ---------------------------------------------------------------------------
// STA/LTA footfall trigger
// ---------------------------------------------------------------------------
// STA_SAMPLES/LTA_SAMPLES and STA_LTA_TRIGGER_RATIO (field branch, below) are
// now grounded, not generic convention - see docs/KNOWN_GAPS.md's 2026-08-14
// entry for the full derivation. Sample counts were checked against the real
// measured geophone_service() rate (226.98 Hz on a lean field-flag build, not
// the nominal 250 Hz) against literature targets from Wijayakulasooriya et
// al. (arXiv:2406.05140) and Trnkoczy/Guralp STA/LTA sizing guidance.
// STA_LTA_TRIGGER_RATIO was checked against a real human stomp test on
// hardware (quiet floor 1.03-1.13, stomp ratio 4.60, real waveform capture
// confirming a genuine ~65x amplitude transient). STA_LTA_DETRIGGER_RATIO was
// removed 2026-08-15 as dead code - see the note where it used to be defined,
// below, and docs/KNOWN_GAPS.md.

// 25 samples: at the measured 226.98 Hz field rate this is ~110 ms, inside
// the ~40-150 ms literature ballpark for a few periods of a ~26 Hz elephant
// footfall (~38 ms/period, Wijayakulasooriya et al.). Short enough to rise
// sharply on a single footfall impact rather than average it away.
#define STA_SAMPLES 25

// 250 samples: at the measured 226.98 Hz field rate this is ~1.10 s, clearing
// the >=0.5 s literature floor (period of the 2 Hz edge of the analog 2-50 Hz
// band-pass) with ~2.2x margin. The long-term average is the local noise
// floor the short-term average is compared against. Bounded by the 2.048 s
// bench window; the LPBAM swap should extend it well past 1 s (KNOWN_GAPS).
#define LTA_SAMPLES 250

// Demo mode: lowers the trigger ratio so a pen tap or light finger tap near
// the geophone reads as a trigger for a live audience, instead of requiring
// a real stomp-strength impact. MUST be set back to 0 before field
// deployment - these ratios are unvalidated placeholders to begin with (see
// WARNING above) and the demo values below are tuned for visible drama, not
// for rejecting ambient field noise (wind, vehicles, footsteps near but not
// at the sensor).
#define SEISMIC_DEMO_MODE 0

#if SEISMIC_DEMO_MODE
// Ratio at which a window is declared a trigger.
#define STA_LTA_TRIGGER_RATIO 2.0f
#else
// Ratio at which a window is declared a trigger. Validated on hardware
// 2026-08-14: a real human stomp test (see device/mcu/README.md's Bench
// stomp test procedure) measured a quiet-floor ratio of 1.03-1.13 over ~89 s
// (before and after the stomp) and a real stomp ratio of 4.60, with a
// captured raw window showing a genuine ~65x amplitude transient over the
// noise floor. 4.0 clears the observed floor ceiling by ~3.5x and the stomp
// clears 4.0 by ~15% - real margin in both directions, so kept at the value
// already here rather than retuned from a single clean trial.
#define STA_LTA_TRIGGER_RATIO 4.0f
#endif

// STA_LTA_DETRIGGER_RATIO removed 2026-08-15 (docs/KNOWN_GAPS.md): it was
// dead code - state_machine.cpp's kEvent case only ever checked EVENT_MAX_MS
// elapsed, never a ratio, so there was no detrigger logic left to calibrate
// this against. Decision: timeout-only exit from kEvent is judged fine for
// now (EVENT_MAX_MS already bounds how long an event stays "active"), so the
// unused constant was deleted rather than kept indefinitely as an unwired
// placeholder. Revisit as a real feature (exit kEvent early once the ratio
// falls back under some threshold, saving EVENT_MAX_MS-COOLDOWN_MS of
// deterrence latency) only alongside real multi-event stomp data to validate
// a specific value against - see docs/KNOWN_GAPS.md for the full writeup.

// ---------------------------------------------------------------------------
// Footfall probability placeholder - pending ml/seismic TinyML model
// ---------------------------------------------------------------------------
// report_footfall_event (device/mpu/bridge/schema.md) needs a real
// probability, not just the raw STA/LTA ratio - but ml/seismic/ is empty
// today, so there is no trained model to produce one. footfall_features.cpp
// derives an honest saturating placeholder from peak_ratio instead of
// inventing an unrelated number, same labeling discipline as
// device/mpu/services/reflex_loop.py's ALERT_PROBABILITY_THRESHOLD comment.
// See docs/KNOWN_GAPS.md - this is a stand-in, not a resolved model.

// Originally an exponential saturation (1 - exp(-k*(ratio-1))), but that
// pulled expf() in from the real board's libm_nano.a - a minimal picolibc
// (--specs=nano.specs -nostdlib) that does not provide __errno, which
// wf_exp.c's expf needs for domain/range error signaling. That link failure
// only shows up on the real arm-zephyr-eabi hardware build, never on
// `pio test -e native` (full host libc always provides __errno) - found the
// hard way flashing this change (docs/KNOWN_GAPS.md, 2026-08-14). Replaced
// with a Hill/generalized-logistic saturation, x^2/(x^2+c^2) where
// x = peak_ratio - 1, that needs only multiplication and division - no libm
// transcendental call, so no errno dependency on any toolchain.
//
// Solved against the same two real data points device/mcu/README.md's bench
// stomp test produced: the real stomp ratio (4.60, x=3.60) should saturate
// near 0.9, not exactly 1.0 - a single clean trial should not become a hard
// ceiling. x^2/(x^2+c^2) = 0.9 at x=3.60 => c^2 = x^2*(1-0.9)/0.9 = 1.44 =>
// c = 1.2. Checked, not separately fitted, against the same session's
// quiet-floor ceiling (1.13, x=0.13): this c maps it to ~0.012, i.e.
// genuinely "near 0" as intended (tighter than the exponential's ~0.08),
// not just correct at the one anchor it was solved from.
#define FOOTFALL_PROBABILITY_SATURATION_C 1.2f

// ---------------------------------------------------------------------------
// Audio deterrence - DFPlayer -> TPA3116D2 (single BTL) -> Ahuja SUH-15
// ---------------------------------------------------------------------------
// All pins below are owned exclusively by src/actuators/horn.cpp.
//
// AUDIO_TRIGGER_PIN: retained but retired by ADR 0015 Decision E. It was a
// GPIO pulse into the DFPlayer PRO (DFR0768) KEY input - the only control
// path available while USART1 on D0/D1 (the sole header UART) was assumed
// fully claimed by the Grove LoRa-E5. Kept #define'd, not deleted, so
// reverting to the KEY-pin trigger costs nothing if the DFPlayer AT link
// ever needs to be bypassed.
#define AUDIO_TRIGGER_PIN 2

// DFPlayer PRO (DFR0768) AT-command link. ADR 0015 Decision A originally
// specified a software UART on D9/D10 (PB8/PB9) - impossible on this part:
// PB8/PB9 have no UART TX/RX alternate function in the STM32U585 pinctrl
// tables at all, and the arduino:zephyr core ships no SoftwareSerial (Zephyr
// has no bit-banged UART driver).
//
// A second candidate, `usart3` on D20/D21, was also ruled out: the official
// UNO Q pinout diagram lists D20/D21 as I2C2 SDA/SCL only - the UART/USART
// column for both rows is empty. There is no `usart3` reachable from either
// header. That closes both non-header options too: JMISC/JMEDIA are 1.8V,
// explicitly marked "cannot be used as regular GPIOs" on the official
// diagram, and physically inaccessible on this board regardless.
//
// USART1 (D0/D1) is therefore the only hardware UART this board exposes at
// all, on any header, so the DFPlayer and the LoRa-E5 share it through a
// 74HC4053 bus switch (UART_SHARE_* below, ADR 0029): DFR0768 TX -> Y0,
// DFR0768 RX <- X0, with the switch commons on D0/D1. See DFPLAYER_SERIAL
// below for the naming rationale.
#define DFPLAYER_UART_BAUD 115200UL

// Minimum gap horn.cpp holds between two consecutive AT command sends to the
// DFR0768. Not from a datasheet number - the module's AT parser has shown
// signs of dropping/misapplying a command sent immediately after another over
// UART (Stage C bring-up: AT+PLAYMODE=3 resent before every fire still did not
// stop the module from auto-advancing through every track, DFRobot forum
// "DFPlayer Pro Playmode Resets"). A small settle gap between sends is the
// standard workaround for this class of cheap AT-command audio module and
// costs only tens of ms against HORN_AMP_ENABLE_DELAY_MS's existing budget.
#define DFPLAYER_AT_COMMAND_GAP_MS 50

// The stream horn.cpp writes AT commands to. `Serial1` is usart1 = D0/D1 -
// the arduino:zephyr core skips the first serial index whenever the board
// overlay declares `arduino,router-serial` (this board does, for Bridge), so
// index 0 is `Serial1`, not `Serial`: `Serial1` = usart1 = D0/D1, `Serial2` =
// lpuart1 = Bridge, `Serial3` = usart3 = D21/D20 (unreachable - see above). Bare `Serial` is the Bridge Monitor stream,
// not a physical wire - confirmed by this project's own LORA_SERIAL
// correction below - so it stays safe for fire_test.cpp's interactive
// console to keep using while DFPLAYER_SERIAL sits on Serial1: the human
// types into Serial, the DFPlayer link is Serial1, they cannot collide.
// The host build resolves Serial1 to hostshim's stub; the pure
// command-string/volume logic (horn_at_vol_command,
// horn_at_playnum_command, horn_dfplayer_volume_from_gain_pct) is what the
// host tests exercise, not the transport. Recorded in ADR 0029.
#define DFPLAYER_SERIAL UART_SHARE_SERIAL

// AT+VOL parameter range on the DFR0768 (protocol reference: 0-30 absolute).
// horn_dfplayer_volume_from_gain_pct() maps the wire gain_pct (0-100, already
// HORN_GAIN_MAX_PCT-clamped by rule_gate_apply) onto [0, this].
#define DFPLAYER_VOL_MAX 30

// AT+PLAYMODE value for "play the selected file once, then pause" (DFR0768
// modes: 1 single-loop, 2 all-loop, 3 play-once, 4 random, 5 folder-loop). A
// deterrence burst must not loop - the amp shutdown ends it on schedule, but a
// looping module would keep driving the DAC behind a muted amp until the next
// fire. horn.cpp re-sends this before every fire, not once in horn_init() or
// on a first-fire latch, because the DFR0768 does not reliably persist the
// play mode across a power cycle and a single send is not verified to land.
#define DFPLAYER_PLAYMODE_SINGLE 3

// The DFR0768 has 128 MB of onboard flash and NO SD-card slot: audio files are
// loaded by plugging its USB-C port into a host and copying them onto the
// mass-storage volume. AT+PLAYNUM=<n> then indexes files by FAT directory
// (copy) order, not by any number in the filename, so the tracks must be copied
// one at a time in the cognition/config.py category order and the mapping
// verified at bring-up (docs/specs/mcu-fire-test-harness.md).

// TPA3116D2 shutdown pin, active low. ADR 0003 drives a single BTL channel,
// not PBTL: at the 12.8 V rail one channel already puts the SUH-15 well above
// the 105 dB/1 m field-validated deterrence reference, while PBTL would exceed
// the horn's own 23 W maximum. Low-side switch on the amp's GND return (an
// IRLZ44N gate on D11), not in series with VCC - VCC feeds the amp directly
// off the raw battery bus (hardware/PIN_MAP.md power-rail table).
//
// D11 (PB15), not the originally-specified D4: D4 is PA12, USB_OTG_FS D+,
// claimed by the Arduino core's USB CDC - digitalWrite there is a silent
// no-op, the same trap that latched the left LED wing on via D5/PA11 before
// that moved to D3. D11 is otherwise-unused SPI2 MOSI and matches the
// physical wiring confirmed at bring-up.
#define HORN_AMP_ENABLE_PIN 11  // PB15

// Width of the DFPlayer trigger pulse - long enough to register as a press on
// its input, short enough not to read as a long-press.
#define AUDIO_TRIGGER_PULSE_MS 100

// Gap between triggering the DFPlayer and bringing the amp out of shutdown.
// The amp stays muted across the DFPlayer's own trigger and track-seek time so
// neither the switching transient nor the TPA3116's un-mute step reaches the
// horn as a pop, and the delay is spent on the clip's lead-in silence rather
// than on content.
//
// INVENTED - no measured DFPlayer trigger-to-audio latency backs this number.
// Measure it at Rung 3 and tune for both pop suppression and clip-start
// integrity (KNOWN_GAPS). Bumped from the original 150 during Stage C bench
// testing: track 1 played clean at 150ms but track 2 consistently produced
// crackle/noise instead of content through the identical fire sequence,
// pointing at a per-file seek/decode-start latency this value did not cover.
#define HORN_AMP_ENABLE_DELAY_MS 600

// Bench bring-up (6 Sept) found a second, separate transient this delay does
// not cover: the TPA3116D2's own power-up/soft-start sequence produces an
// audible rising-falling sweep every time D11 brings it out of shutdown,
// independent of what DFPlayer is doing - confirmed on the bench by the
// sweep appearing identically on every track, not just one. This board has
// no exposed SD/MUTE pin to gate instead (checked the silkscreen around the
// TPA3116D2 - none), so the sweep cannot be removed with this hardware.
//
// A trial moved the amp-enable ahead of the AT commands, on the theory that
// the sweep should land on DFPlayer's silence instead of overlapping the
// track's onset - that trial produced a dropped AT+PLAYNUM (silent no-play,
// no ack check to catch it) on at least one fire, most likely a live,
// actively-switching amp injecting noise onto DFPlayer's own UART RX right
// as the command went out. Reverted (see horn.cpp): a horn that sometimes
// plays nothing is a worse failure than one with an audible sweep on every
// fire. KNOWN_GAPS: the sweep itself remains unsolved - a real SD/MUTE pin,
// or ruling out this UART-noise theory with a scope, are the next leads.

// ADR 0003 requires a burst-duration cap and a cooldown as an animal-welfare
// safeguard and to bound battery draw, but names no numbers. All three values
// below are provisional engineering judgement pending field tuning
// (KNOWN_GAPS).
//
// 3 s is longer than the startle response a deterrent burst is trying to
// provoke needs, and far short of continuous exposure.
#define HORN_BURST_MAX_MS 3000

// 10 s between bursts. Cut from an original 30 s (bring-up, 6 Sept) to
// re-fire faster at an animal still approaching or lingering, at the cost of
// a shorter minimum gap for one that has already stopped moving - a
// deliberate trade toward deterrence responsiveness, not yet field-validated
// (KNOWN_GAPS).
#define HORN_COOLDOWN_MS 10000

// Field record, 7 Sept: a single HORN_BURST_MAX_MS (3 s) roar was tested
// against a real elephant/wild-boar encounter and judged an insufficient
// deterrent stimulus on the spot - one short burst did not read as
// convincingly as several would. A three-roar replay was specified in
// response (re-trigger AT+PLAYNUM per roar with amp-off silence between, so
// they read as distinct roars rather than one long one) and HORN_REPEAT_COUNT
// / HORN_REPEAT_GAP_MS were added here for it.
//
// It was never implemented. horn_fire_sequence() (horn.cpp) plays the track
// exactly once per drive_horn() call and has no repeat loop, so the two
// constants had no reader and have been removed rather than left looking
// live. The field finding itself still stands and is still unaddressed
// (KNOWN_GAPS) - whoever picks it up should treat the paragraph above as the
// requirement and note that it changes the MCU's worst-case single-fire stall
// by roughly 3x, which is the reason it is not a one-line change.
//
// The real worst-case stall today is ~3.8 s: 4 AT sends at
// DFPLAYER_AT_COMMAND_GAP_MS (200 ms) + HORN_AMP_ENABLE_DELAY_MS (600 ms) +
// HORN_BURST_MAX_MS (3000 ms), all of it inside one cooperatively scheduled
// loop() iteration, so geophone_service() and lora_service() are starved for
// that window.

// Software gain ceiling, as a percentage of the channel's full output. ADR
// 0003 limits delivered power to roughly 6-8 W of the channel's ~12 W at the
// 12.8 V rail, which still yields ~117-119 dB at 1 m while leaving real
// thermal headroom under the horn's 23 W maximum across a multi-year
// deployment.
#define HORN_GAIN_MAX_PCT 60.0f

// ---------------------------------------------------------------------------
// Visual deterrence - cool-white + royal-blue LED pods via IRLZ44N gates
// ---------------------------------------------------------------------------
// D5 (PA11) is USB_OTG_FS D- on the UNO Q - the Arduino core claims it for the
// USB CDC and digitalWrite() on it is a no-op, which latched the left wing on.
// Left wing moved to D3 (PB0) on 2026-08-31; D3 is a plain PWM GPIO (TIM3_CH3),
// not shared with any bus. Right wing on D6 (PB1) was always clean.
#define LED_WING_LEFT_PIN 3  // PB0, PWM-capable (TIM3_CH3); drives left wing (mixed white+blue LEDs, 2-wing build)
#define LED_WING_RIGHT_PIN 6   // PB1, PWM-capable (TIM3_CH4); drives right wing (mixed white+blue LEDs, 2-wing build)

// Light is far cheaper to run than the horn and less aversive, so it gets a
// longer cap and a shorter cooldown - independent counters from the horn, per
// device/mpu/bridge/schema.md. Cut from an original 20 s alongside
// HORN_COOLDOWN_MS's 6 Sept reduction, same deterrence-responsiveness trade,
// not yet field-validated (KNOWN_GAPS).
//
// Raised from 10000 to 12500 on 7 Sept, alongside the three-roar horn replay
// specified the same day: field feedback wanted the light illusion running
// "as long as the sound gets played," and a fixed 10 s cap would have gone
// dark before a ~12.2 s multi-roar fire finished.
//
// That replay was never implemented (see the horn section above), so this cap
// is currently sized against a fire that cannot happen. The horn's real
// worst case is ~3.8 s, and the LED therefore outruns it by ~8.7 s. Left at
// 12500 deliberately: shortening it is a change to deterrence behaviour on a
// node heading for a real deployment, not a comment fix, and a light that
// runs longer than the horn is the safe direction to be wrong in - it is the
// cheaper and less aversive of the two actuators (ADR 0014). Re-check this
// bound if the replay is implemented or HORN_BURST_MAX_MS changes.
// Tier 2/3 already select
// led_pattern_id 4/5 (kSweep / kPulseBothSync, cognition/config.py) - the
// antiphase dual-wing "apparent-movement cue" ADR 0014 E.1 calls out - so the
// movement/predator-presence illusion this is meant to run alongside is
// already the pattern the field-tested tiers fire; this change is what keeps
// it lit for the horn's whole roar instead of cutting out partway through.
#define LED_BURST_MAX_MS 12500
#define LED_COOLDOWN_MS 8000
#define LED_GAIN_MAX_PCT 100.0f

// ADR 0014 pattern-axis timing. The four patterns (led.h's led_pattern) all
// run inside drive_led()'s existing blocking window and total exactly the
// resolved duration_ms - they change the shape of the burst, not its length,
// so they add no blocking cost beyond what every LED fire already has
// (docs/KNOWN_GAPS.md, 1 Sept). Numbers here are the deterrence-pattern
// design axis, not safety limits - rule_gate_apply()'s caps above remain the
// sole authority on duration and gain.
//
// SLOW_PULSE: whole on/off cycles spread across the burst, ~50% duty. 2 is
// the smallest count that still reads as a deliberate pulse rather than a
// single flash with a gap.
#define LED_SLOW_PULSE_CYCLES 2

// FAST_STROBE rate. 7 Hz sits in the 6-8 Hz band ADR 0014 specifies: fast
// enough to look like a strobe rather than a blink, and close to the camera
// frame rate so it also disrupts a habituating animal's fixation. ~143 ms
// period at 50% duty. Tiers 1-2 fire at this rate.
#define LED_FAST_STROBE_HZ 7

// Escalation strobe rate for the top tier (ADR 0014 E.3). 11 Hz is still
// inside the 4-12 Hz band that reads as discrete aversive flashes rather
// than fusing toward a steady glow - past ~15 Hz the perceptual effect
// inverts. ~91 ms period at 50% duty. Only pattern_pulse_both_sync
// (pattern_id 5, a Tier 3 pattern) uses it; the ladder's top rung escalates
// on rate as well as wing count and pattern, holding gain at max on every
// tier. No citation validates 11 specifically over 7 as "more effective" -
// only the order of magnitude and the fusion ceiling (ADR 0014 E.3
// "Honest bound").
#define LED_STROBE_FAST_HZ 11

// RANDOM_FLICKER inter-flash envelope. Each flash is on for a random span in
// [MIN_ON, MAX_ON] then dark for a random gap in [MIN_GAP, MAX_GAP], seeded
// from micros() at call time (led.cpp), until the burst budget is spent. The
// irregular gap is the point - it is the "irregular strobe" CONTEXT.md 3
// freezes, and the anti-habituation lever WIRING_GUIDE.md 4.0 names.
#define LED_RANDOM_FLICKER_MIN_ON_MS 20
#define LED_RANDOM_FLICKER_MAX_ON_MS 80
#define LED_RANDOM_FLICKER_MIN_GAP_MS 30
#define LED_RANDOM_FLICKER_MAX_GAP_MS 160

// ---------------------------------------------------------------------------
// IR illuminator - 940 nm, MOSFET-gated, pulsed only during capture
// ---------------------------------------------------------------------------
// 940 nm matches the IMX462's own IR-cut filter (CONTEXT.md 8); a mismatched
// wavelength lights the scene for nothing.
#define IR_ILLUMINATOR_PIN 7  // PB2

// A capture needs a fraction of a second of illumination, and the illuminator
// board and its MOSFET are sized for pulsed, not continuous, duty.
#define IR_PULSE_MAX_MS 500

// 5 s between pulses holds duty at or under 10% at the maximum pulse width,
// which is what keeps the gate MOSFET inside its thermal limit.
#define IR_MIN_INTERVAL_MS 5000
#define IR_GAIN_MAX_PCT 100.0f

// ---------------------------------------------------------------------------
// Status signalling - on-board RGB LED 3
// ---------------------------------------------------------------------------
// RGB LED 3 is MCU-owned (PH10/PH11/PH12) and has no pre-assigned meaning.
// LEDs 1 and 2 are MPU-side, so driving them would cost an MPU wake, and LED 2
// already carries fixed panic/wlan/bt semantics.
//
// Whether the Arduino Core exposes these port pins under these names is not
// confirmed on hardware; nothing drives them yet (KNOWN_GAPS).
#if defined(PH10) && defined(PH11) && defined(PH12)
#define STATUS_LED_R_PIN PH10
#define STATUS_LED_G_PIN PH11
#define STATUS_LED_B_PIN PH12
#else
#define STATUS_LED_R_PIN (-1)
#define STATUS_LED_G_PIN (-1)
#define STATUS_LED_B_PIN (-1)
#endif

// ---------------------------------------------------------------------------
// LoRaWAN - Grove LoRa-E5, IN865 (ADR 0002)
// ---------------------------------------------------------------------------
// LoRa and DFPlayer share USART1/D0-D1 (the board's only header UART - see
// DFPLAYER_UART_BAUD above for why no other pin pair works) through a
// 74HC4053 bus switch, arbitrated in uart_share.cpp (ADR 0029). main.cpp
// gates lora_init()/lora_service() on this. Setting it 0 builds a
// DFPlayer-only image: D0/D1 belong to the DFR0768 outright and
// UART_SHARE_SELECT_PIN is never driven. Overridable with -D (platformio.ini
// tests both) or from config_local.h.
#ifndef LORA_ENABLED
#define LORA_ENABLED 1
#endif

// The switch only has work to do when there is a second module behind it.
#define UART_SHARE_ENABLED LORA_ENABLED

// The one physical USART both modules sit behind. DFPLAYER_SERIAL and
// LORA_SERIAL below both name it; uart_share.cpp is the only file that calls
// begin() on it.
#define UART_SHARE_SERIAL Serial1

// 74HC4053 select line: both used channels' select inputs (A and B, pins 11
// and 10) tied together to this pin, so TX and RX always switch as a pair.
// D4 = PA12, plain GPIO, no PWM channel - fine for a static level, and it
// keeps PWM-capable D5 free. (D4 was HORN_AMP_ENABLE_PIN in older trees; the
// amp enable is D11.)
#define UART_SHARE_SELECT_PIN 4  // PA12

// Select level per module. LOW routes the X0/Y0 pair (DFPlayer), HIGH the
// X1/Y1 pair (E5). Boot state is LOW: the DFPlayer is the default owner.
#define UART_SHARE_SELECT_DFPLAYER LOW
#define UART_SHARE_SELECT_LORA HIGH

// Wait after moving the select line before re-opening the port. The
// 74HC4053's own switching time is well under a microsecond at 3.3 V; this is
// margin for the line to settle, not a datasheet figure, and costs 2 ms per
// switch - nothing against a horn fire's AT sequence.
#define UART_SHARE_SWITCH_SETTLE_MS 2

// USART1 is the only UART on the top headers, confirmed live on hardware
// 2026-09-06 via the board's own compiled devicetree over SSH: `zephyr,
// console = &usart1` and `zephyr,shell-uart = &usart1`, while `arduino,
// router-serial = <&lpuart1>` ('Serial' is provided by the Monitor - not a
// physical wire). CONFIG_SHELL is not set in the board's merged .config, so
// the shell-uart binding is inert; CONFIG_LOG/CONFIG_LOG_BACKEND_UART/
// CONFIG_BOOT_BANNER are all on, so Zephyr kernel log lines (mostly at boot
// in a quiescent system, but not exclusively) can land on this same wire -
// unfixable from sketch code, since the core's devicetree/Kconfig is baked
// into the prebuilt loader. Known, accepted risk on D0/D1; the bus switch
// above does not remove it (it arbitrates between LoRa and the DFPlayer, not
// the kernel console).
#define LORA_UART_RX_PIN 0  // PB7, USART1_RX  <- E5 TX
#define LORA_UART_TX_PIN 1  // PB6, USART1_TX  -> E5 RX

// The Grove LoRa-E5 ships at 9600 baud 8N1.
#define LORA_UART_BAUD 9600UL

// CORRECTED - the 2026-08-18 "CONFIRMED on hardware" note below this line
// used to bind LORA_SERIAL to `Serial` and had the naming backwards; it is
// quoted rather than deleted so the reasoning error is visible. `zephyr,user`
// in the board overlay declares `arduino,router-serial = <&lpuart1>`, and
// its own comment there reads "'Serial' is provided by the Monitor" - i.e.
// bare `Serial` is the Bridge Monitor stream (`journalctl -u arduino-router`
// shows it opening `/dev/ttyHS1`, lpuart1's Linux-side node), not the E5.
//
// The actual E5 wire is USART1/D0-D1, and the generic serial list
// (`serials = <&usart1>, <&lpuart1>, <&usart3>;`) is what names it. The core
// skips the first generic index whenever `arduino,router-serial` is present
// (`cores/arduino/zephyrSerial.h`, `ZARD_SKIP_FIRST_SERIAL`) - because
// `Serial` is already claimed by the router - so the list starts at
// `Serial1`, not `Serial`: **`Serial1` = usart1 = D0/D1 (the E5, via the
// switch), `Serial2` = lpuart1 = Bridge again, `Serial3` = usart3 = D21/D20
// (see DFPLAYER_UART_BAUD above)**. `LORA_SERIAL Serial` therefore pointed at the
// Bridge Monitor the whole time and never reached the physical wire - a
// likely explanation for PIN_MAP.md's "wired 18 Aug, not yet answering AT
// probes". Verify with a bare `AT` on Serial1 at bring-up.
//
// Also confirmed from the linked image: in sketch.ino.map, `Serial` resolves
// to .bss.Monitor from Arduino_RouterBridge/singletons.cpp.o - the same
// address as `Monitor` - while Serial1/2/3 are arduino::ZephyrSerial objects
// from core.a(zephyrSerial.cpp.o).
//
// Real consequence, not just a naming fix: `Serial` (bare) is also the
// firmware's debug console (every `[tag]`-prefixed print throughout this
// codebase) and shares the Bridge Monitor stream - unrelated to the E5's
// physical wire now that LORA_SERIAL is Serial1, so SEISMIC_TRIGGER_CONSOLE_LOG
// below no longer protects LoRa traffic from console noise the way this
// comment previously claimed. Re-evaluate that flag's purpose once Serial1
// is confirmed live; it may now only matter for Bridge Monitor cleanliness.
#define LORA_SERIAL UART_SHARE_SERIAL

// When 1: state_machine.cpp's log_trigger() prints [trigger] on every real
// STA/LTA crossing, and notify_footfall_event() prints [notify] alongside
// its Bridge.notify() call - both unconditional, no debug flag, before this
// flag existed (docs/KNOWN_GAPS.md, 18 Aug). Confirmed on hardware that a
// footfall trigger firing mid-join or mid-uplink sends raw console text down
// the exact same physical wire LORA_SERIAL above uses, which the E5 parses
// as line noise or a garbled AT command. MUST be 0 before any field sync,
// same discipline as the bench-only flags earlier in this file - left at 0,
// state_machine.cpp emits nothing over Serial and the wire stays clean for
// LoRa AT traffic. The real report_footfall_event Bridge.notify() call is
// untouched either way - this flag gates only the local console echo, not
// the MPU-bound schema report. Bench visibility (device/mcu/README.md's
// stomp-test procedure) needs this set to 1 - App Lab's own Serial Monitor
// still works for that as long as the E5 isn't mid-transaction at the same
// moment, same caveat as every other console print now that Serial is
// shared with the radio.
#define SEISMIC_TRIGGER_CONSOLE_LOG 0

// Most AT commands answer in well under a second; 2 s covers a slow one
// without stalling the reflex loop, which never blocks on the radio anyway.
#define LORA_AT_TIMEOUT_MS 2000

// An OTAA join can take tens of seconds when the gateway is busy or the link
// is marginal, so the join gets its own, much longer budget.
#define LORA_JOIN_TIMEOUT_MS 60000

// Five attempts with backoff, then give up and let the state machine carry on
// unjoined - the node's detection and deterrence are local and do not depend on
// the uplink (CONTEXT.md 4).
#define LORA_JOIN_MAX_RETRIES 5

// Multiplied by the retry count, so the waits are linear rather than
// exponential: mac.cpp computes LORA_JOIN_BACKOFF_BASE_MS * (g_retry_count +
// 1), giving 5, 10, 15, 20, 25 s across LORA_JOIN_MAX_RETRIES - about 75 s to
// spend the budget. Backoff rather than a fixed interval so a node that comes
// up while the gateway is down does not hammer the channel; linear rather
// than doubling because the point is to stop retrying at a fixed cadence, not
// to reach long waits, and 80 s of silence on the fifth attempt would delay
// the retry-from-the-top path in lora_service() for no benefit on a node that
// detects and deters locally regardless (CONTEXT.md 4). The comment here
// previously described doubling, which the code has never done.
#define LORA_JOIN_BACKOFF_BASE_MS 5000

// Longest single line the E5 sends back. Fixed buffer, no dynamic allocation
// in the reflex path. A longer line is consumed up to its newline and
// matched on what fit.
#define LORA_RESPONSE_MAX_LEN 128

// Every uplink uses this FPort (ADR 0031); the ingest bridge decodes only
// frames that arrive on it. Set once per join with AT+PORT.
#define LORA_UPLINK_FPORT 10

// Frames waiting for the radio. Events are rare and a status is sent every
// LORA_STATUS_INTERVAL_MS, so four covers a burst of triggers while the port
// is busy with the horn. When full, a new event evicts the oldest status; a
// new status is dropped.
#define LORA_UPLINK_QUEUE_LEN 4

// Largest payload any uplink type encodes to (uplink.h). IN865 allows 51
// bytes even at DR0, so every frame fits at the slowest data rate.
#define LORA_UPLINK_MAX_LEN 16

// One AT+(C)MSGHEX exchange, "+...: Start" through "+...: Done". A confirmed
// frame waits out both receive windows and the E5's own retransmissions
// before it prints Done, so this is far longer than LORA_AT_TIMEOUT_MS.
#define LORA_UPLINK_TIMEOUT_MS 30000UL

// Sends of one frame before it is dropped. A horn fire that cuts the exchange
// short is not counted - the frame is re-sent with the same seq.
#define LORA_UPLINK_MAX_ATTEMPTS 3

// Wait before re-sending a frame that failed: this times the attempt number.
#define LORA_UPLINK_RETRY_BASE_MS 15000UL

// Status heartbeat period. The dashboard marks a node stale after two missed
// periods (bridge/schema.md, report_system_status). A status is also queued
// right after every join so a node shows up as soon as it is on the network.
#define LORA_STATUS_INTERVAL_MS 600000UL

// ---------------------------------------------------------------------------
// Reflex state machine
// ---------------------------------------------------------------------------
// How long the node stays in EVENT before falling back to COOLDOWN if nothing
// escalates. Bounds the time actuators and the MPU wake path can be held open
// by one trigger.
//
// Demo mode (SEISMIC_DEMO_MODE, see the STA/LTA block above) shortens both
// this and COOLDOWN_MS below: read_seismic_window() - the only place either
// the raw-volts or STA/LTA debug stream gets a new sample - is called
// exclusively from kSensing (state_machine.cpp), so every trigger blanks
// both live-plot panels for the full EVENT_MAX_MS + COOLDOWN_MS duration.
// At the field values (15 s + 20 s = 35 s) that is a deliberate anti-alarm-
// fatigue design, not a bug - but demo mode's whole point is triggering
// easily, so at the field cooldown a live audience sees the plot go dark for
// half a minute after almost every tap. Shortened here to keep the demo
// cycling quickly; MUST come back to the field values below before any real
// deployment, same as the trigger ratios.
#if SEISMIC_DEMO_MODE
#define EVENT_MAX_MS 2000
#define COOLDOWN_MS 3000
#else
#define EVENT_MAX_MS 15000

// Quiet period after an event completes, before the node will arm a new one.
// Distinct from the per-actuator cooldowns: those bound one output, this bounds
// the whole detect-deter cycle.
#define COOLDOWN_MS 20000
#endif

// Heartbeat period for report_system_status (device/mpu/bridge/schema.md).
// 10 minutes gives the dashboard a liveness signal through quiet periods
// without waking anything on a schedule that matters to the power budget.
#define SYSTEM_STATUS_PERIOD_MS 600000UL

// Console baud for bench logging.
#define CONSOLE_BAUD 115200UL

// ---------------------------------------------------------------------------
// Bridge RPC - device/mpu/bridge/schema.md
// ---------------------------------------------------------------------------
// Every schema.md payload carries schema_version as its first field,
// currently 4 (schema.md's own header). Mirrors device/mpu/services/
// config.py's SCHEMA_VERSION = 4 - both sides must bump together on any
// breaking field change, never reuse a version number (schema.md). Used
// by bridge_handlers.cpp to log (not reject) a mismatched request on an
// MPU->MCU call, same as services/reflex_loop.py does on an MCU->MPU
// notify - schema.md defines no MCU-side reject behavior for this, and a
// synchronous actuator call still owes its caller an ack either way.
//
// 1 -> 2 on 2026-09-01 (ADR 0014): drive_led's wire args changed from
// (pattern_id, duration_ms) to (channel, pattern_id, gain_pct, duration_ms).
// pattern_id stops meaning "which wing" (that is now `channel`) and starts
// meaning "which flash pattern" (led.h's led_pattern) - its original intent.
//
// 2 -> 3 on 2026-09-01 (ADR 0014 E): drive_led's `channel` value 2 changes
// meaning from "unrecognized, fall back to left" to "both wings, driven
// together inside one blocking call"; `pattern_id` gains 4 = sweep, 5 =
// pulse both sync, 6 = flicker both independent (led.h's led_pattern). No
// field added or removed - the wire shape is unchanged - but a sender on
// schema 2 that meant "fall back" by sending channel 2 would now fire both
// wings, so it is a breaking change and bumps the version.
//
// 3 -> 4 on 2026-09-02 (ADR 0015): drive_horn gains a trailing `track_id:
// uint8` field so the MPU can select which content the DFPlayer plays per
// tier (AT+PLAYNUM), not just how loud (AT+VOL). A real new wire field -
// a schema-3 sender omits it - so it bumps the version. drive_led,
// pulse_ir, and every MCU->MPU row are unchanged.
//
// 4 -> 128 on 2026-09-09: no wire-shape change, value change only. The
// on-device MsgPack library (0.4.2, Arduino_RPClite's Unpacker.h) mis-detects
// positive-fixint-encoded values (0-127) as the wrong type for a uint8_t
// parameter - schema_version was always sent in that range, so every
// actuator RPC call failed at deserialization regardless of everything else
// being correct (bench-verified: value 200 unpacked fine, 0 and 1 did not).
// 128 stays a valid uint8_t but forces the explicit uint8 msgpack format,
// which unpacks correctly on this library version. Mirrors device/mpu/
// services/config.py's SCHEMA_VERSION; both sides must bump together.
#define BRIDGE_SCHEMA_VERSION 128

// Hard limit the arduino-router enforces on a single Bridge message, from
// Arduino's own Bridge reference (docs/research/platform/
// app-lab-flash-and-routerbridge.md). This is not a tunable: the router
// applies it, and the two failure modes are asymmetric and both bad -
// Bridge.notify() drops an oversized message *silently*, while the Python
// Bridge.call() raises ValueError. Anything that builds a payload whose size
// depends on a constant must check itself against this at compile time
// rather than discover it in the field; seismic_capture.h is the worked
// example.
#define BRIDGE_MAX_MESSAGE_BYTES 256

#endif  // CONFIG_H
