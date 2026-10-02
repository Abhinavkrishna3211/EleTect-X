"""Reproduce the deployed MFE + small-CNN approach on the frozen split.

Without this there is no honest comparison to make. The 58.0% in ml/acoustic/
README.md was measured inside Edge Impulse on a *different* dataset assembly and
a file-level split that `build_index.py` shows leaks 25.4% of `elephant_call`.
Quoting a new number against that one would be comparing across two changes at
once - a new model and a new split - and crediting the model for both.

So the production recipe is rebuilt here and run on the identical frozen split
the backbone is scored on:

  * MFE front end - 40 mel filterbank energies, 256-pt FFT, 0.02 s frames at the
    0.020835 s stride the training script derives for a 10 s window
    (`frame_stride_for_window`, widened to stay under Edge Impulse's 500-frame
    feature cap).
  * `conv1d(16) -> conv1d(32) -> dense(24)`, kernel 3, dropout 0.25/0.25/0.4,
    as locked in the README's Impulse section.

This will not reproduce Edge Impulse's number exactly - different framework,
initialisation and training loop - but it puts the production recipe and any
replacement on one split, which is the comparison that means something.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

# The locked impulse resamples to 8 kHz, not 16. This is load-bearing twice over:
# a 0.02 s frame is 160 samples, which fits the 256-pt FFT, and a 10 s window at
# the 0.020835 s stride comes to 482 frames - just under Edge Impulse's 500-frame
# feature cap, which is what forced that odd stride in the first place.
SAMPLE_RATE = 8000
N_MELS = 40
N_FFT = 256
FRAME_LENGTH_S = 0.02
FRAME_STRIDE_S = 0.020835


WIN_LENGTH = int(FRAME_LENGTH_S * SAMPLE_RATE)
HOP_LENGTH = int(FRAME_STRIDE_S * SAMPLE_RATE)
if WIN_LENGTH > N_FFT:
    raise SystemExit(
        f"front-end misconfigured: win_length {WIN_LENGTH} > n_fft {N_FFT}; "
        "check SAMPLE_RATE against the impulse's input rate"
    )


def mfe(path: str, seconds: float) -> np.ndarray:
    """40-band log mel filterbank energies, matching the locked MFE block."""
    import librosa

    want = int(SAMPLE_RATE * seconds)
    y, _ = librosa.load(path, sr=SAMPLE_RATE, mono=True)
    if len(y) < want:
        y = np.pad(y, (0, want - len(y)))
    y = y[:want]
    spec = librosa.feature.melspectrogram(
        y=y,
        sr=SAMPLE_RATE,
        n_fft=N_FFT,
        hop_length=HOP_LENGTH,
        win_length=WIN_LENGTH,
        n_mels=N_MELS,
        fmin=0,
        fmax=SAMPLE_RATE // 2,
        power=2.0,
    )
    return np.log(spec + 1e-6).astype(np.float32)  # (n_mels, frames)


class SmallCNN:
    """conv1d(16) -> conv1d(32) -> dense(24) -> classes, as locked in the README."""

    def __init__(self, n_mels, n_classes, seed):
        import torch
        from torch import nn

        torch.manual_seed(seed)
        self.net = nn.Sequential(
            nn.Conv1d(n_mels, 16, 3, padding=1), nn.ReLU(), nn.MaxPool1d(2), nn.Dropout(0.25),
            nn.Conv1d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool1d(2), nn.Dropout(0.25),
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(32, 24), nn.ReLU(), nn.Dropout(0.4),
            nn.Linear(24, n_classes),
        )

    def fit(self, X, y, epochs=120, lr=1e-3, batch=32, class_weight=None):
        import torch
        from torch import nn

        opt = torch.optim.Adam(self.net.parameters(), lr=lr)
        w = torch.tensor(class_weight, dtype=torch.float32) if class_weight is not None else None
        lossf = nn.CrossEntropyLoss(weight=w)
        X = torch.tensor(X)
        y = torch.tensor(y)
        self.net.train()
        for _ in range(epochs):
            perm = torch.randperm(len(X))
            for i in range(0, len(X), batch):
                idx = perm[i : i + batch]
                opt.zero_grad()
                loss = lossf(self.net(X[idx]), y[idx])
                loss.backward()
                opt.step()
        return self

    def predict(self, X):
        import torch

        self.net.eval()
        with torch.no_grad():
            return self.net(torch.tensor(X)).argmax(1).numpy()


def main() -> int:
    from train_head import apply_split, confusion, per_class_report

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--cache", default=os.path.join("ml", "acoustic", "harness", "mfe_cache.npz"))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=120)
    args = ap.parse_args()

    with open(args.split, encoding="utf-8") as fh:
        spec = json.load(fh)
    rows = spec["records"]
    classes = sorted(spec["classes"])

    if os.path.exists(args.cache):
        d = np.load(args.cache, allow_pickle=True)
        X, label, source, fname = d["X"], d["label"], d["source"], d["fname"]
        print(f"loaded cached MFE features {X.shape}")

        # A re-freeze can bring in clips the cache predates. Extend it in place
        # rather than recomputing the whole front end over the unchanged rest.
        have = set(fname.tolist())
        new_rows = [r for r in rows if r["file"] not in have]
        if new_rows:
            print(f"extending cache with {len(new_rows)} new clip(s)...")
            add = []
            for n, r in enumerate(new_rows, 1):
                add.append(mfe(r["path"], spec["window_s"]))
                if n % 100 == 0:
                    print(f"  {n}/{len(new_rows)}", flush=True)
            X = np.concatenate([X, np.stack(add)])
            label = np.concatenate([label, [r["label"] for r in new_rows]])
            source = np.concatenate([source, [r["source"] for r in new_rows]])
            fname = np.concatenate([fname, [r["file"] for r in new_rows]])
            split = np.concatenate([d["split"], [r["split"] for r in new_rows]])
            np.savez_compressed(args.cache, X=X, label=label, split=split,
                                source=source, fname=fname)
            print(f"cached -> {args.cache}")
    else:
        print(f"computing MFE for {len(rows)} clips...")
        feats, keep = [], []
        for n, r in enumerate(rows, 1):
            try:
                feats.append(mfe(r["path"], spec["window_s"]))
                keep.append(r)
            except Exception as exc:  # noqa: BLE001
                print(f"  skip {r['file']}: {exc}")
            if n % 500 == 0:
                print(f"  {n}/{len(rows)}", flush=True)
        X = np.stack(feats)
        label = np.array([r["label"] for r in keep])
        split = np.array([r["split"] for r in keep])
        source = np.array([r["source"] for r in keep])
        fname = np.array([r["file"] for r in keep])
        np.savez_compressed(args.cache, X=X, label=label, split=split, source=source, fname=fname)
        print(f"cached -> {args.cache}")

    # The cache may predate the current freeze, so take the split from the file.
    split, X, label, source = apply_split(args.split, fname, X, label, source)

    # Per-clip standardisation. This is NOT what Edge Impulse's MFE block does:
    # that one clamps at a -52 dB noise floor and then subtracts a 101-frame
    # sliding local mean. Swapping this for the Edge Impulse transform costs
    # ~2.6 points of overall accuracy but gains macro-average, so the two are
    # not interchangeable and the difference is deliberate, not parity.
    X = (X - X.mean(axis=(1, 2), keepdims=True)) / (X.std(axis=(1, 2), keepdims=True) + 1e-6)

    cidx = {c: i for i, c in enumerate(classes)}
    y = np.array([cidx[v] for v in label])
    tr, te = split == "train", split == "test"
    counts = np.bincount(y[tr], minlength=len(classes))
    cw = (counts.sum() / (len(classes) * np.maximum(counts, 1))).astype(np.float32)

    print(f"\ntrain {tr.sum()}  test {te.sum()}  epochs={args.epochs}  seeds={args.seeds}")
    runs = []
    for seed in range(args.seeds):
        model = SmallCNN(X.shape[1], len(classes), seed).fit(
            X[tr], y[tr], epochs=args.epochs, class_weight=cw
        )
        pred = model.predict(X[te])
        yt = np.array([classes[i] for i in y[te]])
        yp = np.array([classes[i] for i in pred])
        runs.append(
            {
                "overall": float(np.mean(yp == yt)),
                "per_class": per_class_report(yt, yp, classes),
                "field": per_class_report(
                    yt[source[te] == "field_capture"], yp[source[te] == "field_capture"], classes
                ),
                "cm": confusion(yt, yp, classes).tolist(),
            }
        )
        print(f"  seed {seed}: overall {runs[-1]['overall']:.1%}")

    print(f"\n{'class':<16}{'recall mean':>13}{'min':>8}{'max':>8}{'n':>6}")
    for c in classes:
        vals = [r["per_class"][c]["recall"] for r in runs]
        print(f"{c:<16}{np.mean(vals):>12.1%}{min(vals):>8.1%}{max(vals):>8.1%}"
              f"{runs[0]['per_class'][c]['support']:>6}")
    ov = [r["overall"] for r in runs]
    print(f"{'OVERALL':<16}{np.mean(ov):>12.1%}{min(ov):>8.1%}{max(ov):>8.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
