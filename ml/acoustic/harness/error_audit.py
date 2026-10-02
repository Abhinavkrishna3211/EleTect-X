"""Name the false positives, then find an operating point that removes them.

Recall alone cannot decide this deployment. A chainsaw alert sends a forest
officer to a location; at 69% precision roughly one in three of those trips is
to nothing, and the cost of that lands on the people the system is asking for
trust. So this script answers two questions the summary tables cannot:

  1. *Which* recordings drive the false positives - label noise the dataset
     should fix, or genuinely confusable audio that needs hard negatives.
  2. What precision is reachable by moving the decision threshold, given recall
     must stay at or above the 85% bar.

argmax is only one point on a curve. Because the head emits calibrated
probabilities, each class gets its own threshold: predict the class when its
probability clears that threshold, and fall back to argmax otherwise.
"""

from __future__ import annotations

import argparse
from collections import Counter

import numpy as np

from train_head import apply_split, balance_idx, fit_once


def sweep(proba, yte, classes, target, floor=0.85, lo=0.05, hi=0.96):
    """Highest-precision threshold for `target` that keeps recall >= floor."""
    col = classes.index(target)
    p = proba[:, col]
    truth = yte == target
    argmax_pred = np.array(classes)[proba.argmax(1)]

    rows = []
    for t in np.round(np.arange(lo, hi, 0.01), 2):
        # Above the threshold the class fires; below it, argmax still decides,
        # so raising `t` can only remove predictions this class would have won.
        pred = np.where(p >= t, target, argmax_pred)
        pred = np.where((pred == target) & (p < t), argmax_pred, pred)
        tp = int(((pred == target) & truth).sum())
        fp = int(((pred == target) & ~truth).sum())
        fn = int(((pred != target) & truth).sum())
        rec = tp / max(tp + fn, 1)
        prec = tp / max(tp + fp, 1)
        rows.append((t, rec, prec, tp, fp))
    ok = [r for r in rows if r[1] >= floor]
    return rows, (max(ok, key=lambda r: r[2]) if ok else None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emb", default="embeddings_cnn14.npz")
    ap.add_argument("--split", default="split.json")
    ap.add_argument("--target", default="chainsaw")
    ap.add_argument("--floor", type=float, default=0.85)
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--lo", type=float, default=0.05, help="lowest threshold to sweep")
    args = ap.parse_args()

    d = np.load(args.emb, allow_pickle=True)
    split, X, label, source, fname = apply_split(
        args.split, d["fname"], d["X"], d["label"], d["source"], d["fname"]
    )
    classes = sorted(set(label.tolist()))
    tr, te = split == "train", split == "test"

    # Average probabilities over seeds: a single seed's false positives are
    # partly its own noise, and the audit should name the persistent ones.
    acc = None
    for seed in range(args.seeds):
        sel = balance_idx(label[tr], seed)
        _, proba, codes = fit_once(X[tr][sel], label[tr][sel], X[te], "mlp", seed, False)
        order = [list(codes).index(c) for c in classes]
        acc = proba[:, order] if acc is None else acc + proba[:, order]
    proba = acc / args.seeds

    yte, fte, ste = label[te], fname[te], source[te]
    pred = np.array(classes)[proba.argmax(1)]

    fp = np.flatnonzero((pred == args.target) & (yte != args.target))
    print(f"\n{len(fp)} false {args.target} at argmax "
          f"(precision {int((pred == args.target).sum()) and ((pred == args.target) & (yte == args.target)).sum() / (pred == args.target).sum():.1%})")
    print(f"true label mix: {dict(Counter(yte[fp].tolist()))}")
    print(f"source mix:     {dict(Counter(ste[fp].tolist()))}\n")

    conf = proba[fp, classes.index(args.target)]
    for i in np.argsort(-conf)[:25]:
        print(f"  {conf[i]:.2f}  {yte[fp][i]:<14}{ste[fp][i]:<16}{fte[fp][i][:64]}")

    rows, best = sweep(proba, yte, classes, args.target, args.floor, args.lo)
    print(f"\nthreshold sweep for {args.target} (recall floor {args.floor:.0%})")
    print(f"{'thr':>6}{'recall':>9}{'prec':>9}{'tp':>5}{'fp':>5}")
    for t, rec, prec, tp, fpn in rows:
        if round(t * 100) % 5 == 0:
            print(f"{t:>6.2f}{rec:>9.1%}{prec:>9.1%}{tp:>5}{fpn:>5}")
    if best:
        t, rec, prec, tp, fpn = best
        print(f"\nbest threshold {t:.2f}: recall {rec:.1%}  precision {prec:.1%}  "
              f"({tp} true, {fpn} false)")
    else:
        print(f"\nno threshold reaches {args.floor:.0%} recall")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
