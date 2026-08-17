#include "footfall_features.h"

#include <cmath>

#include "config.h"

float footfall_probability_from_ratio(float peak_ratio) {
  if (peak_ratio <= 1.0f) {
    return 0.0f;
  }
  // x^2/(x^2+c^2), not exp() - see config.h's FOOTFALL_PROBABILITY_SATURATION_C
  // comment for why: exp() pulls in expf from the real board's libm_nano.a,
  // which needs __errno and this nostdlib firmware build doesn't provide one.
  const float x = peak_ratio - 1.0f;
  const float x2 = x * x;
  const float c2 = FOOTFALL_PROBABILITY_SATURATION_C * FOOTFALL_PROBABILITY_SATURATION_C;
  return x2 / (x2 + c2);
}

void footfall_feature_vector(const float *window, size_t n, const sta_lta_result &result,
                              float out[8]) {
  out[0] = result.sta;
  out[1] = result.lta;
  out[2] = result.peak_ratio;
  out[3] = static_cast<float>(result.trigger_index);

  if (n == 0) {
    out[4] = out[5] = out[6] = out[7] = 0.0f;
    return;
  }

  float min_v = window[0];
  float max_v = window[0];
  float sum = 0.0f;
  for (size_t i = 0; i < n; ++i) {
    if (window[i] < min_v) {
      min_v = window[i];
    }
    if (window[i] > max_v) {
      max_v = window[i];
    }
    sum += window[i];
  }
  const float mean = sum / static_cast<float>(n);

  float sq_sum = 0.0f;
  for (size_t i = 0; i < n; ++i) {
    const float d = window[i] - mean;
    sq_sum += d * d;
  }

  out[4] = min_v;
  out[5] = max_v;
  out[6] = mean;
  out[7] = std::sqrt(sq_sum / static_cast<float>(n));
}
