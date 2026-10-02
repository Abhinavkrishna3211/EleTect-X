"""Three-way numerical parity: the C++ port vs dsp.py vs torchlibrosa.

`../parity_check.py` proves dsp.py reproduces the front end PANNs was
trained on. This proves the C++ that actually ships reproduces dsp.py -
and, transitively, torchlibrosa. Without it the port is only inspected,
and an inspected DSP port is how a model quietly loses accuracy between
Studio and the device with nothing in the logs to say so.

Run from this directory:

    g++ -O2 -std=c++17 parity_main.cpp -o parity_cpp
    python parity_cpp.py

Two criteria, because the two legs are not the same kind of claim.

Against dsp.py the bar is absolute and unmasked: every mel bin of every
probe within TOL_DB. dsp.py is what Studio ran while the model trained,
so any disagreement here is the port changing what the classifier sees.

Against torchlibrosa the bar is relative: inside the top DYNAMIC_RANGE_DB
the port must be no further from it than dsp.py already is. It cannot be
absolute, because torchlibrosa is itself the least accurate of the three.
Measured against a float64 reference on these probes, librosa lands
within 1e-5 dB, this port within 2e-5 dB, and torchlibrosa's own float32
conv1d STFT drifts as far as 6e-1 dB on a pure tone. Demanding the port
match torchlibrosa exactly would be demanding it reproduce torchlibrosa's
rounding error. What it must not do is add error of its own, which is
precisely what the relative form asserts.

Exit code 0 means both hold.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import dsp  # noqa: E402 - relies on the sys.path insert above

SR = dsp.PANNS_SAMPLE_RATE
N_FFT = 1024
HOP = 320
MELS = 64
FMIN = 50
FMAX = 14000

# The same bar ../parity_check.py holds dsp.py to against torchlibrosa.
# Holding the port to its reference no less tightly than the reference is
# held to the ground truth keeps the chain honest end to end.
TOL_DB = 1e-2

# PANNs' own normalisation discards everything more than 80 dB under the
# loudest bin, so agreement outside that band cannot affect a prediction.
# ../parity_check.py masks to this band for the same reason when it holds
# dsp.py against torchlibrosa.
DYNAMIC_RANGE_DB = 80.0


def probes() -> list[tuple[str, np.ndarray]]:
    """Signals chosen to break a log-mel port in each way one can break.

    Every entry targets a specific failure: window convention, filterbank
    edges, padding mode, the amin clamp, the int16 rescale.
    """
    rng = np.random.default_rng(20260929)
    n = SR * 3  # the capture length services/acoustic_watch.py uses
    t = np.arange(n, dtype=np.float32) / SR
    out: list[tuple[str, np.ndarray]] = []

    # Pure tones at filterbank landmarks. A tone sits in one or two mel
    # bins, so a filterbank built with the wrong mel convention (HTK
    # instead of Slaney) or the wrong normalisation moves energy to a
    # visibly different bin rather than perturbing everything slightly.
    for hz in (55, 440, 1000, 4000, 13500):
        out.append((f"tone_{hz}hz", (0.4 * np.sin(2 * np.pi * hz * t)).astype(np.float32)))

    # Just below fmin and just above fmax: the filters must roll off to
    # nothing, which is where an off-by-one in the band edges shows.
    out.append(("tone_below_fmin_30hz", (0.4 * np.sin(2 * np.pi * 30 * t)).astype(np.float32)))
    out.append(("tone_above_fmax_15500hz", (0.4 * np.sin(2 * np.pi * 15500 * t)).astype(np.float32)))

    # Broadband: exercises all 513 rfft bins and all 64 filters at once.
    out.append(("white_noise", (0.2 * rng.standard_normal(n)).astype(np.float32)))

    # Linear chirp across the whole band: catches a filterbank whose
    # spacing is right at the ends and wrong in the middle.
    sweep = 50 + (15000 - 50) * t / t[-1] / 2
    out.append(("chirp_50_15000", (0.4 * np.sin(2 * np.pi * sweep * t)).astype(np.float32)))

    # Impulse at the very first sample: the only probe that makes the
    # reflect padding on the leading edge observable at all.
    imp = np.zeros(n, dtype=np.float32)
    imp[0] = 0.9
    out.append(("impulse_at_start", imp))

    # ...and at the last, for the trailing edge.
    imp2 = np.zeros(n, dtype=np.float32)
    imp2[-1] = 0.9
    out.append(("impulse_at_end", imp2))

    # Digital silence: every bin lands on the amin clamp, so this asserts
    # both sides clamp at the same place and produce exactly -100 dB.
    out.append(("digital_silence", np.zeros(n, dtype=np.float32)))

    # Near-silence at the clamp boundary - the regime a flat BY-M1 cell
    # actually produces, and the one place float32 accumulation order
    # could plausibly move a value across the clamp.
    out.append(("near_silence", (1e-6 * rng.standard_normal(n)).astype(np.float32)))

    # Full-scale square wave: heavy harmonics all the way to Nyquist,
    # plus values at the edge of the [-1, 1) range.
    out.append(("square_full_scale", (np.sign(np.sin(2 * np.pi * 220 * t)) * 0.99).astype(np.float32)))

    # Two tones an octave apart with a DC offset, mimicking a real capture
    # through an electret with a bias the codec did not fully reject.
    two_tone = 0.3 * np.sin(2 * np.pi * 600 * t) + 0.2 * np.sin(2 * np.pi * 1200 * t) + 0.05
    out.append(("two_tone_with_dc", two_tone.astype(np.float32)))

    # A non-multiple-of-hop length, so frames = 1 + n // hop is checked
    # somewhere other than an exact boundary.
    ragged = 0.3 * np.sin(2 * np.pi * 900 * t[: n - 137])
    out.append(("ragged_length", ragged.astype(np.float32)))

    return out


def run_cpp(exe: Path, y: np.ndarray, workdir: Path, name: str) -> np.ndarray:
    """Round-trip one clip through the compiled core."""
    fin = workdir / f"{name}.f32"
    fout = workdir / f"{name}.bin"
    fin.write_bytes(np.ascontiguousarray(y, dtype="<f4").tobytes())

    proc = subprocess.run(
        [
            str(exe), str(fin), str(fout),
            str(SR), str(N_FFT), str(HOP), str(MELS), str(FMIN), str(FMAX),
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"{name}: harness exited {proc.returncode}: {detail}")

    raw = fout.read_bytes()
    frames, mels = struct.unpack("<ii", raw[:8])
    data = np.frombuffer(raw[8:], dtype="<f4", count=frames * mels)
    return data.reshape(frames, mels).copy()


def torchlibrosa_logmel(y: np.ndarray) -> np.ndarray:
    """The actual modules PANNs instantiates, for the third leg of the check."""
    import torch
    from torchlibrosa.stft import LogmelFilterBank, Spectrogram

    spec = Spectrogram(
        n_fft=N_FFT, hop_length=HOP, win_length=N_FFT, window="hann",
        center=True, pad_mode="reflect", freeze_parameters=True,
    )
    mel = LogmelFilterBank(
        sr=SR, n_fft=N_FFT, n_mels=MELS, fmin=FMIN, fmax=FMAX,
        ref=1.0, amin=1e-10, top_db=None, freeze_parameters=True,
    )
    batch = torch.from_numpy(np.ascontiguousarray(y, dtype=np.float32)[None, :])
    with torch.no_grad():
        return mel(spec(batch)).numpy()[0, 0]


def compare(label: str, a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    """Max absolute dB difference, overall and within the audible 80 dB."""
    if a.shape != b.shape:
        raise AssertionError(f"{label}: shape {a.shape} vs {b.shape}")
    diff = np.abs(a.astype(np.float64) - b.astype(np.float64))
    mask = a >= a.max() - DYNAMIC_RANGE_DB
    in_band = float(diff[mask].max()) if mask.any() else 0.0
    return float(diff.max()), in_band


def main() -> int:
    """Run every probe through both references and report the worst gap."""
    exe = HERE / "parity_cpp.exe"
    if not exe.exists():
        exe = HERE / "parity_cpp"
    if not exe.exists():
        print("build the harness first:  g++ -O2 -std=c++17 parity_main.cpp -o parity_cpp")
        return 2

    workdir = Path(tempfile.mkdtemp(prefix="panns_parity_"))
    failures: list[str] = []
    worst_py = 0.0
    worst_tl = 0.0

    try:
        header = (
            f"{'probe':<26} {'frames':>7} {'cpp-vs-py':>11} "
            f"{'cpp-vs-tl':>11} {'py-vs-tl':>11}   (dB, tl cols in-band)"
        )
        print(header)
        print("-" * len(header))
        for name, y in probes():
            got = run_cpp(exe, y, workdir, name)
            ref_py = dsp.logmel(
                y, sr=SR, n_fft=N_FFT, hop_size=HOP,
                mel_bins=MELS, fmin=FMIN, fmax=FMAX,
            )
            ref_tl = torchlibrosa_logmel(y)

            d_py, _ = compare(name, ref_py, got)
            _, band_cpp_tl = compare(name, ref_tl, got)
            _, band_py_tl = compare(name, ref_tl, ref_py)
            worst_py = max(worst_py, d_py)
            worst_tl = max(worst_tl, band_cpp_tl)

            bad = []
            if d_py > TOL_DB:
                bad.append(f"{name}: {d_py:.6f} dB vs dsp.py (tol {TOL_DB})")
            # The port may inherit torchlibrosa's error; it may not add to
            # it. Anything else would be asserting that this C++ rounds the
            # same way a float32 PyTorch conv1d does.
            if band_cpp_tl > band_py_tl + TOL_DB:
                bad.append(
                    f"{name}: {band_cpp_tl:.6f} dB vs torchlibrosa in-band, "
                    f"worse than dsp.py's own {band_py_tl:.6f} dB by more than {TOL_DB}"
                )
            failures.extend(bad)
            print(
                f"{name:<26} {got.shape[0]:>7} {d_py:>11.3e} "
                f"{band_cpp_tl:>11.3e} {band_py_tl:>11.3e}"
                f"{'   <-- FAIL' if bad else ''}"
            )

        # The int16 rescale is a separate contract: the same waveform in
        # raw counts must give the same spectrogram as in [-1, 1). This is
        # the one place the C++ is allowed to differ from dsp.logmel(),
        # because the rescale lives in generate_features() on that side.
        print()
        tone_t = np.arange(SR, dtype=np.float32) / SR
        tone = (0.4 * np.sin(2 * np.pi * 1000 * tone_t)).astype(np.float32)
        as_float = run_cpp(exe, tone, workdir, "scale_float")
        as_counts = run_cpp(exe, (tone * 32768.0).astype(np.float32), workdir, "scale_counts")
        d_scale = float(np.abs(as_float.astype(np.float64) - as_counts.astype(np.float64)).max())
        ok_scale = d_scale <= TOL_DB
        verdict = "OK" if ok_scale else "FAIL"
        print(f"int16-counts rescale agrees with float input: {d_scale:.3e} dB  {verdict}")
        if not ok_scale:
            failures.append(f"int16 rescale: {d_scale:.6f} dB")

        # Frame count must match librosa's 1 + n // hop, or the learning
        # block is fed a different number of time steps than it was
        # trained on and the flatten silently misaligns.
        n = SR * 3
        expected = 1 + n // HOP
        actual = run_cpp(exe, np.zeros(n, dtype=np.float32), workdir, "frames").shape[0]
        ok_frames = actual == expected
        verdict = "OK" if ok_frames else "FAIL"
        print(f"frame count for {n} samples: {actual} (expected {expected})  {verdict}")
        if not ok_frames:
            failures.append(f"frame count {actual} != {expected}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print()
    print(f"worst vs dsp.py, all cells:            {worst_py:.3e} dB")
    print(f"worst vs torchlibrosa, top {DYNAMIC_RANGE_DB:.0f} dB:       {worst_tl:.3e} dB")
    print(f"tolerance:                             {TOL_DB:.3e} dB")

    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nPASS - the C++ front end reproduces the trained one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
