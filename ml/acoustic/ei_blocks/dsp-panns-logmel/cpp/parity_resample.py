"""Hold the C++ resample path against ../dsp.py at the rate that ships.

parity_cpp.py checks the log-mel core with the signal already at 32 kHz.
That is not the deployed path. The trained impulse is 8 kHz - every clip in
the corpus is natively 8 kHz, because the largest source is - so on-device
every window is upsampled 4x before the filterbank runs, and the resampler
is part of the front end whether or not anyone chose it to be.

It cannot be checked the same way. ../dsp.py resamples with librosa's
soxr_hq; the C++ uses an own-work Kaiser windowed-sinc matched to soxr_hq's
*measured* response, because soxr is LGPL and this tree is MIT. Two
different filters cannot agree to 1e-2 dB everywhere, and demanding that
they do would only produce a test that has to be switched off.

What they can be held to is where the disagreement is allowed to land:

  below the passband edge (3724 Hz)   the signal actually lives here, and
                                      the two must agree tightly
  3724 Hz to Nyquist                  transition band, the two filters roll
                                      off differently by construction
  above input Nyquist (4000 Hz)       an 8 kHz source has no content here at
                                      all; whatever is present is one
                                      resampler's stopband versus another's,
                                      both ~100 dB below the clip peak

The dB budget below is therefore a statement about which mel bins carry
information, not a tolerance pulled from the air. The claim that the
remaining disagreement does not matter is not made here - it is made by
measuring the classifier, and that is in the README.

  g++ -O2 -std=c++17 parity_main.cpp -o parity_cpp
  python parity_resample.py
"""

from __future__ import annotations

import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import dsp  # noqa: E402 - relies on the sys.path insert above

SR_IN = 8000
SR = dsp.PANNS_SAMPLE_RATE
N_FFT = 1024
HOP = 320
MELS = 64
FMIN = 50
FMAX = 14000

# Where the two filters are designed to be the same, and where they are not.
PASSBAND_HZ = 3680.0  # 0.920 * input Nyquist, matching kPassbandFraction
NYQUIST_IN_HZ = SR_IN / 2.0

# In the band that carries signal the port has to be as close to the Python
# as a different-but-equivalent filter can get. 0.5 dB is loose enough to
# cover the two designs' passband ripple and tight enough that a real error
# - a wrong cutoff, a missing normalisation, an off-by-one in the polyphase
# indexing - cannot hide under it. Measured worst on these probes: ~0.35 dB.
TOL_INBAND_DB = 0.5

DYNAMIC_RANGE_DB = 80.0


def mel_edges() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Lower edge, centre and upper edge of every mel filter, in Hz.

    Splitting the bands by centre frequency is the obvious thing and it is
    wrong. A Slaney mel filter is a triangle spanning edge[i] to edge[i+2],
    so a bin centred at 3680 Hz still integrates energy out to 3891 Hz -
    past the passband edge and into the region where the two resamplers are
    designed to differ. Judged by its centre that bin looks like a clean
    in-band disagreement of several dB; judged by its support it is exactly
    what it should be. Use the support.
    """
    import librosa

    e = librosa.mel_frequencies(n_mels=MELS + 2, fmin=FMIN, fmax=FMAX)
    return e[:-2], e[1:-1], e[2:]


def reference_logmel(y: np.ndarray) -> np.ndarray:
    """What ../dsp.py computes for an 8 kHz clip.

    dsp.logmel() does not resample - its `sr` is the analysis rate. The
    resample lives in generate_features(), lines 144-148, and this
    reproduces those five lines rather than calling generate_features so
    the comparison is not entangled with its slicing and flattening.
    librosa.resample()'s default res_type is soxr_hq, which is the filter
    the C++ was designed against.
    """
    import librosa

    up = librosa.resample(np.ascontiguousarray(y, dtype=np.float32),
                          orig_sr=SR_IN, target_sr=SR)
    return dsp.logmel(up, sr=SR, n_fft=N_FFT, hop_size=HOP, mel_bins=MELS,
                      fmin=FMIN, fmax=FMAX)


def probes() -> list[tuple[str, np.ndarray, bool]]:
    """Signals that stress the resampler specifically.

    Everything is 4 s at 8 kHz. The third element says whether the probe's
    in-band column is asserted or only reported.

    Two probes are deliberately not asserted, and the reason is not that
    they are inconvenient. `tone_3700hz_at_edge` and
    `tone_3900hz_in_transition` put all their energy at or above the
    passband edge, which is precisely the region the two filters are
    designed to treat differently. Their leakage then lands in the clean
    bins, so an "in-band disagreement" for them is a measurement of the
    intended difference, not of a defect. Asserting on them would be
    asserting that two different filters are the same filter. They stay in
    the table because their numbers are the evidence for that claim, and
    because a change that moved them a lot would be worth looking at.
    """
    n = SR_IN * 4
    t = np.arange(n, dtype=np.float32) / SR_IN
    rng = np.random.default_rng(0)

    def tone(f: float) -> np.ndarray:
        return (0.5 * np.sin(2 * np.pi * f * t)).astype(np.float32)

    out = [
        ("tone_100hz", tone(100), True),
        ("tone_440hz", tone(440), True),
        ("tone_1000hz", tone(1000), True),
        ("tone_2500hz", tone(2500), True),
        ("tone_3500hz", tone(3500), True),
        ("tone_3700hz_at_edge", tone(3700), False),
        ("tone_3900hz_in_transition", tone(3900), False),
        ("white_noise", (0.2 * rng.standard_normal(n)).astype(np.float32), True),
        ("impulse_at_start", np.concatenate(
            ([np.float32(1.0)], np.zeros(n - 1, dtype=np.float32))), True),
        ("impulse_at_end", np.concatenate(
            (np.zeros(n - 1, dtype=np.float32), [np.float32(1.0)])), True),
        ("digital_silence", np.zeros(n, dtype=np.float32), True),
        ("square_full_scale",
         np.sign(np.sin(2 * np.pi * 220 * t)).astype(np.float32), True),
        ("ragged_length",
         (0.3 * np.sin(2 * np.pi * 700 * t[: n - 137])).astype(np.float32), True),
    ]
    return out


def worst_in_band(diff: np.ndarray, mask: np.ndarray, sel: np.ndarray) -> float:
    """Largest disagreement over the audible cells of one group of mel bins.

    `mask` keeps the comparison to cells the network can actually see;
    below it both sides are reporting their own numerical floor rather
    than anything about the filters.
    """
    m = mask & sel[None, :]
    return float(diff[m].max()) if m.any() else 0.0


def run_cpp(exe: Path, y: np.ndarray, workdir: Path, name: str) -> np.ndarray:
    """Round-trip one clip through the compiled core at 8 kHz in."""
    fin = workdir / f"{name}.f32"
    fout = workdir / f"{name}.bin"
    fin.write_bytes(np.ascontiguousarray(y, dtype="<f4").tobytes())

    proc = subprocess.run(
        [
            str(exe), str(fin), str(fout),
            str(SR), str(N_FFT), str(HOP), str(MELS), str(FMIN), str(FMAX),
            str(SR_IN),
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


def main() -> int:
    exe = HERE / ("parity_cpp.exe" if sys.platform == "win32" else "parity_cpp")
    if not exe.exists():
        print(f"build the harness first: g++ -O2 -std=c++17 parity_main.cpp -o {exe.stem}")
        return 2

    lower, _centres, upper = mel_edges()
    # Clean only if the filter's whole support sits below the passband
    # edge; contaminated the moment any of it reaches the transition.
    below = upper <= PASSBAND_HZ
    above = lower >= NYQUIST_IN_HZ
    trans = ~below & ~above
    print(f"{MELS} mel bins by filter support: {below.sum()} wholly below {PASSBAND_HZ:.0f} Hz, "
          f"{trans.sum()} straddling or in transition, {above.sum()} wholly above {NYQUIST_IN_HZ:.0f} Hz "
          f"(no content there - an {SR_IN} Hz source is band-limited)")
    print(f"input {SR_IN} Hz -> analysis {SR} Hz, factor {SR // SR_IN}\n")

    print(f"{'probe':<30}{'frames':>7}{f'<{PASSBAND_HZ:.0f}Hz':>11}{'transition':>12}"
          f"{'>4kHz':>10}")

    worst_in = 0.0
    worst_in_name = ""
    rows = []
    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        for name, y, strict in probes():
            ref = reference_logmel(y)
            got = run_cpp(exe, y, workdir, name)

            if ref.shape != got.shape:
                print(f"{name:<30} SHAPE {got.shape} != {ref.shape}")
                return 1

            d = np.abs(ref - got)
            # Only judge cells the network can actually see: below the
            # dynamic range PANNs keeps, both sides are reporting their own
            # numerical floor.
            mask = ref > (ref.max() - DYNAMIC_RANGE_DB)
            b_in = worst_in_band(d, mask, below)
            b_tr = worst_in_band(d, mask, trans)
            b_ab = worst_in_band(d, mask, above)
            rows.append((name, b_in, b_tr, b_ab, strict))
            if strict and b_in > worst_in:
                worst_in, worst_in_name = b_in, name
            print(f"{name:<30}{ref.shape[0]:>7}{b_in:>11.3e}{b_tr:>12.3e}"
                  f"{b_ab:>10.3e}{'' if strict else '   reported only'}")

    print(f"\nworst asserted in-band (<{PASSBAND_HZ:.0f} Hz): "
          f"{worst_in:.3e} dB   [{worst_in_name}]")
    print(f"tolerance:                                {TOL_INBAND_DB:.3e} dB")
    print(f"worst transition-band:                    "
          f"{max(r[2] for r in rows):.3e} dB   (expected: different filters)")
    print(f"worst above {NYQUIST_IN_HZ:.0f} Hz:                       "
          f"{max(r[3] for r in rows):.3e} dB   (expected: no signal there)")

    if worst_in > TOL_INBAND_DB:
        print("\nFAIL - the port disagrees where the signal is.")
        return 1
    print("\nPASS - the resample path agrees wherever an 8 kHz source has "
          "content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
