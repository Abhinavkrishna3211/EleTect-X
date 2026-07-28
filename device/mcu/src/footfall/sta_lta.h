// STA/LTA footfall trigger - pure function, no hardware calls.
//
// Short-term-average / long-term-average ratio detector. Takes a fixed window
// of seismic samples and the caller's own thresholds; returns whether the
// window contains a trigger and where. Zero ADC calls, zero Bridge calls,
// zero config.h dependency baked into the signature - the caller reads
// thresholds out of config.h and passes them in, so this file is testable
// with nothing but plain arrays (ENGINEERING_CONVENTIONS.md 2).

#ifndef FOOTFALL_STA_LTA_H
#define FOOTFALL_STA_LTA_H

#include <cstddef>

struct sta_lta_result {
  float sta;            // short-term average over the trigger window
  float lta;             // long-term average over the trigger window
  float peak_ratio;      // sta / lta at the reported trigger_index
  size_t trigger_index;  // index into x where peak_ratio was reached
  bool triggered;         // true if peak_ratio ever reached trigger_ratio
};

// Slides an sta_n-wide short-term window and an lta_n-wide long-term window
// across x (both mean absolute value, not RMS - the ratio is then exactly
// hand-computable, which is what makes a known-answer test meaningful rather
// than a "returns a float" test). Reports the highest sta/lta ratio reached
// and whether it crossed trigger_ratio.
//
// Never blocks, never touches a sensor, never allocates. Degenerate inputs
// (n == 0, lta_n > n, an all-zero window - the zero-filled-on-timeout case
// from read_seismic_window()) return triggered = false with peak_ratio = 0,
// not a crash or a division by zero.
sta_lta_result sta_lta_detect(const float *x, size_t n, size_t sta_n,
                               size_t lta_n, float trigger_ratio);

#endif  // FOOTFALL_STA_LTA_H
