#include "seismic_capture.h"

#include <cstddef>

namespace {

// Emits whatever the batch currently holds and leaves `state` empty.
// Separated out because both exit paths below need it and getting one of
// them subtly different is how a batch ends up reused across a gap.
void close_batch(seismic_capture_state *state, seismic_batch *out) {
  // Zero the tail before handing it over. The array is sent in full and
  // `count` says how much of it is real, so a short batch that kept the
  // previous batch's samples in its tail would put stale ground motion on
  // the wire for a receiver that trusted the array over the count.
  for (size_t i = state->pending.count; i < SEISMIC_CAPTURE_BATCH_SAMPLES; ++i) {
    state->pending.samples[i] = 0;
  }
  *out = state->pending;
  state->started = false;
  state->pending.count = 0;
}

void begin_batch(seismic_capture_state *state, int16_t raw, uint32_t sample_index,
                 bool geophone_ok) {
  state->started = true;
  state->pending.first_sample_index = sample_index;
  state->pending.samples[0] = raw;
  state->pending.count = 1;
  state->pending.geophone_ok = geophone_ok;
}

}  // namespace

void seismic_capture_reset(seismic_capture_state *state) {
  state->started = false;
  state->pending.first_sample_index = 0;
  state->pending.count = 0;
  state->pending.geophone_ok = false;
  state->pending.samples.fill(0);
}

bool seismic_capture_push(seismic_capture_state *state, int16_t raw, uint32_t sample_index,
                          bool geophone_ok, seismic_batch *out) {
  if (!state->started) {
    begin_batch(state, raw, sample_index, geophone_ok);
    return false;
  }

  // The batch expects a contiguous run. Unsigned addition is rollover-safe
  // and wraps the same way geophone_sample_count() does, so the one sample
  // at the uint32 boundary is treated as continuous rather than as a false
  // gap - the same idiom rule_gate_apply() and geophone_service() use for
  // millis().
  const uint32_t expected = state->pending.first_sample_index + state->pending.count;
  if (sample_index != expected) {
    // Out of sequence: hand back what we have rather than concatenating
    // across the hole. The MPU sees first_sample_index + count not matching
    // the next batch's first_sample_index, which is exactly the gap, stated
    // rather than smoothed over.
    close_batch(state, out);
    begin_batch(state, raw, sample_index, geophone_ok);
    return true;
  }

  state->pending.samples[state->pending.count] = raw;
  ++state->pending.count;
  // Unhealthy at any point in the batch makes the whole batch unhealthy -
  // never the other way round, so a sensor that recovers mid-batch cannot
  // launder the stale samples in front of it.
  state->pending.geophone_ok = state->pending.geophone_ok && geophone_ok;

  if (state->pending.count >= SEISMIC_CAPTURE_BATCH_SAMPLES) {
    close_batch(state, out);
    return true;
  }
  return false;
}
