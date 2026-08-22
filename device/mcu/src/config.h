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
// the Qwiic connector: no JST-SH cable is in hand. D20/D21 are I2C2, a bus
// entirely separate from the Qwiic connector's I2C4 (PD12/PD13), so this
// leaves Qwiic free for the BME280/MPU-6050 later.
#define GEOPHONE_I2C_SDA_PIN 20  // PB11, I2C2_SDA (default mapping, no config needed)
#define GEOPHONE_I2C_SCL_PIN 21  // PB10, I2C2_SCL

// CONFIRMED on hardware 2026-08-14: `Wire` is the correct instance for I2C2.
// The arduino:zephyr core declares Wire/Wire1/Wire2/... in the order listed
// by the board overlay's `zephyr,user { i2cs = <&i2c2>, <&i2c4>, <&i2c3>; }`
// (arduino_uno_q_stm32u585xx.overlay) - i2c2 is first, so it is `Wire`, not
// `Wire1` (which binds to i2c4, the Qwiic connector). The generated board
// .dts confirms i2c2's pinctrl-0 is `i2c2_scl_pb10`/`i2c2_sda_pb11` and that
// the node is aliased `arduino_i2c` - i.e. i2c2 is the default Arduino I2C
// header, exactly the PB10/PB11 pins documented above. Cross-checked against
// real bench data: continuous, plausible, varying ADS1115 differential
// readings over the socat/TCP console bridge (not silent, not garbage),
// which is what a correct bus produces - a wrong bus would fail every I2C
// transaction and produce no ring-buffer writes at all.
#define GEOPHONE_I2C_BUS Wire

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
// Manual fire-test harness - MUST be 0 before any field sync
// ---------------------------------------------------------------------------
// Serial-command-triggered single fire of horn/LED/IR for hardware bring-up
// verification (docs/specs/mcu-fire-test-harness.md). Human types a digit
// into App Lab's Serial Monitor; nothing fires without that keystroke, so
// this has no autonomous trigger path. Still gated to 0 by default, same
// discipline as the seismic bench flags above: the point of field builds is
// that bench-only surface area doesn't exist in them.
#define FIRE_TEST_HARNESS 0

// Bench defaults - short and conservative. The real safety backstop is still
// rule_gate_apply()'s per-actuator caps (HORN_GAIN_MAX_PCT etc. above); these
// are just sane starting points for a desk-bench test, not a duplicate
// limit.
#define FIRE_TEST_HORN_DURATION_MS 500   // well under HORN_BURST_MAX_MS=3000
#define FIRE_TEST_HORN_GAIN_PCT 30.0f    // under HORN_GAIN_MAX_PCT=60, desk-volume not field-volume
#define FIRE_TEST_LED_DURATION_MS 1000
#define FIRE_TEST_LED_GAIN_PCT 50.0f
#define FIRE_TEST_IR_DURATION_MS 200     // under IR_PULSE_MAX_MS=500
#define FIRE_TEST_IR_GAIN_PCT 100.0f     // IR is invisible, thermal is the only real constraint

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
// Both pins below are owned exclusively by src/actuators/horn.cpp.
//
// The DFPlayer is triggered by a GPIO pulse on its IO/ADKEY input rather than
// over UART: USART1 on D0/D1 is the only UART broken out to the top headers
// and the Grove LoRa-E5 has it.
// PB3, plain GPIO -> DFPlayer PRO (DFR0768) KEY input. Active-low: the
// DF1101S pulls KEY up to its own IO rail (idle high) and reads a direct
// short to ground as key K1 (Play & Pause) - see horn.cpp's top comment.
#define AUDIO_TRIGGER_PIN 2

// TPA3116D2 shutdown pin, active low. ADR 0003 drives a single BTL channel,
// not PBTL: at the 12.8 V rail one channel already puts the SUH-15 well above
// the 105 dB/1 m field-validated deterrence reference, while PBTL would exceed
// the horn's own 23 W maximum.
#define HORN_AMP_ENABLE_PIN 4  // PA12

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
// integrity (KNOWN_GAPS).
#define HORN_AMP_ENABLE_DELAY_MS 150

// ADR 0003 requires a burst-duration cap and a cooldown as an animal-welfare
// safeguard and to bound battery draw, but names no numbers. All three values
// below are provisional engineering judgement pending field tuning
// (KNOWN_GAPS).
//
// 3 s is longer than the startle response a deterrent burst is trying to
// provoke needs, and far short of continuous exposure.
#define HORN_BURST_MAX_MS 3000

// 30 s between bursts. Long enough that a node cannot harass an animal that
// has not moved, short enough to re-fire at an animal still approaching.
#define HORN_COOLDOWN_MS 30000

// Software gain ceiling, as a percentage of the channel's full output. ADR
// 0003 limits delivered power to roughly 6-8 W of the channel's ~12 W at the
// 12.8 V rail, which still yields ~117-119 dB at 1 m while leaving real
// thermal headroom under the horn's 23 W maximum across a multi-year
// deployment.
#define HORN_GAIN_MAX_PCT 60.0f

// ---------------------------------------------------------------------------
// Visual deterrence - cool-white + royal-blue LED pods via IRLZ44N gates
// ---------------------------------------------------------------------------
#define LED_WHITE_PIN 5  // PA11, PWM-capable (TIM1_CH4)
#define LED_BLUE_PIN 6   // PB1, PWM-capable (TIM3_CH4); royal-blue, ~450 nm

// Light is far cheaper to run than the horn and less aversive, so it gets a
// longer cap and a shorter cooldown - independent counters from the horn, per
// device/mpu/bridge/schema.md. Provisional, same as the horn values above.
#define LED_BURST_MAX_MS 10000
#define LED_COOLDOWN_MS 20000
#define LED_GAIN_MAX_PCT 100.0f

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
// USART1 is the only UART on the top headers. Whether the Arduino Core also
// claims it for the sketch console is unconfirmed (KNOWN_GAPS).
#define LORA_UART_RX_PIN 0  // PB7, USART1_RX  <- E5 TX
#define LORA_UART_TX_PIN 1  // PB6, USART1_TX  -> E5 RX

// The Grove LoRa-E5 ships at 9600 baud 8N1.
#define LORA_UART_BAUD 9600UL

// CONFIRMED on hardware 2026-08-18: `Serial` is the correct instance for
// USART1/D0-D1. Read directly from the board's own installed
// arduino:zephyr core devicetree overlay
// (~/.arduino15/packages/arduino/hardware/zephyr/0.90.0/variants/
// arduino_uno_q_stm32u585xx/arduino_uno_q_stm32u585xx.overlay), not
// inferred: `&usart1` (PB6/PB7, D0/D1) is assigned `zephyr,console`, while
// `arduino,router-serial = <&lpuart1>` - a separate, header-inaccessible
// internal peripheral - is what Bridge uses, with the overlay's own comment
// noting "'Serial' is provided by the Monitor". Cross-checked against a
// live board: `journalctl -u arduino-router` shows arduino-router opening
// `/dev/ttyHS1` for its serial connection, the Linux-side node for that same
// lpuart1 link - independent confirmation that Serial1/lpuart1 is Bridge's
// internal MCU<->MPU channel, not the E5's physical UART. This settles the
// open question in docs/eletect-x-applab-notes.md and docs/KNOWN_GAPS.md:
// the community forum reports were right, and config.h's previous
// `Serial1` default had never actually reached the physical Grove LoRa-E5.
//
// Real consequence, not just a naming fix: `Serial` is also the firmware's
// debug console (every `[tag]`-prefixed print throughout this codebase), and
// it is the *same physical wire* as the E5 - so any console output emitted
// while lora_service() is mid-sequence lands on the E5's RX pin as noise.
// Mitigated below by SEISMIC_TRIGGER_CONSOLE_LOG for the one unconditional
// offender (state_machine.cpp's [trigger]/[notify] prints) - see
// docs/KNOWN_GAPS.md's 18 Aug entry for the confirmed-real risk this closes.
#define LORA_SERIAL Serial

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

// First retry waits 5 s, then doubles: 5, 10, 20, 40, 80 s. Backoff rather
// than a fixed interval so a node that comes up while the gateway is down does
// not hammer the channel.
#define LORA_JOIN_BACKOFF_BASE_MS 5000

// Longest single line the E5 sends back. Fixed buffer, no dynamic allocation
// in the reflex path.
#define LORA_RESPONSE_MAX_LEN 128

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
// currently 1 (schema.md's own header). Mirrors device/mpu/services/
// config.py's SCHEMA_VERSION = 1 - both sides must bump together on any
// breaking field change, never reuse a version number (schema.md). Used
// by bridge_handlers.cpp to log (not reject) a mismatched request on an
// MPU->MCU call, same as services/reflex_loop.py does on an MCU->MPU
// notify - schema.md defines no MCU-side reject behavior for this, and a
// synchronous actuator call still owes its caller an ack either way.
#define BRIDGE_SCHEMA_VERSION 1

#endif  // CONFIG_H
