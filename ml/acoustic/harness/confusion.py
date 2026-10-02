"""Confusion matrices for the exported ONNX graphs on the frozen 605-clip test split.

train_head.py and the export path both report overall accuracy and per-class
recall and precision, which between them still hide the thing this application
most needs to know: which way an error falls. An elephant call scored as ambient
is a missed alert; the same call scored as gunshot still raises an alarm. Those
are not interchangeable outcomes and no summary row distinguishes them.

Scores the graph as it will ship - the ONNX file through onnxruntime, not the
PyTorch model - so the matrix describes the artifact rather than its ancestor.
The front end is the processing block's FFT implementation, which parity_check.py
holds equal to torchlibrosa; scoring through either produces the same matrix.

Run: python confusion.py            (all three graphs in the report's table)
     python confusion.py --graph cnn10_10s_fp32.onnx --window 10 --crop head
"""

from __future__ import annotations

import argparse
import collections
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

# The three rows section 7.1 tabulates. Window and crop are not free parameters:
# they must match what the graph was exported and scored at, or the matrix
# describes a configuration nobody measured.
DEFAULT_GRAPHS = [
    ("fp32 10 s", "cnn10_10s_fp32.onnx", 10.0, "head"),
    ("int8 7-bit 10 s", "cnn10_10s_int8_conv_rr.onnx", 10.0, "head"),
    ("int8 7-bit 3 s peak", "cnn10_3s_int8_conv_rr.onnx", 3.0, "peak"),
]


def test_rows(split_path: str) -> list[dict]:
    with open(split_path, encoding="utf-8") as fh:
        return [r for r in json.load(fh)["records"] if r["split"] == "test"]


def score(graph: str, window: float, crop: str, rows: list[dict],
          labels: list[str]) -> collections.Counter:
    sess = ort.InferenceSession(os.path.join(HERE, graph), providers=["CPUExecutionProvider"])
    name = sess.get_inputs()[0].name
    conf: collections.Counter = collections.Counter()
    for r in rows:
        mel = logmel(load_clip(r["path"], window, crop))[None, None].astype(np.float32)
        conf[(r["label"], labels[int(sess.run(None, {name: mel})[0][0].argmax())])] += 1
    return conf


def report(title: str, graph: str, conf: collections.Counter, labels: list[str]) -> dict:
    n = sum(conf.values())
    hit = sum(v for (a, p), v in conf.items() if a == p)
    width = max(len(x) for x in labels) + 2
    print(f"\n{title}  -  {graph}")
    print(f"  overall {100.0 * hit / max(n, 1):.1f}%  ({hit}/{n})")
    print("  " + "actual v / pred >".ljust(width)
          + "".join(f"{x[:9]:>11}" for x in labels) + f"{'recall':>9}")
    for a in labels:
        total = sum(conf[(a, p)] for p in labels)
        print("  " + a.ljust(width) + "".join(f"{conf[(a, p)]:>11}" for p in labels)
              + f"{100.0 * conf[(a, a)] / max(total, 1):>8.1f}%")
    print("  " + "precision".ljust(width)
          + "".join(f"{100.0 * conf[(p, p)] / max(sum(conf[(a, p)] for a in labels), 1):>10.1f}%"
                    for p in labels))
    return {"overall": hit / max(n, 1), "n": n,
            "matrix": {f"{a}->{p}": v for (a, p), v in sorted(conf.items())}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=None, help="score one graph instead of the report's three")
    ap.add_argument("--window", type=float, default=10.0)
    ap.add_argument("--crop", default="head", choices=("head", "peak"))
    ap.add_argument("--meta", default=os.path.join(HERE, "cnn10_10s_meta.json"))
    ap.add_argument("--split", default=os.path.join(HERE, "split.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "confusion_results.json"))
    args = ap.parse_args()

    with open(args.meta, encoding="utf-8") as fh:
        labels = json.load(fh)["classes"]
    rows = test_rows(args.split)
    print(f"{len(rows)} test clips, classes {labels}")

    graphs = ([(args.graph, args.graph, args.window, args.crop)] if args.graph
              else DEFAULT_GRAPHS)
    results = {}
    for title, graph, window, crop in graphs:
        results[title] = report(title, graph, score(graph, window, crop, rows, labels), labels)

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"\nwrote {os.path.basename(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
