"""Train a classifier head on frozen backbone embeddings and report honestly.

Reporting rules, carried over from ml/acoustic/README.md's existing discipline:

  * Per-class recall is always reported per class, never averaged into one
    headline figure.
  * Every run is repeated across seeds and the spread is printed, because
    caveat 13 in that README measures 15-20 point per-class swings between runs
    that differed only in training randomness. A single run is not a
    measurement.
  * The field slice (clips captured on this project's own hardware) is scored
    separately from the public-corpus slice. They are different claims and the
    field number is the one that predicts deployment behaviour.
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np


def per_class_report(y_true, y_pred, classes):
    out = {}
    for c in classes:
        tp = int(np.sum((y_true == c) & (y_pred == c)))
        fn = int(np.sum((y_true == c) & (y_pred != c)))
        fp = int(np.sum((y_true != c) & (y_pred == c)))
        rec = tp / (tp + fn) if tp + fn else 0.0
        prec = tp / (tp + fp) if tp + fp else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        out[c] = {"recall": rec, "precision": prec, "f1": f1, "support": tp + fn, "tp": tp}
    return out


def bootstrap_recall(y_true, y_pred, classes, n=2000, seed=0):
    """Percentile CI for per-class recall, resampling test recordings.

    Each test recording contributes exactly one file (see freeze_split.py), so
    resampling rows resamples recordings - the unit the split was drawn on.
    With n=62 for elephant_call, this interval is wide, and that width is the
    point: it is what a single held-out number does not tell you.
    """
    rng = np.random.default_rng(seed)
    out = {c: [] for c in classes}
    idx = np.arange(len(y_true))
    for _ in range(n):
        take = rng.choice(idx, len(idx), replace=True)
        yt, yp = y_true[take], y_pred[take]
        for c in classes:
            m = yt == c
            out[c].append(float(np.mean(yp[m] == c)) if m.any() else np.nan)
    return {
        c: (
            float(np.nanpercentile(v, 2.5)),
            float(np.nanpercentile(v, 97.5)),
        )
        for c, v in out.items()
    }


def confusion(y_true, y_pred, classes):
    m = np.zeros((len(classes), len(classes)), dtype=int)
    idx = {c: i for i, c in enumerate(classes)}
    for t, p in zip(y_true, y_pred, strict=True):
        m[idx[t], idx[p]] += 1
    return m


def fit_once(Xtr, ytr, Xte, kind, seed, balanced):
    from sklearn.linear_model import LogisticRegression
    from sklearn.neural_network import MLPClassifier
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(Xtr)
    Xtr, Xte = scaler.transform(Xtr), scaler.transform(Xte)
    cw = "balanced" if balanced else None

    # MLPClassifier's early-stopping scorer runs np.isnan over its own
    # predictions, which raises on string class labels. Fit on integer codes and
    # map back afterwards so the caller still sees label strings.
    codes, ytr_enc = np.unique(ytr, return_inverse=True)

    if kind == "logreg":
        clf = LogisticRegression(max_iter=3000, C=1.0, class_weight=cw, random_state=seed)
    elif kind == "mlp":
        # Sample weights are not supported by MLPClassifier, so imbalance is
        # handled by resampling the training set instead - see `balance_idx`.
        clf = MLPClassifier(
            hidden_layer_sizes=(512, 256),
            alpha=1e-3,
            batch_size=128,
            learning_rate_init=8e-4,
            max_iter=400,
            early_stopping=True,
            n_iter_no_change=25,
            validation_fraction=0.12,
            random_state=seed,
        )
    else:
        raise ValueError(kind)
    clf.fit(Xtr, ytr_enc)
    return codes[clf.predict(Xte)], clf.predict_proba(Xte), codes


def apply_split(split_path, fname, *arrays):
    """Re-key a feature cache against the frozen split file.

    Caches store the split label each row had when the features were extracted,
    which silently goes stale the moment the split is re-frozen - and a stale
    test set is the one bug this harness exists to avoid. So the frozen file is
    treated as the only authority: rows are matched by filename, rows no longer
    in the split (deduplicated recordings, corpora excluded from this run) are
    dropped, and a split that references a file the cache lacks is a hard error
    rather than a quietly smaller test set.
    """
    with open(split_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    want = {r["file"]: r["split"] for r in spec["records"]}
    pos = {f: i for i, f in enumerate(fname)}
    missing = [f for f in want if f not in pos]
    if missing:
        raise SystemExit(
            f"{len(missing)} file(s) in {split_path} are absent from the cache, "
            f"e.g. {missing[:3]} - re-extract features"
        )
    keep = np.array([pos[f] for f in want])
    split = np.array([want[f] for f in want])
    dropped = len(fname) - len(keep)
    if dropped:
        print(f"split re-map: {len(keep)} rows kept, {dropped} stale row(s) dropped")
    return (split, *(a[keep] for a in arrays))


def balance_idx(y, seed):
    """Oversample minority classes to the majority count (for MLP)."""
    rng = np.random.default_rng(seed)
    classes, counts = np.unique(y, return_counts=True)
    target = counts.max()
    idx = []
    for c in classes:
        where = np.flatnonzero(y == c)
        idx.append(where)
        if len(where) < target:
            idx.append(rng.choice(where, target - len(where), replace=True))
    return np.concatenate(idx)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emb", default=os.path.join("ml", "acoustic", "harness", "embeddings_cnn14.npz"))
    ap.add_argument("--head", default="mlp", choices=("logreg", "mlp"))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--balanced", action="store_true", help="class-weight / oversample to fight imbalance")
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"),
                    help="frozen split; authoritative over the split baked into --emb")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    d = np.load(args.emb, allow_pickle=True)
    split, X, label, source = apply_split(
        args.split, d["fname"], d["X"], d["label"], d["source"]
    )
    classes = sorted(set(label.tolist()))

    tr, te = split == "train", split == "test"
    Xtr, ytr = X[tr], label[tr]
    Xte, yte = X[te], label[te]
    src_te = source[te]
    print(f"embeddings {X.shape}  train {tr.sum()}  test {te.sum()}  head={args.head}"
          f"  balanced={args.balanced}  seeds={args.seeds}\n")

    runs = []
    for seed in range(args.seeds):
        if args.head == "mlp" and args.balanced:
            sel = balance_idx(ytr, seed)
            xt, yt = Xtr[sel], ytr[sel]
        else:
            xt, yt = Xtr, ytr
        pred, _, _ = fit_once(xt, yt, Xte, args.head, seed, args.balanced and args.head == "logreg")
        runs.append(
            {
                "seed": seed,
                "overall": float(np.mean(pred == yte)),
                "per_class": per_class_report(yte, pred, classes),
                "field": per_class_report(
                    yte[src_te == "field_capture"], pred[src_te == "field_capture"], classes
                ),
                "public": per_class_report(
                    yte[src_te != "field_capture"], pred[src_te != "field_capture"], classes
                ),
                "cm": confusion(yte, pred, classes).tolist(),
                "pred": pred.tolist(),
            }
        )
        print(f"  seed {seed}: overall {runs[-1]['overall']:.1%}")

    def spread(getter):
        vals = [getter(r) for r in runs]
        return float(np.mean(vals)), float(np.min(vals)), float(np.max(vals))

    print(f"\n{'class':<16}{'recall mean':>13}{'min':>8}{'max':>8}{'prec':>8}{'F1':>7}{'n':>6}")
    for c in classes:
        rm, rlo, rhi = spread(lambda r, c=c: r["per_class"][c]["recall"])
        pm, _, _ = spread(lambda r, c=c: r["per_class"][c]["precision"])
        fm, _, _ = spread(lambda r, c=c: r["per_class"][c]["f1"])
        n = runs[0]["per_class"][c]["support"]
        print(f"{c:<16}{rm:>12.1%}{rlo:>8.1%}{rhi:>8.1%}{pm:>8.1%}{fm:>7.2f}{n:>6}")
    om, olo, ohi = spread(lambda r: r["overall"])
    print(f"{'OVERALL':<16}{om:>12.1%}{olo:>8.1%}{ohi:>8.1%}")

    ci = bootstrap_recall(yte, np.asarray(runs[0]["pred"]), classes)
    print()
    print("95% CI on per-class recall (2000 bootstrap resamples of the test set)")
    for c in classes:
        lo, hi = ci[c]
        print(f"  {c:<16}[{lo:>6.1%}, {hi:>6.1%}]   n={runs[0]['per_class'][c]['support']}")

    for slice_name in ("public", "field"):
        if not any(runs[0][slice_name][c]["support"] for c in classes):
            continue
        print(f"\n-- {slice_name} slice --")
        for c in classes:
            n = runs[0][slice_name][c]["support"]
            if not n:
                continue
            rm, rlo, rhi = spread(lambda r, c=c, s=slice_name: r[s][c]["recall"])
            print(f"  {c:<16}{rm:>8.1%}  (min {rlo:.1%} max {rhi:.1%})  n={n}")

    cm = np.mean([r["cm"] for r in runs], axis=0)
    print(f"\nconfusion (rows=true, mean over seeds)\n{'':<16}" + "".join(f"{c[:9]:>11}" for c in classes))
    for i, c in enumerate(classes):
        row = cm[i]
        print(f"{c:<16}" + "".join(f"{v / max(row.sum(), 1):>10.1%} " for v in row))

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump({"emb": args.emb, "head": args.head, "runs": runs}, fh, indent=1)
        print(f"\nwrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
