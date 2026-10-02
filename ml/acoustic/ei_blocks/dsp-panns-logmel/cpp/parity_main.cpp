// Host harness: runs the pure DSP core over a raw float32 clip and writes
// the resulting log-mel spectrogram back out, so parity_cpp.py can diff it
// against ../dsp.py on a development machine with no Edge Impulse SDK and
// no target board present.
//
// Deliberately free of the SDK. The point of splitting the core out of
// panns_logmel.cpp is that the arithmetic can be checked here, where the
// Python reference actually runs, instead of only on hardware where a
// disagreement shows up as an unexplained accuracy drop.
//
//   g++ -O2 -std=c++17 parity_main.cpp -o parity_cpp
//   ./parity_cpp in.f32 out.bin 32000 1024 320 64 50 14000 [in_rate]
//
// The optional tenth argument is the rate the samples arrive at, as
// distinct from the analysis rate in argument three. Supplying it
// exercises LogMelResample, which is the path the deployed 8 kHz impulse
// takes; leaving it off exercises LogMel directly. Both matter, and they
// are different code.
//
// Input:  raw little-endian float32 samples, mono.
// Output: int32 frames, int32 mel_bins, then frames*mel_bins float32
//         values in row-major (frame, mel) order.

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "panns_logmel_core.hpp"

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr,
                     "usage: %s <in.f32> <out.bin> "
                     "[sr n_fft hop mels fmin fmax [in_rate]]\n",
                     argv[0]);
        return 2;
    }

    panns::Params p;
    if (argc >= 9) {
        p.sample_rate = std::atoi(argv[3]);
        p.n_fft = std::atoi(argv[4]);
        p.hop_size = std::atoi(argv[5]);
        p.mel_bins = std::atoi(argv[6]);
        p.fmin = std::atoi(argv[7]);
        p.fmax = std::atoi(argv[8]);
    }
    const int in_rate = argc >= 10 ? std::atoi(argv[9]) : p.sample_rate;

    std::FILE* fin = std::fopen(argv[1], "rb");
    if (fin == nullptr) {
        std::fprintf(stderr, "cannot open %s\n", argv[1]);
        return 2;
    }
    std::fseek(fin, 0, SEEK_END);
    const long bytes = std::ftell(fin);
    std::fseek(fin, 0, SEEK_SET);
    const size_t n = static_cast<size_t>(bytes) / sizeof(float);
    std::vector<float> samples(n);
    if (std::fread(samples.data(), sizeof(float), n, fin) != n) {
        std::fprintf(stderr, "short read on %s\n", argv[1]);
        std::fclose(fin);
        return 2;
    }
    std::fclose(fin);

    // Same data-driven rescale the deployed wrapper applies, so the
    // harness exercises the path that actually ships rather than a
    // cleaned-up variant of it.
    panns::ScaleIfInt16Counts(samples.data(), n);

    // Upsampling multiplies the sample count before the STFT ever sees
    // it, so size the buffer from the post-resample length or the last
    // frames simply have nowhere to go.
    const int factor =
        (in_rate > 0 && in_rate < p.sample_rate && p.sample_rate % in_rate == 0)
            ? p.sample_rate / in_rate
            : 1;
    const int max_frames =
        panns::NumFrames(n * static_cast<size_t>(factor), p.hop_size);
    std::vector<float> out(static_cast<size_t>(max_frames) * p.mel_bins);
    int frames = 0;
    const panns::Status st =
        panns::LogMelResample(samples.data(), n, in_rate, p, out.data(),
                              out.size(), &frames);
    if (st != panns::Status::kOk) {
        std::fprintf(stderr, "LogMel failed with status %d\n",
                     static_cast<int>(st));
        return 1;
    }

    std::FILE* fout = std::fopen(argv[2], "wb");
    if (fout == nullptr) {
        std::fprintf(stderr, "cannot open %s for writing\n", argv[2]);
        return 2;
    }
    const int32_t hdr[2] = {frames, p.mel_bins};
    std::fwrite(hdr, sizeof(int32_t), 2, fout);
    std::fwrite(out.data(), sizeof(float),
                static_cast<size_t>(frames) * p.mel_bins, fout);
    std::fclose(fout);
    return 0;
}
