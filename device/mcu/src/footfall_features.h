// Footfall probability/feature placeholder - pure functions, no hardware
// calls, no Bridge, no config.h dependency baked into the signature (the
// caller reads FOOTFALL_PROBABILITY_SATURATION_C out of config.h and
// nothing here does, same discipline sta_lta.h documents for its own
// thresholds).
//
// Stand-in for the not-yet-built on-MCU TinyML footfall model (ml/seismic/
// is empty today - only STA/LTA exists). report_footfall_event
// (device/mpu/bridge/schema.md) needs a real probability and an 8-float
// feature_vector to notify the MPU with; this file derives both honestly
// from the STA/LTA result and the raw window rather than inventing
// placeholder numbers, same labeling discipline as device/mpu/services/
// reflex_loop.py's ALERT_PROBABILITY_THRESHOLD comment. Both are documented
// real-data stand-ins, not the final TinyML model or its eventual feature
// design (see docs/KNOWN_GAPS.md).

#ifndef FOOTFALL_FEATURES_H
#define FOOTFALL_FEATURES_H

#include <cstddef>

#include "sta_lta.h"

// Saturating placeholder confidence, anchored against the two real data
// points this project has (device/mcu/README.md's bench stomp test,
// docs/KNOWN_GAPS.md's 2026-08-14 entry): quiet-floor ratios (1.03-1.13)
// map near 0, the real stomp ratio (4.60) maps high (~0.9), without a hard
// clamp at exactly the stomp's own ratio - a single trial should not become
// a ceiling. Never negative, saturates toward 1.0 as peak_ratio grows
// without bound; a peak_ratio at or below 1.0 (sta == lta, no signal above
// the noise floor) returns exactly 0. Implemented as x^2/(x^2+c^2)
// (config.h's FOOTFALL_PROBABILITY_SATURATION_C), not an exp()-based
// formula - exp() does not link on the real board (docs/KNOWN_GAPS.md,
// 2026-08-14: libm_nano.a's expf needs __errno, this nostdlib firmware
// build provides none).
float footfall_probability_from_ratio(float peak_ratio);

// Real-data stand-in for the on-MCU TinyML model's eventual feature vector -
// not the final feature design (KNOWN_GAPS). Populates exactly 8 floats:
// [0] sta, [1] lta, [2] peak_ratio, [3] trigger_index (as float), [4] window
// min, [5] window max, [6] window mean, [7] window population stdev - the
// STA/LTA result plus cheap real statistics over the same window, rather
// than zeros or fabricated values. Never blocks, never allocates. n == 0
// returns a zero-filled vector rather than reading out of bounds.
void footfall_feature_vector(const float *window, size_t n, const sta_lta_result &result,
                              float out[8]);

#endif  // FOOTFALL_FEATURES_H
