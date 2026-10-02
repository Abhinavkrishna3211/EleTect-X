// Edge Impulse integration shim for the PANNs log-mel block.
//
// Drop this file (and panns_logmel_core.hpp) into a C++ library exported
// from Studio for a project that uses the dsp-panns-logmel custom block.
// Because parameters.json declares `"cppType": "panns_logmel"`, the export
// emits into model-parameters/model_variables.h:
//
//   int extract_panns_logmel_features(signal_t *signal,
//                                     matrix_t *output_matrix,
//                                     void *config_ptr,
//                                     const float frequency);
//
// ...as a forward declaration only, plus a populated
// `ei_dsp_config_panns_logmel_t`. Supplying the definition is the
// integrator's job - Edge Impulse's docs are explicit that for a custom
// block "we cannot automatically generate optimized native code for the
// block, like we do for built-in processing blocks", which is also why a
// cloud build for target `arduino-uno-q` fails in about fifteen seconds
// with `Cannot build for "arduino-uno-q" as your project contains custom
// DSP blocks`. This file is the sanctioned answer to that message.
//
// Build path for this project (aarch64 Linux, giving a .eim the App Lab
// Edge Impulse brick can load). Studio's own "Linux (AARCH64)" target
// refuses this impulse for the reason above, so the .eim is built here
// instead, from the plain C++ library export:
//
//   git clone https://github.com/edgeimpulse/example-standalone-inferencing-linux
//   cp -r <studio C++ library export>/. example-standalone-inferencing-linux/
//   cd example-standalone-inferencing-linux
//   cp -r tensorflow-lite edge-impulse-sdk/tensorflow-lite
//   cp <this dir>/panns_logmel.cpp <this dir>/panns_logmel_core.hpp source/
//   # CXXSOURCES is an explicit list and does not glob source/, so add:
//   #   CXXSOURCES += source/panns_logmel.cpp
//   APP_EIM=1 USE_FULL_TFLITE=1 TARGET_LINUX_AARCH64=1
//     CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ make -j$(nproc)
//
// (that last one is a single command; it is split here only to fit)
//
// Four things in that recipe are not optional and are not obvious:
//
//   USE_FULL_TFLITE=1        without it the build targets TFLite-Micro with
//                            a statically sized arena, which this model's
//                            21.9 MB of float32 weights will not fit.
//   the tensorflow-lite copy  the Makefile compiles with
//                            -Iedge-impulse-sdk/tensorflow-lite, but the
//                            headers ship at the repo root and the export
//                            does not carry them.
//   a real cross toolchain    the upstream README builds aarch64 with plain
//                            clang, which only works on an aarch64 host.
//   an LF checkout            a clone made by Windows git arrives with CRLF,
//                            and a Makefile with trailing \r puts a control
//                            character inside every variable value.
//
// Numerical behaviour is verified against ../dsp.py by ./parity_main.cpp -
// see cpp/README.md. The dB agreement asserted there is what lets Studio's
// reported accuracy describe the deployed model.

#include "edge-impulse-sdk/classifier/ei_model_types.h"
#include "edge-impulse-sdk/dsp/numpy.hpp"
#include "edge-impulse-sdk/dsp/returntypes.hpp"
#include "edge-impulse-sdk/porting/ei_classifier_porting.h"
#include "model-parameters/model_metadata.h"

#include <vector>

// model_variables.h is deliberately not included, although it is the file
// that declares this function. Two reasons, either of which is enough.
//
// It defines rather than declares: the config instance, the label table and
// the DSP block array are all globals with external linkage, so a second
// translation unit including it is a duplicate-definition link error. The
// SDK includes it in exactly one place, from ei_run_classifier.h.
//
// It also does not stand alone. Studio writes the forward declaration with
// unqualified signal_t and matrix_t at file scope, which only parse because
// ei_run_dsp.h has already done `using namespace ei;` - a constraint the SDK
// states at ei_run_classifier.h:98 ("implicit dependency on ei_run_dsp.h, so
// must come after that include!"). Pulling that in here to satisfy a
// declaration we do not need would open the whole namespace this file is
// careful to keep closed.
//
// Nothing is lost by leaving it out. The declaration and this definition
// still have to agree, and the linker is what checks it: a signature that
// drifts shows up as an undefined reference to extract_panns_logmel_features
// when the .eim is linked, which is the same error, one stage later.

#include "panns_logmel_core.hpp"

// Everything borrowed from the SDK, named explicitly. The status
// enumerators live in namespace ei alongside the types, which is easy to
// miss - much of Edge Impulse's own DSP source opens the whole namespace,
// so unqualified EIDSP_OK reads as though it were global. Listing the
// five actually used documents the dependency and keeps the rest of that
// namespace out.
using ei::matrix_t;
using ei::signal_t;
using ei::EIDSP_INPUT_MATRIX_EMPTY;
using ei::EIDSP_MATRIX_SIZE_MISMATCH;
using ei::EIDSP_OK;
using ei::EIDSP_PARAMETER_INVALID;
using ei::EIDSP_SIGNAL_SIZE_MISMATCH;

namespace {

// The SDK hands DSP blocks their parameters through a void*, so the cast
// is unavoidable. Pulling it into one function keeps it to one place, and
// keeps the reason documented where the risk is: the struct is generated
// from parameters.json, so renaming a `param` in Studio silently renames
// a field here and this file stops compiling. That is the good failure -
// a rename that *kept* compiling would change the front end under a model
// trained on the old one.
const ei_dsp_config_panns_logmel_t* AsConfig(void* config_ptr) {
    return static_cast<const ei_dsp_config_panns_logmel_t*>(config_ptr);
}

}  // namespace

int extract_panns_logmel_features(signal_t* signal,
                                  matrix_t* output_matrix,
                                  void* config_ptr,
                                  const float frequency) {
    if (signal == nullptr || output_matrix == nullptr ||
        config_ptr == nullptr) {
        return EIDSP_PARAMETER_INVALID;
    }

    const ei_dsp_config_panns_logmel_t* cfg = AsConfig(config_ptr);

    // `frequency` is the rate the samples arrive at. It is *not* the rate
    // the filterbank is defined at: PANNs is 32 kHz always, and this
    // impulse is 8 kHz, so on the deployed path the two differ on every
    // window. Params::sample_rate is the analysis rate, which is why it
    // is left at its default rather than being set from `frequency`.
    const int input_rate = static_cast<int>(frequency);

    panns::Params p;
    p.n_fft = cfg->n_fft;
    p.hop_size = cfg->hop_size;
    p.mel_bins = cfg->mel_bins;
    p.fmin = cfg->fmin;
    p.fmax = cfg->fmax;

    // Rates that are not an integer divisor of 32 kHz are refused rather
    // than approximated. ../dsp.py would resample any rate at all through
    // librosa, but the rates this impulse can actually be fed are 8 kHz
    // (what it is trained at) and 16 kHz, and a rational resampler
    // written to cover rates nobody uses is untested code on the one path
    // that decides what the classifier sees.
    if (input_rate <= 0 || input_rate > panns::kPannsSampleRate ||
        panns::kPannsSampleRate % input_rate != 0) {
        ei_printf("ERR: panns_logmel needs an integer divisor of %d Hz, "
                  "got %d Hz.\n",
                  panns::kPannsSampleRate, input_rate);
        return EIDSP_PARAMETER_INVALID;
    }

    // `peak_crop` is intentionally not read. In ../dsp.py it is applied as
    // peak_window(y, sr, len(y)/sr), whose crop length always equals the
    // input length, so the function returns the signal unchanged - the
    // parameter is a no-op on the Studio path it was meant to affect.
    // Reproducing a no-op would add an untestable branch; diverging from
    // it would break parity. Documented here so the next reader does not
    // "fix" the omission. If peak cropping ever becomes real in the
    // Python, it has to be added here in the same commit.

    const size_t n_samples = signal->total_length;
    if (n_samples == 0) {
        return EIDSP_INPUT_MATRIX_EMPTY;
    }

    // The whole clip is materialised. Reflect padding reaches backwards
    // from the start and forwards from the end, so a streaming pull would
    // need a buffer of the signal anyway for the first and last frames,
    // and the target here is Linux on a QRB2210 where a 3 s clip is
    // 384 kB - not the 786 kB SRAM budget that shapes the MCU side.
    std::vector<float> samples(n_samples);
    int r = signal->get_data(0, n_samples, samples.data());
    if (r != EIDSP_OK) {
        return r;
    }

    // Must match ../dsp.py exactly: the decision is made from the data,
    // not from a project setting, on both sides.
    panns::ScaleIfInt16Counts(samples.data(), n_samples);

    const size_t capacity =
        static_cast<size_t>(output_matrix->rows) * output_matrix->cols;
    int frames = 0;
    const panns::Status status =
        panns::LogMelResample(samples.data(), n_samples, input_rate, p,
                              output_matrix->buffer, capacity, &frames);

    switch (status) {
        case panns::Status::kOk:
            break;
        case panns::Status::kBadParams:
            ei_printf("ERR: panns_logmel parameters invalid "
                      "(n_fft=%d hop=%d mels=%d fmin=%d fmax=%d)\n",
                      p.n_fft, p.hop_size, p.mel_bins, p.fmin, p.fmax);
            return EIDSP_PARAMETER_INVALID;
        case panns::Status::kSignalTooShort:
            ei_printf("ERR: panns_logmel needs more than %d samples "
                      "to reflect-pad, got %d\n",
                      p.n_fft / 2, static_cast<int>(n_samples));
            return EIDSP_SIGNAL_SIZE_MISMATCH;
        case panns::Status::kBufferTooSmall:
            ei_printf("ERR: panns_logmel needs %d floats, matrix holds %d\n",
                      frames * p.mel_bins, static_cast<int>(capacity));
            return EIDSP_MATRIX_SIZE_MISMATCH;
        case panns::Status::kUnsupportedRate:
            // Unreachable: the guard above already rejected these. Listed
            // so the switch stays exhaustive and -Wswitch keeps working
            // if another status is ever added.
            ei_printf("ERR: panns_logmel cannot resample %d Hz to %d Hz\n",
                      input_rate, p.sample_rate);
            return EIDSP_PARAMETER_INVALID;
    }

    // The SDK allocates the output as a flat (1, n_output_features) matrix
    // sized from the block's declared output, so reshaping it to
    // (frames, mel_bins) is a relabel, not a move: LogMel already wrote
    // frames-major, which is the order ../dsp.py flattens and therefore
    // the order the learning block was trained to read.
    output_matrix->rows = static_cast<uint32_t>(frames);
    output_matrix->cols = static_cast<uint32_t>(p.mel_bins);

    return EIDSP_OK;
}
