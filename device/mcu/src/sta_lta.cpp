#include "sta_lta.h"

#include <cmath>

namespace {

// Mean absolute value over x[start, start+len). Caller guarantees the range
// is in bounds.
float mean_abs(const float *x, size_t start, size_t len) {
  float sum = 0.0f;
  for (size_t i = 0; i < len; ++i) {
    sum += std::fabs(x[start + i]);
  }
  return sum / static_cast<float>(len);
}

}  // namespace

sta_lta_result sta_lta_detect(const float *x, size_t n, size_t sta_n,
                               size_t lta_n, float trigger_ratio) {
  sta_lta_result result{};
  result.sta = 0.0f;
  result.lta = 0.0f;
  result.peak_ratio = 0.0f;
  result.trigger_index = 0;
  result.triggered = false;

  if (x == nullptr || sta_n == 0 || lta_n == 0 || lta_n > n ||
      sta_n > lta_n) {
    return result;
  }

  // The long-term window must be fully populated before a ratio means
  // anything, so the slide starts once lta_n samples are available and the
  // short-term window (aligned to the end of the long-term one) still fits.
  for (size_t end = lta_n; end <= n; ++end) {
    const size_t lta_start = end - lta_n;
    const size_t sta_start = end - sta_n;

    const float lta = mean_abs(x, lta_start, lta_n);
    const float sta = mean_abs(x, sta_start, sta_n);

    // A silent/zero-filled window (the read_seismic_window() timeout
    // contract) has lta == 0 - report no trigger rather than dividing by
    // zero.
    const float ratio = (lta > 0.0f) ? (sta / lta) : 0.0f;

    if (ratio > result.peak_ratio) {
      result.peak_ratio = ratio;
      result.sta = sta;
      result.lta = lta;
      result.trigger_index = end - 1;
    }
  }

  result.triggered = result.peak_ratio >= trigger_ratio;
  return result;
}
