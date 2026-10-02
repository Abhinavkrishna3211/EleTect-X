"""Score and time an exported PANNs graph, on the host or on the target.

Two jobs, deliberately in one file so the number measured on a workstation and
the number measured on the QRB2210 come from identical code.

  --build-mels   Host only. Computes the log-mel input for the frozen test set
                 and caches it, so the board never needs torch, librosa or the
                 audio corpus - only numpy, onnxruntime and this cache.

  (default)      Runs a graph over that cache: per-class recall and precision
                 against the frozen labels, plus wall-clock latency per clip at
                 a given thread count.

Accuracy here is the honest counterpart to ADR 0026's complaint about Edge
Impulse: `POST /jobs/classify` ignores `selectedModelType` and always scores
float32, so Studio cannot tell you what the quantized model you are about to
ship actually does. This runs the exact file that would be deployed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def build_mels(split_path: str, arch: str, window: float, out: str, limit: int,
               crop: str = "head") -> int:
    """Cache the log-mel input for every test clip in the frozen split."""
    from embed import load_clip
    from export_panns import build_backbone, logmel

    with open(split_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    rows = [r for r in spec["records"] if r["split"] == "test"]
    if limit:
        rows = rows[:limit]
    backbone = build_backbone(arch)
    print(f"{len(rows)} test clips, arch={arch}, window={window}s", flush=True)

    mels, labels, files = [], [], []
    t0 = time.time()
    for i, r in enumerate(rows):
        wav = load_clip(r["path"], window, crop)[None, :]
        # float16 halves a cache that has to be copied to the board; the input is
        # a log-magnitude in roughly [-100, 30], so fp16 resolution is far finer
        # than the int8 quantizer's own step.
        mels.append(logmel(backbone, wav).numpy()[0].astype(np.float16))
        labels.append(r["label"])
        files.append(r["file"])
        if (i + 1) % 100 == 0:
            rate = (i + 1) / (time.time() - t0)
            print(f"  {i + 1}/{len(rows)}  {rate:.1f} clips/s", flush=True)

    np.savez_compressed(out, mel=np.stack(mels), label=np.array(labels),
                        fname=np.array(files))
    print(f"wrote {out}  ({os.path.getsize(out) / 1e6:.1f} MB)")
    return 0


def derive_meta(model_path: str) -> str:
    """<prefix>_meta.json for a model named <prefix>_{fp32,int8}[_anything].onnx.

    Splitting on the last underscore is wrong the moment a variant suffix is
    added (..._int8_conv.onnx), and picking up the wrong meta silently reorders
    the class names rather than failing, so cut at the precision tag instead.
    """
    base = os.path.basename(model_path)
    m = re.match(r"(.+?)_(?:fp32|int8)(?:_.*)?\.onnx$", base)
    if not m:
        raise SystemExit(f"cannot derive a meta path from {base!r}; pass --meta")
    return os.path.join(os.path.dirname(os.path.abspath(model_path)),
                        m.group(1) + "_meta.json")


def per_class(y_true, y_pred, classes):
    out = {}
    for c in classes:
        tp = int(np.sum((y_true == c) & (y_pred == c)))
        fn = int(np.sum((y_true == c) & (y_pred != c)))
        fp = int(np.sum((y_true != c) & (y_pred == c)))
        out[c] = {
            "recall": tp / (tp + fn) if tp + fn else 0.0,
            "precision": tp / (tp + fp) if tp + fp else 0.0,
            "support": tp + fn,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build-mels", action="store_true")
    ap.add_argument("--split", default=os.path.join(HERE, "split.json"))
    ap.add_argument("--arch", default="cnn10", choices=("cnn6", "cnn10"))
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--crop", default="head", choices=("head", "peak"),
                    help="must match the --crop the model's embeddings were extracted with")
    ap.add_argument("--mels", default=None, help="mel cache; defaults beside the model")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default=None, help="the .onnx to score and time")
    ap.add_argument("--meta", default=None, help="<prefix>_meta.json for the class order")
    ap.add_argument("--threads", type=int, default=0, help="0 = onnxruntime default")
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--time-only", type=int, default=0,
                    help="skip scoring; time this many clips instead")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--save-probs", default=None,
                    help="write the per-clip class probabilities, so an operating point "
                         "can be chosen without a second inference pass")
    args = ap.parse_args()

    crop_tag = "" if args.crop == "head" else f"_{args.crop}"
    mels_path = args.mels or os.path.join(
        HERE, f"testmels_{args.arch}_{args.window:g}s{crop_tag}.npz")
    if args.build_mels:
        return build_mels(args.split, args.arch, args.window, mels_path, args.limit,
                          args.crop)

    if not args.model:
        ap.error("--model is required unless --build-mels")

    import onnxruntime as ort

    d = np.load(mels_path, allow_pickle=True)
    mel, y_true = d["mel"], d["label"].astype(str)
    if args.limit:
        mel, y_true = mel[: args.limit], y_true[: args.limit]

    meta_path = args.meta or derive_meta(args.model)
    with open(meta_path, encoding="utf-8") as fh:
        classes = np.array(json.load(fh)["classes"])

    opts = ort.SessionOptions()
    if args.threads:
        opts.intra_op_num_threads = args.threads
        opts.inter_op_num_threads = 1
    sess = ort.InferenceSession(args.model, opts, providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name

    n = args.time_only or len(mel)
    x0 = mel[0][None].astype(np.float32)
    for _ in range(args.warmup):
        sess.run(None, {name: x0})

    probs, times = [], []
    for i in range(n):
        x = mel[i % len(mel)][None].astype(np.float32)
        t = time.perf_counter()
        out = sess.run(None, {name: x})[0]
        times.append((time.perf_counter() - t) * 1000)
        probs.append(out[0])
    times = np.array(times)

    label = os.path.basename(args.model)
    thr = args.threads or "default"
    print(f"\n{label}   threads={thr}   n={n}")
    print(f"  latency ms/clip   median {np.median(times):7.1f}   "
          f"mean {times.mean():7.1f}   p90 {np.percentile(times, 90):7.1f}")
    print(f"  real-time factor  {np.median(times) / 1000 / args.window:.3f}x "
          f"of a {args.window:g}s window")

    result = {"model": label, "threads": args.threads, "n": n,
              "median_ms": float(np.median(times)), "mean_ms": float(times.mean()),
              "p90_ms": float(np.percentile(times, 90)), "window_s": args.window}

    if not args.time_only:
        y_pred = classes[np.argmax(np.stack(probs), axis=1)]
        overall = float(np.mean(y_pred == y_true))
        pc = per_class(y_true, y_pred, list(classes))
        print(f"  overall accuracy  {100 * overall:.1f}%   ({len(y_true)} clips)")
        print(f"  {'class':<16}{'recall':>9}{'prec':>9}{'n':>6}")
        for c in classes:
            print(f"  {c:<16}{100 * pc[c]['recall']:8.1f}%{100 * pc[c]['precision']:8.1f}%"
                  f"{pc[c]['support']:6d}")
        result["overall"] = overall
        result["per_class"] = pc

    if args.save_probs and not args.time_only:
        np.savez_compressed(args.save_probs, probs=np.stack(probs),
                            label=y_true, classes=classes)
        print(f"  wrote {args.save_probs}")

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2)
        print(f"  wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
