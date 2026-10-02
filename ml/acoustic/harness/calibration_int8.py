"""Does int8 preserve calibrated scores, not just argmax? ADR 0026 turns on this.

ADR 0026 ships the acoustic classifier as float32, and its strongest argument is
not accuracy but calibration: section 7.2 sets the operating point with per-class
probability thresholds rather than argmax, so a quantisation that keeps the
argmax but flattens or sharpens the scores would silently invalidate every
threshold while looking harmless in a confusion matrix.

That ADR was decided against the earlier 92 KB MFE model on project 1109511,
where quantising the whole graph cost ~14 points and moved validation loss from
0.557 to 3.279. The model has since changed to a 21.4 MB PANNs Cnn10, and the
quantisation recipe has changed with it - `export_panns.py` restricts int8 to
Conv ops, per-channel and 7-bit, deliberately leaving bn0, the head's Gemm and
the Softmax in float precisely because those carry the calibrated scores. Equal
overall accuracy between the two is already on record. Equal *calibration* is
not, and that is the claim the ADR needs.

This script scores both graphs over the frozen test split, keeps the full
probability vector for every clip, and reports the things a confusion matrix
hides: how far the scores move, whether the accuracy-vs-threshold curves lie on
top of each other, and how many clips cross a threshold in each direction.

Run from this directory:
    python calibration_int8.py
    python calibration_int8.py --limit 60      # quick pass
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

import numpy as np
import onnxruntime as ort

HERE = os.path.dirname(os.path.abspath(__file__))
BLOCK = os.path.join(HERE, "..", "ei_blocks", "dsp-panns-logmel")
sys.path.insert(0, BLOCK)

from dsp import logmel

from embed import load_clip

FP32 = "cnn10_10s_fp32.onnx"
INT8 = "cnn10_10s_int8_conv_rr.onnx"
WINDOW, CROP = 10.0, "head"
THRESHOLDS = (0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 0.9)


def test_rows(split_path: str, limit: int) -> list[dict]:
    with open(split_path, encoding="utf-8") as fh:
        rows = [r for r in json.load(fh)["records"] if r["split"] == "test"]
    if limit:
        # Stratified, so a short pass is not all one class.
        by: dict[str, list] = {}
        for r in rows:
            by.setdefault(r["label"], []).append(r)
        per = max(1, limit // len(by))
        rows = [r for rs in by.values() for r in rs[:per]]
    return rows


def score_all(graph: str, rows: list[dict], mels: list[np.ndarray]) -> np.ndarray:
    """Full probability vectors, one row per clip.

    The mel features are computed once and shared between the two graphs. Both
    consume the identical front end - the quantisation is in the network, not the
    DSP - so recomputing them per graph would only add a second source of
    difference to a measurement whose whole point is to isolate the first.
    """
    sess = ort.InferenceSession(os.path.join(HERE, graph),
                                providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    out = np.zeros((len(rows), 4), dtype=np.float64)
    for i, mel in enumerate(mels):
        out[i] = sess.run(None, {name: mel})[0][0]
        if (i + 1) % 50 == 0:
            print(f"    {graph}: {i + 1}/{len(rows)}", flush=True)
    return out


def acc_curve(p: np.ndarray, truth: np.ndarray) -> dict[float, float]:
    """Accuracy with below-threshold windows counted wrong, as Edge Impulse does."""
    pred, top = p.argmax(1), p.max(1)
    return {t: float(((pred == truth) & (top >= t)).mean()) for t in THRESHOLDS}


def ece(p: np.ndarray, truth: np.ndarray, bins: int = 10) -> float:
    """Expected calibration error on the top-1 score."""
    pred, conf = p.argmax(1), p.max(1)
    hit = (pred == truth).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    e = 0.0
    for lo, hi in itertools.pairwise(edges):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            e += m.mean() * abs(hit[m].mean() - conf[m].mean())
    return float(e)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default=os.path.join(HERE, "split.json"))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=os.path.join(HERE, "calibration_int8.json"))
    args = ap.parse_args()

    rows = test_rows(args.split, args.limit)
    labels = sorted({r["label"] for r in rows})
    truth = np.array([labels.index(r["label"]) for r in rows])
    print(f"clips: {len(rows)}   labels: {labels}")

    print("  computing mel features once, shared by both graphs ...", flush=True)
    mels = []
    for n, r in enumerate(rows):
        mels.append(logmel(load_clip(r["path"], WINDOW, CROP))[None, None].astype(np.float32))
        if (n + 1) % 50 == 0:
            print(f"    mel {n + 1}/{len(rows)}", flush=True)

    p32 = score_all(FP32, rows, mels)
    p8 = score_all(INT8, rows, mels)

    a32, a8 = acc_curve(p32, truth), acc_curve(p8, truth)
    agree = float((p32.argmax(1) == p8.argmax(1)).mean())
    dtop = np.abs(p32.max(1) - p8.max(1))
    dall = np.abs(p32 - p8)

    print(f"\nargmax agreement fp32 vs int8: {agree:.4%} "
          f"({int(agree * len(rows))}/{len(rows)} clips)")
    print(f"top-1 score shift: mean {dtop.mean():.5f}  p95 {np.percentile(dtop, 95):.5f}  "
          f"max {dtop.max():.5f}")
    print(f"all-class score shift: mean {dall.mean():.5f}  max {dall.max():.5f}")
    print(f"mean top-1 confidence: fp32 {p32.max(1).mean():.4f}  int8 {p8.max(1).mean():.4f}")
    print(f"ECE (10 bins):         fp32 {ece(p32, truth):.4f}  int8 {ece(p8, truth):.4f}")

    print(f"\n{'threshold':>10} {'fp32':>9} {'int8':>9} {'delta':>9}"
          "   (below-threshold counted wrong)")
    for t in THRESHOLDS:
        print(f"{t:>10.2f} {a32[t]:>8.2%} {a8[t]:>8.2%} {a8[t] - a32[t]:>+8.2%}")

    # The operational question behind the ADR: at the deployed gate, how many
    # clips does quantisation push across it, and which way?
    g = 0.6
    c32, c8 = p32.max(1) >= g, p8.max(1) >= g
    print(f"\nat the {g} gate: fp32 confident on {c32.sum()}, int8 on {c8.sum()}; "
          f"{int((~c32 & c8).sum())} gained, {int((c32 & ~c8).sum())} lost")

    payload = {
        "fp32": FP32, "int8": INT8, "n": len(rows), "labels": labels,
        "argmax_agreement": agree,
        "top1_shift": {"mean": float(dtop.mean()),
                       "p95": float(np.percentile(dtop, 95)),
                       "max": float(dtop.max())},
        "all_class_shift": {"mean": float(dall.mean()), "max": float(dall.max())},
        "mean_top1_confidence": {"fp32": float(p32.max(1).mean()),
                                 "int8": float(p8.max(1).mean())},
        "ece": {"fp32": ece(p32, truth), "int8": ece(p8, truth)},
        "accuracy_vs_threshold": {f"{t:.2f}": {"fp32": a32[t], "int8": a8[t]}
                                  for t in THRESHOLDS},
        "gate_0.6": {"fp32_confident": int(c32.sum()), "int8_confident": int(c8.sum()),
                     "gained": int((~c32 & c8).sum()), "lost": int((c32 & ~c8).sum())},
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
