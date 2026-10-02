#ifndef STUB_MODEL_METADATA_H
#define STUB_MODEL_METADATA_H
#include <cstdint>

// 8000, not 32000: the impulse is trained and deployed at 8 kHz because the
// corpus is 8 kHz throughout. The PANNs filterbank is defined at 32 kHz, and
// the 4x upsample to it happens inside the block. See ../README.md.
#define EI_CLASSIFIER_FREQUENCY 8000

// Studio generates this from ../../parameters.json into model_metadata.h -
// not into model_variables.h, where an earlier version of these stubs put
// it. One field per `param`, named by its `param` value and typed from its
// `type`, behind three fixed fields the generator always emits first.
// Checked against a real export of impulse 19 (deploy version 7).
// Keep in step with parameters.json - see README.md.
typedef struct {
    uint32_t block_id;
    uint16_t implementation_version;
    int axes;
    int mel_bins;   // "mel_bins",  int,     64
    int n_fft;      // "n_fft",     int,     1024
    int hop_size;   // "hop_size",  int,     320
    int fmin;       // "fmin",      int,     50
    int fmax;       // "fmax",      int,     14000
    bool peak_crop; // "peak_crop", boolean, false
} ei_dsp_config_panns_logmel_t;

#endif
