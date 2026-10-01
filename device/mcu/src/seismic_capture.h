// Batched ground-motion egress to the MPU (ADR 0035, plan item 11a).
//
// The MPU needs the raw seismic waveform, not just the STA/LTA verdict, so
// the camera can label it minutes later and a future species-specific
// footfall model has a corpus to train on. read_seismic_window() (geophone.h)
// already holds exactly that data - but it cannot be handed over as a Bridge
// call, and that constraint is what shapes this file.
//
// WHY A PUSHED STREAM AND NOT A PULL. The Bridge caps a message at
// BRIDGE_MAX_MESSAGE_BYTES (256). One window is SEISMIC_WINDOW_SAMPLES (512)
// samples; as MessagePack floats that is ~2.5 kB, ten times over, and an
// oversized Bridge.notify() is *silently dropped* while Bridge.call() raises
// on the MPU side. Chunking a pull into 256-byte replies would work but puts
// a dozen blocking round trips per second onto lpuart1 - the same link
// drive_horn/drive_led/pulse_ir need an ack from mid-encounter. So the MCU
// pushes instead: Bridge.notify() takes a write mutex and returns without
// waiting on the MPU (geophone.cpp's existing debug_stream_raw_seismic_sample
// path relies on the same property), so a slow or busy MPU can never stall
// the reflex loop.
//
// WHY int16 COUNTS AND NOT VOLTS. These are the ADS1115's own conversion
// results, so nothing is lost by shipping them unconverted - volts are
// recovered on the MPU as `raw * ADS1115_LSB_VOLTS`. An int16 encodes in at
// most three MessagePack bytes against a float32's five, and it removes a
// real hazard: the Bridge type map allows a `float` to encode as either
// float32 or float64, and nothing in the reference says which this library
// picks. At float64 a batch sized against float32 would quietly cross 256
// bytes and vanish. An integer has no such ambiguity.
//
// This file is the pure, host-testable core (ENGINEERING_CONVENTIONS.md 2/4)
// - it accumulates samples and decides when a batch is complete. It never
// touches the Bridge, the ADC or millis(). geophone.cpp owns the one
// Bridge.notify() call that sends what this hands back.

#ifndef SENSORS_SEISMIC_CAPTURE_H
#define SENSORS_SEISMIC_CAPTURE_H

#include <array>
#include <cstddef>
#include <cstdint>

#include "config.h"

// One complete batch, ready to hand to Bridge.notify().
struct seismic_batch {
  // Absolute index of samples[0] in geophone_sample_count()'s monotonic
  // sequence. This is the whole gap-detection mechanism: the MPU knows the
  // next batch should start at first_sample_index + count, and any other
  // value is a real, measurable hole rather than one papered over by
  // concatenation. Survives nothing but a reboot, which resets it to 0 and
  // which the MPU reads as the discontinuity it is.
  uint32_t first_sample_index;
  // Always sent in full, with the tail past `count` zeroed. A fixed-length
  // array keeps the encoded size of a notify constant, which is what lets
  // the static_assert below be exact rather than a worst case over lengths -
  // and std::array is in the Bridge's published type map, so this needs no
  // variable-length or binary-blob encoding whose byte cost would have to be
  // guessed at.
  std::array<int16_t, SEISMIC_CAPTURE_BATCH_SAMPLES> samples;
  // How many leading entries of `samples` are real. Normally
  // SEISMIC_CAPTURE_BATCH_SAMPLES; short only when a sample arrived out of
  // sequence and closed the batch early - see seismic_capture_push().
  uint8_t count;
  // False if the geophone was unhealthy for *any* sample in this batch, not
  // just the last one. A partly-stale batch is not training data, and the
  // conservative reading is the only one that cannot quietly mislabel it.
  bool geophone_ok;
};

struct seismic_capture_state {
  seismic_batch pending;
  bool started;
};

void seismic_capture_reset(seismic_capture_state *state);

// Accumulates one accepted ADC sample. Returns true when `out` has been
// filled with a batch the caller should send, false when the batch is still
// filling.
//
// `sample_index` is geophone_sample_count() at the moment this sample was
// accepted. If it is not the index this batch expects next, the partial
// batch is emitted short through `out` and `raw` begins a fresh batch - so a
// discontinuity is never hidden inside a batch, only ever visible between
// two of them, which is the one place the MPU looks for it.
bool seismic_capture_push(seismic_capture_state *state, int16_t raw, uint32_t sample_index,
                          bool geophone_ok, seismic_batch *out);

// Worst-case MessagePack size of the notify this batch becomes, in bytes.
// Laid out field by field so the budget can be re-checked by reading it
// rather than by re-deriving it:
//
//   [2, "report_seismic_batch", [schema_version, first_sample_index, count,
//                                samples, geophone_ok]]
//
//   outer fixarray header .................. 1
//   message type 2 (positive fixint) ....... 1
//   "report_seismic_batch" (fixstr, 20) .... 1 + 20
//   args fixarray header ................... 1
//   schema_version (explicit uint8) ........ 2
//   first_sample_index (uint32) ............ 5
//   count (explicit uint8) ................. 2
//   samples (array16 header) ............... 3
//   samples (worst-case int16, 3 each) ..... 3N
//   geophone_ok (bool) ..................... 1
//
// 3 bytes per sample is the worst case, not the typical one: MessagePack
// spends 1 byte on -32..127 and 2 on the rest of int8 range, so a quiet
// trace encodes far smaller. Budgeting for the worst case is the point -
// the margin has to hold during the loud part of a footfall, which is
// exactly when every sample is large.
constexpr size_t seismic_capture_encoded_bytes(size_t samples) {
  return 37U + (3U * samples);
}

// The guard that makes the budget above load-bearing rather than a comment.
// An oversized notify is dropped silently by the Bridge, so the failure this
// prevents would otherwise look exactly like a geophone that stopped
// reporting - at the bench, weeks later, with the data already lost.
static_assert(seismic_capture_encoded_bytes(SEISMIC_CAPTURE_BATCH_SAMPLES) <=
                  BRIDGE_MAX_MESSAGE_BYTES,
              "a full seismic batch must fit one Bridge message - the Bridge drops an "
              "oversized notify silently, so this cannot be left to runtime");

#endif  // SENSORS_SEISMIC_CAPTURE_H
