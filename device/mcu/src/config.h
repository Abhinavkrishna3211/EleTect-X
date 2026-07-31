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

// Which TwoWire instance the Arduino Core exposes for I2C2 on this board is
// NOT confirmed on hardware yet - `Wire` is the assumption, `Wire1` the likely
// alternative. Resolve at the bench before trusting a silent read (KNOWN_GAPS).
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
#define SEISMIC_DEBUG_VERBOSE 1

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
#define SEISMIC_DEBUG_STREAM_RAW 1

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
// crashed state machine (ENGINEERING_CONVENTIONS.md 7).
#define GEOPHONE_WINDOW_STALE_MS 3072

// ---------------------------------------------------------------------------
// STA/LTA footfall trigger
// ---------------------------------------------------------------------------
// WARNING: these four values are generic STA/LTA convention, carried over from
// standard seismic-trigger practice. They are NOT derived from the elephant
// footfall-frequency work ADR 0001 cites, and no bench data backs them yet.
// They decide whether the node triggers at all, so they are the first thing to
// calibrate against a real stomp trace (KNOWN_GAPS).

// 25 samples = 0.1 s. The short-term average has to be brief enough to rise
// sharply on a single footfall impact rather than average it away.
#define STA_SAMPLES 25

// 250 samples = 1.0 s. The long-term average is the local noise floor the
// short-term average is compared against. Bounded by the 2.048 s bench window;
// the LPBAM swap should extend it well past 1 s (KNOWN_GAPS).
#define LTA_SAMPLES 250

// Ratio at which a window is declared a trigger.
#define STA_LTA_TRIGGER_RATIO 4.0f

// Ratio the signal must fall back below before a new trigger can be declared,
// set well under the trigger ratio so one event does not chatter into many.
#define STA_LTA_DETRIGGER_RATIO 1.5f

// ---------------------------------------------------------------------------
// Audio deterrence - DFPlayer -> TPA3116D2 (single BTL) -> Ahuja SUH-15
// ---------------------------------------------------------------------------
// Both pins below are owned exclusively by src/actuators/horn.cpp.
//
// The DFPlayer is triggered by a GPIO pulse on its IO/ADKEY input rather than
// over UART: USART1 on D0/D1 is the only UART broken out to the top headers
// and the Grove LoRa-E5 has it.
#define AUDIO_TRIGGER_PIN 2  // PB3, plain GPIO -> DFPlayer IO/ADKEY input

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

// Which HardwareSerial instance maps to USART1 on this core is unconfirmed;
// Serial1 is the assumption (KNOWN_GAPS).
#define LORA_SERIAL Serial1

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
#define EVENT_MAX_MS 15000

// Quiet period after an event completes, before the node will arm a new one.
// Distinct from the per-actuator cooldowns: those bound one output, this bounds
// the whole detect-deter cycle.
#define COOLDOWN_MS 20000

// Heartbeat period for report_system_status (device/mpu/bridge/schema.md).
// 10 minutes gives the dashboard a liveness signal through quiet periods
// without waking anything on a schedule that matters to the power budget.
#define SYSTEM_STATUS_PERIOD_MS 600000UL

// Console baud for bench logging.
#define CONSOLE_BAUD 115200UL

#endif  // CONFIG_H
