"""Assert this block's log-mel equals torchlibrosa's, which is what PANNs trained on.

The whole value of the block is that it is not an approximation of the PANNs
front end, so that claim needs a test rather than a comment. This runs the real
torchlibrosa `Spectrogram` + `LogmelFilterBank` modules - the same objects the
backbone instantiates - against `dsp.logmel`.

What is compared, and why not raw dB everywhere. The two implementations are
numerically different routes to the same quantity: torchlibrosa computes the
STFT as a conv1d against a DFT matrix and projects with
`matmul(spectrogram, melW)`, while this block uses an FFT and `melW @ power`.
Both accumulate 513 float32 products per mel bin, in different orders. Where a
bin carries real energy that is float32 rounding, order 1e-4 dB. Where a bin is
near-silent - a pure tone leaves most bins at the `amin=1e-10` clamp floor, some
95 dB down - the same absolute rounding becomes a large *relative* error, and dB
magnifies it to ~5e-2. That is not a convention divergence, and the backbone
never sees it as one: those cells are already pinned at the floor.

So the assertions are:
  1. log-mel agreement over cells within 80 dB of the clip peak, the range that
     carries signal;
  2. agreement of the Cnn10 *embedding*, relative to its own scale. This is the
     end-to-end quantity - if it holds, the pretrained weights are being fed the
     distribution they expect, whatever happens at the noise floor.

Real test-split clips are used for the assertions, because synthetic signals are
exactly the pathological case described above. Synthetic signals are still run,
but reported rather than asserted on.

Run: python parity_check.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "harness")))

from dsp import PANNS_SAMPLE_RATE, generate_features, logmel

N_FFT, HOP, MELS, FMIN, FMAX = 1024, 320, 64, 50, 14000
SPLIT = os.path.join(os.path.dirname(__file__), "..", "..", "harness", "split.json")

# Cells more than 80 dB below the clip peak are at or near the amin floor; see
# the module docstring. Within that range the two routes differ only by float32
# accumulation order.
DYNAMIC_RANGE_DB = 80.0
TOL_DB = 1e-2
TOL_EMBEDDING_REL = 1e-3
N_CLIPS = 24


def torchlibrosa_logmel(y: np.ndarray) -> np.ndarray:
    """(frames, mel_bins) from the actual torchlibrosa modules PANNs instantiates."""
    import torch
    from torchlibrosa.stft import LogmelFilterBank, Spectrogram

    spec = Spectrogram(
        n_fft=N_FFT, hop_length=HOP, win_length=N_FFT, window="hann",
        center=True, pad_mode="reflect", freeze_parameters=True,
    )
    mel = LogmelFilterBank(
        sr=PANNS_SAMPLE_RATE, n_fft=N_FFT, n_mels=MELS, fmin=FMIN, fmax=FMAX,
        ref=1.0, amin=1e-10, top_db=None, freeze_parameters=True,
    )
    with torch.no_grad():
        return mel(spec(torch.from_numpy(y[None, :]))).numpy()[0, 0]


def embed(backbone, mel: np.ndarray) -> np.ndarray:
    """Cnn10's 512-d embedding for one log-mel frame stack.

    Mirrors export_panns.make_module's `embed`, which is the code path that
    actually ships, rather than the vendored training-mode forward pass.
    """
    import torch

    x = torch.from_numpy(mel)[None, None, :, :]
    with torch.no_grad():
        x = backbone.bn0(x.transpose(1, 3)).transpose(1, 3)
        for cb in (backbone.conv_block1, backbone.conv_block2,
                   backbone.conv_block3, backbone.conv_block4):
            x = cb(x, pool_size=(2, 2), pool_type="avg")
        x = torch.mean(x, dim=3)
        x = torch.max(x, dim=2)[0] + torch.mean(x, dim=2)
        return torch.relu(backbone.fc1(x)).numpy()[0]


def synthetic_report() -> None:
    """Report, without asserting, on signals that sit at the clamp floor."""
    rng = np.random.default_rng(0)
    print("synthetic signals (reported, not asserted - see module docstring):")
    for seconds in (3.0, 10.0):
        n = int(PANNS_SAMPLE_RATE * seconds)
        cases = (
            ("white noise", (rng.standard_normal(n) * 0.1).astype(np.float32)),
            ("tone 440 Hz", np.sin(2 * np.pi * 440 * np.arange(n) / PANNS_SAMPLE_RATE).astype(np.float32)),
            ("silence", np.zeros(n, dtype=np.float32)),
            ("impulse", np.eye(1, n, n // 3, dtype=np.float32)[0]),
        )
        for name, y in cases:
            ref, got = torchlibrosa_logmel(y), logmel(y)
            assert got.shape == ref.shape, f"{name} {seconds}s: {got.shape} vs {ref.shape}"
            d = np.abs(got - ref)
            near = ref > (ref.max() - DYNAMIC_RANGE_DB)
            in_range = float(d[near].max()) if near.any() else 0.0
            print(f"  {seconds:>4.0f}s  {name:<12}  {got.shape!s:<12}"
                  f"  all cells {float(d.max()):.2e} dB"
                  f"   top {DYNAMIC_RANGE_DB:.0f} dB {in_range:.2e} dB")


def clip_parity() -> tuple[float, float]:
    """(worst dB error in range, worst relative embedding error) over real clips."""
    from embed import load_clip
    from export_panns import build_backbone

    with open(SPLIT, encoding="utf-8") as fh:
        rows = [r for r in json.load(fh)["records"] if r["split"] == "test"][:N_CLIPS]
    backbone = build_backbone("cnn10")

    worst_db = worst_rel = 0.0
    for r in rows:
        y = load_clip(r["path"], 10.0)
        ref, got = torchlibrosa_logmel(y), logmel(y)
        d = np.abs(got - ref)
        near = ref > (ref.max() - DYNAMIC_RANGE_DB)
        worst_db = max(worst_db, float(d[near].max()))
        a, b = embed(backbone, ref), embed(backbone, got)
        scale = max(float(np.max(np.abs(a))), 1e-9)
        worst_rel = max(worst_rel, float(np.max(np.abs(a - b))) / scale)
    print(f"\n{len(rows)} real test clips at 10 s:")
    print(f"  log-mel, top {DYNAMIC_RANGE_DB:.0f} dB : {worst_db:.3e} dB   (tolerance {TOL_DB:.0e})")
    print(f"  Cnn10 embedding, relative : {worst_rel:.3e}     (tolerance {TOL_EMBEDDING_REL:.0e})")
    return worst_db, worst_rel


def shape_check() -> None:
    """The Studio path, which also covers int16 scaling and the resample."""
    rng = np.random.default_rng(1)
    n = int(PANNS_SAMPLE_RATE * 10)
    frames = 1 + n // HOP
    res = generate_features(1, False, rng.standard_normal(n) * 0.1, ["audio"], PANNS_SAMPLE_RATE)
    assert res["output_config"]["shape"] == {"width": frames, "height": MELS}
    assert len(res["features"]) == frames * MELS

    # A 16 kHz project must land on the same frame count after resampling, or
    # the learning block's fixed input shape silently mismatches.
    half = rng.standard_normal(16000 * 10) * 0.1
    res16 = generate_features(1, False, half, ["audio"], 16000)
    assert res16["output_config"]["shape"] == {"width": frames, "height": MELS}, \
        res16["output_config"]["shape"]

    # int16 counts must be scaled to [-1, 1), not run as raw amplitudes: a
    # 32768x amplitude error is a +90 dB offset on every bin.
    counts = (rng.standard_normal(n) * 3000).astype(np.int16).astype(np.float64)
    a = np.array(generate_features(1, False, counts, ["audio"], PANNS_SAMPLE_RATE)["features"])
    b = np.array(generate_features(1, False, counts / 32768.0, ["audio"], PANNS_SAMPLE_RATE)["features"])
    assert np.max(np.abs(a - b)) < 1e-4, float(np.max(np.abs(a - b)))
    print(f"\ngenerate_features: {frames} frames x {MELS} bins, resample and int16 scaling OK")


def main() -> int:
    synthetic_report()
    shape_check()
    worst_db, worst_rel = clip_parity()
    if worst_db > TOL_DB or worst_rel > TOL_EMBEDDING_REL:
        print("\nFAIL: front ends have diverged", file=sys.stderr)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
