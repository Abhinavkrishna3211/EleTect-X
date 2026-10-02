// PANNs log-mel front end, C++ port of ../dsp.py.
//
// Deliberately free of every Edge Impulse type. The EI-facing wrapper is
// panns_logmel.cpp; everything numerical lives here so it can be compiled
// and diffed against the Python on a dev host with no SDK present, which
// is what parity_main.cpp does. A DSP port that cannot be checked against
// its reference is a rewrite, not a port.
//
// Why this file has to exist at all
// ---------------------------------
// Edge Impulse cannot build a cloud deployment for a project containing a
// custom DSP block. Their documentation states the reason plainly: "we
// cannot automatically generate optimized native code for the block, like
// we do for built-in processing blocks." The documented remedy is the
// `cppType` field in parameters.json, which makes the C++ library export
// emit a forward declaration - here
// `extract_panns_logmel_features` - that the integrator implements. So
// this is the sanctioned path, not a workaround around a bug.
//
// The convention being reproduced is torchlibrosa's `Spectrogram` +
// `LogmelFilterBank`, which is what the PANNs AudioSet backbones were
// trained on: 32 kHz, 1024-point periodic-Hann STFT with centre padding,
// 320-sample hop, power spectrum, 64 Slaney-normalised mel filters over
// 50-14000 Hz, then 10*log10 with amin=1e-10 and no top_db ceiling. Every
// one of those is load-bearing; ../dsp.py's header explains why the stock
// MFE block is not a substitute.

#ifndef PANNS_LOGMEL_CORE_HPP_
#define PANNS_LOGMEL_CORE_HPP_

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace panns {

// Pi is spelled out here rather than taken from <cmath>: the familiar
// macro is a POSIX extension, not standard C++, and vanishes under a
// strict -std= setting. The Edge Impulse Linux makefile brings its own
// flags, so this header cannot assume any particular relaxation.
constexpr double kPi = 3.14159265358979323846;

// torchlibrosa's LogmelFilterBank defaults, named rather than inlined so
// the arithmetic below reads against the reference implementation.
constexpr float kAmin = 1e-10f;
constexpr float kRef = 1.0f;

// PANNs' fixed operating point. Every released checkpoint is trained
// here. Unlike the Python, this port cannot resample - there is no
// librosa on the target - so a mismatch is an error rather than a
// conversion. See panns_logmel.cpp.
constexpr int kPannsSampleRate = 32000;

struct Params {
    int sample_rate = kPannsSampleRate;
    int n_fft = 1024;
    int hop_size = 320;
    int mel_bins = 64;
    int fmin = 50;
    int fmax = 14000;
};

enum class Status {
    kOk = 0,
    kBadParams,      // a parameter is non-positive, or n_fft is not a power of two
    kSignalTooShort, // fewer samples than the centre padding needs to reflect
    kBufferTooSmall, // the caller's output buffer cannot hold frames * mel_bins
    kUnsupportedRate,// input rate is not an integer divisor of the analysis rate
};

// ---------------------------------------------------------------------
// Slaney mel scale (librosa's htk=False)
// ---------------------------------------------------------------------
// Linear below 1 kHz, logarithmic above. Computed in double because the
// filterbank is built once and its edges set every filter's support -
// a rounding error here shifts a whole mel bin, not one sample.

inline double HzToMelSlaney(double hz) {
    constexpr double kFSp = 200.0 / 3.0;
    constexpr double kMinLogHz = 1000.0;
    const double min_log_mel = kMinLogHz / kFSp;  // 15.0
    if (hz >= kMinLogHz) {
        const double logstep = std::log(6.4) / 27.0;
        return min_log_mel + std::log(hz / kMinLogHz) / logstep;
    }
    return hz / kFSp;
}

inline double MelToHzSlaney(double mel) {
    constexpr double kFSp = 200.0 / 3.0;
    constexpr double kMinLogHz = 1000.0;
    const double min_log_mel = kMinLogHz / kFSp;  // 15.0
    if (mel >= min_log_mel) {
        const double logstep = std::log(6.4) / 27.0;
        return kMinLogHz * std::exp(logstep * (mel - min_log_mel));
    }
    return kFSp * mel;
}

// librosa.filters.mel(..., htk=False, norm="slaney"), row-major
// (mel_bins, 1 + n_fft/2).
inline std::vector<float> MelFilterbank(const Params& p) {
    const int n_bins = p.n_fft / 2 + 1;
    std::vector<float> weights(static_cast<size_t>(p.mel_bins) * n_bins, 0.0f);

    // Bin centre frequencies of the rfft, in Hz.
    std::vector<double> fftfreqs(n_bins);
    for (int j = 0; j < n_bins; ++j) {
        fftfreqs[j] = static_cast<double>(j) * p.sample_rate / p.n_fft;
    }

    // mel_bins + 2 band edges, equally spaced on the mel scale.
    const int n_edges = p.mel_bins + 2;
    std::vector<double> mel_f(n_edges);
    const double min_mel = HzToMelSlaney(p.fmin);
    const double max_mel = HzToMelSlaney(p.fmax);
    for (int i = 0; i < n_edges; ++i) {
        const double m = min_mel + (max_mel - min_mel) * i / (n_edges - 1);
        mel_f[i] = MelToHzSlaney(m);
    }

    for (int i = 0; i < p.mel_bins; ++i) {
        const double lower_width = mel_f[i + 1] - mel_f[i];
        const double upper_width = mel_f[i + 2] - mel_f[i + 1];
        // Slaney normalisation: each filter is scaled to unit area rather
        // than unit peak, so a wide high-frequency filter does not
        // out-weigh a narrow low-frequency one purely by bandwidth.
        const double enorm = 2.0 / (mel_f[i + 2] - mel_f[i]);
        for (int j = 0; j < n_bins; ++j) {
            const double lower = (fftfreqs[j] - mel_f[i]) / lower_width;
            const double upper = (mel_f[i + 2] - fftfreqs[j]) / upper_width;
            double w = lower < upper ? lower : upper;
            if (w < 0.0) w = 0.0;
            weights[static_cast<size_t>(i) * n_bins + j] =
                static_cast<float>(w * enorm);
        }
    }
    return weights;
}

// ---------------------------------------------------------------------
// Radix-2 FFT
// ---------------------------------------------------------------------
// Two deliberate trades, both bought with the same currency: the whole
// DSP stage is roughly 300 frames of 1024 points - a few million flops -
// against a classifier block Studio estimates at 4,134 ms on this
// silicon. Arithmetic here is effectively free, so it is spent on being
// obviously correct.
//
// First, a full complex transform on real input, doing twice the
// arithmetic a packed real FFT would. The split-radix bookkeeping a
// packed version needs is the classic place to introduce a silent,
// spectrum-mangling bug in exactly this kind of port.
//
// Second, double precision internally, even though input and output are
// float. This is not fastidiousness - it was measured. With float32
// twiddles the rounding of each factor (~6e-8) compounds across all ten
// radix-2 stages, and the resulting noise floor sits right at the
// spectral leakage floor of a pure tone. Bins whose true value is 100 dB
// down then disagree with librosa by ~0.1 dB, because there the
// computation is reporting its own noise. In double the same probes
// agree to ~1e-5 dB. The float32 version was not *wrong* anywhere that
// changes a prediction - the disagreement was confined to bins outside
// the 80 dB band PANNs normalisation discards, and torchlibrosa itself
// is further from an exact float64 reference than either. But a parity
// test that has to be told which cells to ignore is a weaker test, and
// this stage was not the place to spend the budget.

inline bool IsPowerOfTwo(int n) { return n > 0 && (n & (n - 1)) == 0; }

class Fft {
public:
    explicit Fft(int n) : n_(n), cos_(n / 2), sin_(n / 2), rev_(n) {
        for (int i = 0; i < n / 2; ++i) {
            const double a = -2.0 * kPi * i / n;
            cos_[i] = std::cos(a);
            sin_[i] = std::sin(a);
        }
        int log2n = 0;
        while ((1 << log2n) < n) ++log2n;
        for (int i = 0; i < n; ++i) {
            int r = 0;
            for (int b = 0; b < log2n; ++b) {
                if (i & (1 << b)) r |= 1 << (log2n - 1 - b);
            }
            rev_[i] = r;
        }
    }

    // In-place decimation-in-time transform of (re, im), each length n.
    void Forward(double* re, double* im) const {
        for (int i = 0; i < n_; ++i) {
            const int j = rev_[i];
            if (j > i) {
                std::swap(re[i], re[j]);
                std::swap(im[i], im[j]);
            }
        }
        for (int len = 2; len <= n_; len <<= 1) {
            const int half = len / 2;
            const int step = n_ / len;
            for (int base = 0; base < n_; base += len) {
                for (int k = 0; k < half; ++k) {
                    const double wr = cos_[k * step];
                    const double wi = sin_[k * step];
                    const int a = base + k;
                    const int b = a + half;
                    const double xr = re[b] * wr - im[b] * wi;
                    const double xi = re[b] * wi + im[b] * wr;
                    re[b] = re[a] - xr;
                    im[b] = im[a] - xi;
                    re[a] += xr;
                    im[a] += xi;
                }
            }
        }
    }

    int size() const { return n_; }

private:
    int n_;
    std::vector<double> cos_;
    std::vector<double> sin_;
    std::vector<int> rev_;
};

// ---------------------------------------------------------------------
// The front end
// ---------------------------------------------------------------------

inline int NumFrames(size_t n_samples, int hop_size) {
    // librosa's centre-padded frame count: 1 + n // hop.
    return 1 + static_cast<int>(n_samples / static_cast<size_t>(hop_size));
}

// Compute the log-mel spectrogram of `samples` into `out`, laid out as
// (frames, mel_bins) row-major - the same order ../dsp.py flattens, and
// the order the learning block's input expects.
//
// `samples` must already be in [-1, 1): the int16 rescale lives in the
// caller, because only the caller knows what the data source hands over.
//
// Returns Status::kOk and writes *out_frames on success.
inline Status LogMel(const float* samples,
                     size_t n_samples,
                     const Params& p,
                     float* out,
                     size_t out_capacity,
                     int* out_frames) {
    if (p.n_fft <= 0 || p.hop_size <= 0 || p.mel_bins <= 0 ||
        p.sample_rate <= 0 || p.fmin < 0 || p.fmax <= p.fmin ||
        !IsPowerOfTwo(p.n_fft)) {
        return Status::kBadParams;
    }

    const int pad = p.n_fft / 2;
    // numpy's "reflect" mirrors without repeating the edge sample, which
    // needs at least pad+1 samples to draw from on each side.
    if (n_samples < static_cast<size_t>(pad) + 1) {
        return Status::kSignalTooShort;
    }

    const int frames = NumFrames(n_samples, p.hop_size);
    const size_t needed = static_cast<size_t>(frames) * p.mel_bins;
    if (out_capacity < needed) {
        return Status::kBufferTooSmall;
    }

    // Centre padding, materialised rather than index-mapped: the frame
    // loop below is already the hot path and an extra branch per sample
    // there costs more than this one buffer.
    const size_t padded_n = n_samples + 2 * static_cast<size_t>(pad);
    std::vector<float> padded(padded_n);
    for (int i = 0; i < pad; ++i) {
        padded[i] = samples[pad - i];                              // reflect left
        padded[padded_n - 1 - i] = samples[n_samples - 1 - (pad - i)];  // reflect right
    }
    for (size_t i = 0; i < n_samples; ++i) {
        padded[pad + i] = samples[i];
    }

    // Periodic Hann, matching scipy.signal.get_window("hann", N,
    // fftbins=True) - which is what librosa's window="hann" resolves to.
    // The symmetric variant differs by one sample of phase and shows up
    // as a small, consistent bias across every frame.
    std::vector<double> window(p.n_fft);
    for (int i = 0; i < p.n_fft; ++i) {
        window[i] = 0.5 * (1.0 - std::cos(2.0 * kPi * i / p.n_fft));
    }

    const std::vector<float> mel_w = MelFilterbank(p);
    const int n_bins = p.n_fft / 2 + 1;
    const Fft fft(p.n_fft);

    std::vector<double> re(p.n_fft), im(p.n_fft), power(n_bins);
    const float ref_db = 10.0f * std::log10(kRef > kAmin ? kRef : kAmin);

    for (int t = 0; t < frames; ++t) {
        const size_t start = static_cast<size_t>(t) * p.hop_size;
        for (int i = 0; i < p.n_fft; ++i) {
            re[i] = static_cast<double>(padded[start + i]) * window[i];
            im[i] = 0.0;
        }
        fft.Forward(re.data(), im.data());
        for (int j = 0; j < n_bins; ++j) {
            power[j] = re[j] * re[j] + im[j] * im[j];
        }


        float* row = out + static_cast<size_t>(t) * p.mel_bins;
        for (int m = 0; m < p.mel_bins; ++m) {
            const float* w = &mel_w[static_cast<size_t>(m) * n_bins];
            // 513 products per bin, accumulated in double for the same
            // reason the transform is: the near-silent bins that land on
            // the amin clamp are where an accumulation-order difference
            // shows up largest once converted to dB.
            double acc = 0.0;
            for (int j = 0; j < n_bins; ++j) {
                acc += static_cast<double>(w[j]) * power[j];
            }
            const float v = acc > kAmin ? static_cast<float>(acc) : kAmin;
            row[m] = 10.0f * std::log10(v) - ref_db;
        }
    }

    *out_frames = frames;
    return Status::kOk;
}

// ---------------------------------------------------------------------
// Resampling to the PANNs rate
// ---------------------------------------------------------------------
//
// ../dsp.py calls librosa.resample() for anything that is not 32 kHz, and
// this project needs it: the trained impulse is 8 kHz - every clip in the
// corpus is natively 8 kHz, because the largest source is - so on the
// deployed path *every* window goes through a 4x upsample before the
// filterbank ever runs. A port that refuses instead of resampling is a
// port that never executes.
//
// The design below is not a textbook default. librosa.load() - which is
// what embed.load_clip() called for every clip this model trained and was
// scored on - resamples with soxr_hq, and soxr_hq was measured here rather
// than assumed: flat to 3724 Hz, -24 dB by 3900 Hz, -141 dB at 4000 Hz,
// and -131 dB or better above it. Putting the cutoff at Nyquist the way
// the textbook says leaves half the transition band above 4 kHz; that
// filter passed -23 dB where soxr passes -60, and the mel bins at the band
// edge disagreed by tens of dB as a result.
//
// These are own-work coefficients matched to that measured response, not
// soxr's. soxr is LGPL and this tree is MIT, so a table lifted out of its
// impulse response would be a licensing question rather than a technical
// one. What is borrowed is the specification, and a specification here is
// a measurement.

// Fraction of the input Nyquist that stays flat.
//
// soxr_hq's own -0.1 dB point sits at 3724/4000 = 0.931, but copying that
// number is not the same as matching the filter: a Kaiser design placed
// there rolls off later than soxr through the transition, and the two
// disagree by up to 7.8 dB across 3724-4000 Hz. Sweeping the parameter
// against soxr's measured response instead puts the best fit at 0.920,
// which cuts the RMS transition-band error from 4.15 dB to 1.45 dB and
// needs fewer taps (921 rather than 1067) while doing it. Fitted, not
// quoted.
constexpr double kPassbandFraction = 0.920;

// Stopband attenuation to design for, in dB. soxr_hq holds -131 dB; 140
// here lands at -139 dB, so the port is never the noisier of the two.
constexpr double kStopbandAttenDb = 140.0;

// Modified Bessel function of the first kind, order zero, by its defining
// series. The Kaiser window needs exactly this and nothing else, and the
// series reaches double precision inside a few dozen terms at the beta
// this design uses - no reason to pull in a special-function library for
// one call, on a target where every dependency has to be justified.
inline double BesselI0(double x) {
    const double half = 0.5 * x;
    double term = 1.0;
    double sum = 1.0;
    for (int k = 1; k < 128; ++k) {
        const double r = half / static_cast<double>(k);
        term *= r * r;
        sum += term;
        if (term < 1e-18 * sum) break;
    }
    return sum;
}

// numpy's normalised sinc: sin(pi x) / (pi x), and 1 at the origin.
inline double Sinc(double x) {
    if (x == 0.0) return 1.0;
    const double px = kPi * x;
    return std::sin(px) / px;
}

// A linear-phase interpolation filter for integer upsampling.
struct Upsampler {
    int factor = 1;
    std::vector<double> taps;  // odd length, symmetric, sums to `factor`
};

// Kaiser windowed-sinc lowpass, using Kaiser's own order and beta
// estimates. A factor of 1 or less yields an empty filter, which
// UpsampleInteger treats as a copy.
inline Upsampler DesignUpsampler(int factor,
                                 double fs_out,
                                 double pass_fraction = kPassbandFraction,
                                 double atten_db = kStopbandAttenDb) {
    Upsampler u;
    if (factor <= 1 || fs_out <= 0.0) {
        u.factor = factor > 0 ? factor : 1;
        return u;
    }
    u.factor = factor;

    // Band edges expressed at the *output* rate, which is the rate the
    // filter actually runs at once the signal has been zero-stuffed.
    const double nyquist_in = 0.5 * fs_out / factor;
    const double f_stop = nyquist_in;
    const double f_pass = pass_fraction * nyquist_in;

    const double fc = 0.5 * (f_pass + f_stop) / fs_out;
    const double df = (f_stop - f_pass) / fs_out;
    const double beta = 0.1102 * (atten_db - 8.7);

    int n_taps = static_cast<int>(
        std::ceil((atten_db - 8.0) / (2.285 * 2.0 * kPi * df)));
    if (n_taps < 3) n_taps = 3;
    n_taps |= 1;  // odd, so there is an exact centre tap and zero delay

    u.taps.resize(static_cast<size_t>(n_taps));
    const double centre = 0.5 * (n_taps - 1);
    const double i0_beta = BesselI0(beta);
    double sum = 0.0;
    for (int n = 0; n < n_taps; ++n) {
        const double d = static_cast<double>(n) - centre;
        const double ratio = d / centre;
        const double arg = 1.0 - ratio * ratio;
        const double w =
            BesselI0(beta * std::sqrt(arg > 0.0 ? arg : 0.0)) / i0_beta;
        const double h = 2.0 * fc * Sinc(2.0 * fc * d) * w;
        u.taps[static_cast<size_t>(n)] = h;
        sum += h;
    }
    // Normalise to a DC gain of `factor`, which is what zero stuffing costs.
    const double scale = static_cast<double>(factor) / sum;
    for (size_t i = 0; i < u.taps.size(); ++i) u.taps[i] *= scale;
    return u;
}

// Upsample by an integer factor: zero-stuff, then filter. Evaluated in
// polyphase form, so the multiplies against the stuffed zeros never
// happen - at 1067 taps and 4x that is the difference between 340M and
// 85M multiply-accumulates for a ten-second window.
//
// Output length is n * factor, delay-compensated by the centre tap, which
// is what numpy's convolve(...)[centre:centre+len] slice does and what
// librosa returns.
inline void UpsampleInteger(const float* x,
                            size_t n,
                            const Upsampler& u,
                            std::vector<float>* out) {
    const int l = u.factor;
    if (l <= 1 || u.taps.empty()) {
        out->assign(x, x + n);
        return;
    }
    const int n_taps = static_cast<int>(u.taps.size());
    const int centre = (n_taps - 1) / 2;
    const size_t n_out = n * static_cast<size_t>(l);
    out->assign(n_out, 0.0f);
    if (n == 0) return;

    const double* h = u.taps.data();
    const long long last = static_cast<long long>(n) - 1;
    for (size_t m = 0; m < n_out; ++m) {
        // y[m] = sum_i h[m + centre - i*l] * x[i], over the taps in range.
        const long long top = static_cast<long long>(m) + centre;
        long long i_hi = top / l;
        long long i_lo = (top - (n_taps - 1) + l - 1) / l;  // ceil division
        if (i_lo < 0) i_lo = 0;
        if (i_hi > last) i_hi = last;
        double acc = 0.0;
        for (long long i = i_lo; i <= i_hi; ++i) {
            acc += h[top - i * l] * static_cast<double>(x[static_cast<size_t>(i)]);
        }
        (*out)[m] = static_cast<float>(acc);
    }
}

// Log-mel of a signal that may not already be at the analysis rate.
//
// `input_rate` is the rate the samples arrive at; `p.sample_rate` stays
// the rate the STFT and filterbank are defined at, which for PANNs is
// always 32 kHz. Equal rates delegate straight to LogMel, so the verified
// no-resample path stays bit-for-bit what parity_cpp.py measured.
//
// Only integer upsampling is supported, and that is a real restriction
// rather than a simplification: the rates this project can present are
// 8 kHz (the trained impulse) and 16 kHz, both exact divisors. A
// non-divisor needs a rational resampler, and silently approximating one
// would be exactly the quiet front-end drift this file exists to prevent.
inline Status LogMelResample(const float* samples,
                             size_t n_samples,
                             int input_rate,
                             const Params& p,
                             float* out,
                             size_t out_capacity,
                             int* out_frames) {
    if (input_rate <= 0) return Status::kBadParams;
    if (input_rate == p.sample_rate) {
        return LogMel(samples, n_samples, p, out, out_capacity, out_frames);
    }
    if (input_rate > p.sample_rate || p.sample_rate % input_rate != 0) {
        return Status::kUnsupportedRate;
    }

    const int factor = p.sample_rate / input_rate;
    const Upsampler u = DesignUpsampler(factor, static_cast<double>(p.sample_rate));
    std::vector<float> up;
    UpsampleInteger(samples, n_samples, u, &up);
    return LogMel(up.data(), up.size(), p, out, out_capacity, out_frames);
}

// Edge Impulse serves int16 PCM as raw counts from some data sources and
// as floats from others. PANNs trained on [-1, 1), and a 32768x amplitude
// error is a +90 dB offset on every mel bin that the frozen bn0 layer
// cannot absorb. ../dsp.py decides this on evidence rather than on a
// project setting, and so does this - the two must agree or Studio's
// accuracy figures stop describing the deployed model.
inline void ScaleIfInt16Counts(float* samples, size_t n) {
    float peak = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        const float a = std::fabs(samples[i]);
        if (a > peak) peak = a;
    }
    if (peak > 1.0f) {
        for (size_t i = 0; i < n; ++i) samples[i] /= 32768.0f;
    }
}

}  // namespace panns

#endif  // PANNS_LOGMEL_CORE_HPP_
