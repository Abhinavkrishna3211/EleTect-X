"""Log-mel features in the convention the PANNs AudioSet backbones were trained with.

Why this block exists rather than the stock MFE block. The deployed classifier is
a PANNs Cnn10 backbone carrying its released AudioSet weights (see
../../ACOUSTIC_MODEL_REPORT.md). Those weights were learned on one specific
front end, implemented in torchlibrosa as `Spectrogram` followed by
`LogmelFilterBank`. Edge Impulse's MFE block is a different front end in three
ways that matter:

  * MFE sets every bin below a configurable noise floor to zero. PANNs applies
    no floor beyond `amin=1e-10`, so quiet bins keep their (large, negative)
    log values. Zeroing them moves the input distribution away from the one the
    pretrained convolutions expect, and the backbone has no opportunity to
    relearn around it - the whole point of the transfer is that it is frozen.
  * MFE normalises per window; PANNs does not, and instead folds input
    normalisation into the backbone's own `bn0` batch-norm layer.
  * MFE's default filterbank geometry is not PANNs' (64 filters, 50-14000 Hz,
    Slaney-normalised, over a power spectrum).

So this block reimplements the torchlibrosa path exactly. `parity_check.py` in
this directory asserts that against the real torchlibrosa modules; it is the
evidence for the claim, and it should be re-run whenever this file changes.

The output layout is (frames, mel_bins) flattened row-major, which is what
Edge Impulse's spectrogram viewer and the learning block both expect.
"""

from __future__ import annotations

import numpy as np

# PANNs' fixed operating point. Every released checkpoint is trained here; a
# clip arriving at any other rate is resampled rather than run as-is, because a
# rate mismatch silently rescales every mel centre frequency.
PANNS_SAMPLE_RATE = 32000

# torchlibrosa's LogmelFilterBank defaults, named so the arithmetic below can be
# read against the reference implementation rather than taken on trust.
AMIN = 1e-10
REF = 1.0

_MEL_CACHE: dict[tuple, np.ndarray] = {}


def mel_filterbank(sr: int, n_fft: int, n_mels: int, fmin: int, fmax: int) -> np.ndarray:
    """librosa's Slaney-normalised mel matrix, shape (n_mels, 1 + n_fft // 2).

    Cached because it depends only on the parameters, and rebuilding it per
    window costs more than the STFT it feeds.
    """
    key = (sr, n_fft, n_mels, fmin, fmax)
    if key not in _MEL_CACHE:
        import librosa

        _MEL_CACHE[key] = librosa.filters.mel(
            sr=sr, n_fft=n_fft, n_mels=n_mels, fmin=fmin, fmax=fmax
        ).astype(np.float32)
    return _MEL_CACHE[key]


def peak_window(y: np.ndarray, sr: int, seconds: float) -> np.ndarray:
    """`seconds` of audio centred on the loudest 100 ms.

    Only used to reproduce the training harness's `--crop peak`, which exists
    because a fixed head crop of a 10 s clip can miss a transient entirely and
    so understates what a sliding detector would see. On device the window is
    already sliding, so this is off by default.
    """
    want = int(sr * seconds)
    if len(y) <= want:
        return y
    hop = sr // 10
    energy = np.convolve(y.astype(np.float64) ** 2, np.ones(hop), mode="same")
    start = int(np.clip(int(np.argmax(energy)) - want // 2, 0, len(y) - want))
    return y[start : start + want]


def logmel(
    y: np.ndarray,
    sr: int = PANNS_SAMPLE_RATE,
    n_fft: int = 1024,
    hop_size: int = 320,
    mel_bins: int = 64,
    fmin: int = 50,
    fmax: int = 14000,
) -> np.ndarray:
    """(frames, mel_bins) float32, bit-comparable with torchlibrosa's output.

    The chain is: Hann-windowed STFT with `center=True` and reflect padding ->
    power spectrum -> mel projection -> `10 * log10(clamp(x, amin))`, minus
    `10 * log10(max(amin, ref))`, which is zero at the PANNs default ref=1.0 but
    is kept explicit so a future ref change stays correct.
    """
    import librosa

    stft = librosa.stft(
        np.ascontiguousarray(y, dtype=np.float32),
        n_fft=n_fft,
        hop_length=hop_size,
        win_length=n_fft,
        window="hann",
        center=True,
        pad_mode="reflect",
    )
    power = (np.abs(stft) ** 2).astype(np.float32)  # (1 + n_fft // 2, frames)
    mel = mel_filterbank(sr, n_fft, mel_bins, fmin, fmax) @ power  # (mel_bins, frames)

    out = 10.0 * np.log10(np.clip(mel, AMIN, None))
    out -= 10.0 * np.log10(max(AMIN, REF))
    return out.T.astype(np.float32)  # (frames, mel_bins)


def generate_features(
    implementation_version,
    draw_graphs,
    raw_data,
    axes,
    sampling_freq,
    mel_bins=64,
    n_fft=1024,
    hop_size=320,
    fmin=50,
    fmax=14000,
    peak_crop=False,
):
    """Edge Impulse processing-block entry point."""
    if implementation_version != 1:
        raise ValueError(f"unsupported implementation version {implementation_version}")
    if len(axes) != 1:
        raise ValueError(
            f"PANNs log-mel is a single-channel audio front end, got {len(axes)} axes"
        )

    y = np.asarray(raw_data, dtype=np.float32).reshape(-1)

    # Edge Impulse serves int16 PCM as raw counts for some data sources and as
    # floats for others. PANNs was trained on [-1, 1) floats, and a 32768x
    # amplitude error becomes a +90 dB offset on every mel bin, which the frozen
    # bn0 cannot absorb. Scale on evidence rather than on a project setting.
    if np.max(np.abs(y)) > 1.0:
        y = y / 32768.0

    sr = int(sampling_freq)
    if sr != PANNS_SAMPLE_RATE:
        import librosa

        y = librosa.resample(y, orig_sr=sr, target_sr=PANNS_SAMPLE_RATE)
        sr = PANNS_SAMPLE_RATE

    if peak_crop:
        y = peak_window(y, sr, len(y) / sr)

    mel = logmel(
        y,
        sr=sr,
        n_fft=int(n_fft),
        hop_size=int(hop_size),
        mel_bins=int(mel_bins),
        fmin=int(fmin),
        fmax=int(fmax),
    )

    graphs = []
    if draw_graphs:
        graphs.append(
            {
                "name": "Log-mel spectrogram",
                "image": _spectrogram_png(mel),
                "imageMimeType": "image/png",
                "type": "image",
            }
        )

    return {
        "features": mel.flatten().tolist(),
        "graphs": graphs,
        "labels": [f"mel_{i}" for i in range(mel.shape[1])],
        "output_config": {
            "type": "spectrogram",
            "shape": {"width": int(mel.shape[0]), "height": int(mel.shape[1])},
        },
    }


def _spectrogram_png(mel: np.ndarray) -> str:
    """Base64 PNG of the spectrogram for the Studio preview pane."""
    import base64
    import io

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6, 2.2), dpi=100)
    ax.imshow(mel.T, aspect="auto", origin="lower", interpolation="nearest")
    ax.set_xlabel("frame (10 ms)")
    ax.set_ylabel("mel bin")
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")
