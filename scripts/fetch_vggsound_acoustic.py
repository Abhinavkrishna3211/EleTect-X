"""Fetch VGGSound segments for the acoustic classes, including hard negatives.

Two gaps in the AudioSet fetch this fills.

**Elephant.** AudioSet's ontology has no elephant entry at all, which is why
`elephant_call` still leans on a corpus that carries no licence
(ml/acoustic/README.md caveat 1). VGGSound has `elephant trumpeting`, an
independent source. Beyond adding data it enables a cross-corpus test: train on
one corpus, score on the other, which distinguishes having learned *elephant*
from having learned one corpus's recording conditions.

**Hard negatives.** The first backbone run scored chainsaw recall 93.5% at only
64.9% precision - it over-fires, and 11.1% of ambient came back as chainsaw.
Recall was the target and precision was the thing that actually broke. A false
chainsaw alert sends a forest officer out for nothing, so the fix is to train
against the specific sounds that get mistaken for the targets rather than to add
more of the targets:

  * `fireworks banging` -> ambient. This one is not theoretical. The deployment
    is in Kothamangalam, where temple festivals mean fireworks are the most
    likely false gunshot this system will ever hear.
  * `lawn mowing`, `tractor digging`, `engine accelerating`, `motorboat` ->
    ambient. Small petrol engines are what a chainsaw classifier confuses.

`cap gun shooting` is deliberately NOT mapped to gunshot. A cap gun is a toy;
training on it teaches the model to dispatch an officer for one.

Licensing note, same position as the AudioSet fetcher: the VGGSound CSV is
released CC BY 4.0, but the audio is YouTube content and is not ours to
redistribute. Clips stay in the local cache, which is gitignored.
"""

from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_audioset_acoustic import download  # one download implementation, reused

CSV_URL = "https://raw.githubusercontent.com/hche11/VGGSound/master/data/vggsound.csv"
OUT_DIR = os.path.join("ml", "datasets", "acoustic", "raw", "_vggsound_clips")
SPLIT_SEED = 20260923

# VGGSound label -> our wire class.
CLASS_LABELS = {
    "elephant_call": ["elephant trumpeting"],
    "chainsaw": ["chainsawing trees"],
    "gunshot": ["machine gun shooting"],
    "ambient": [
        # Confusers, the reason this fetch exists.
        "fireworks banging",
        "lawn mowing",
        "tractor digging",
        "engine accelerating",
        "motorboat",
        # Genuine forest background.
        "wind noise",
        "wind rustling leaves",
        "raining",
        "bird chirping",
        "cricket chirping",
        "frog croaking",
        "owl hooting",
        "woodpecker pecking tree",
    ],
}


def load_csv(path: str) -> list[dict]:
    """VGGSound rows are `ytid,start_seconds,label,split` with no header."""
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for rec in csv.reader(fh):
            if len(rec) < 3:
                continue
            try:
                start = float(rec[1])
            except ValueError:
                continue
            rows.append({"ytid": rec[0].strip(), "start": start, "label": rec[2].strip().strip('"')})
    return rows


def select(rows: list[dict], per_class_cap: int, exclude_ytids: set[str]):
    label_to_class = {lab: cls for cls, labs in CLASS_LABELS.items() for lab in labs}
    rng = random.Random(SPLIT_SEED)
    picked, stats = {}, Counter()

    # One segment per video. Several cuts of one video are the same recording,
    # and keeping only one keeps the corpus honest about how much independent
    # audio it actually holds.
    by_class: dict[str, dict[str, dict]] = {c: {} for c in CLASS_LABELS}
    for r in rows:
        cls = label_to_class.get(r["label"])
        if cls is None:
            continue
        if r["ytid"] in exclude_ytids:
            stats[f"{cls}:already_have"] += 1
            continue
        if r["ytid"] in by_class[cls]:
            stats[f"{cls}:same_video"] += 1
            continue
        by_class[cls][r["ytid"]] = r

    for cls, items in by_class.items():
        uniq = sorted(items.values(), key=lambda i: (i["ytid"], i["start"]))
        stats[f"{cls}:candidates"] = len(uniq)
        if per_class_cap and len(uniq) > per_class_cap:
            uniq = rng.sample(uniq, per_class_cap)
            uniq.sort(key=lambda i: (i["ytid"], i["start"]))
        picked[cls] = uniq
    return picked, stats


def existing_ytids(*dirs: str) -> set[str]:
    """Video ids already fetched, so the two corpora cannot double-count one."""
    out = set()
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            parts = name.rsplit(".", 1)[0].split("_")
            if len(parts) >= 3:
                out.add(parts[-2])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=os.path.join("ml", "datasets", "acoustic", "raw", "vggsound.csv"))
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--cap", type=int, default=400, help="max segments per class")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        import urllib.request

        os.makedirs(os.path.dirname(args.csv), exist_ok=True)
        print(f"downloading VGGSound index -> {args.csv}")
        urllib.request.urlretrieve(CSV_URL, args.csv)

    rows = load_csv(args.csv)
    have = existing_ytids(
        os.path.join("ml", "datasets", "acoustic", "raw", "_audioset_clips"), args.out_dir
    )
    picked, stats = select(rows, args.cap, have)

    print(f"{len(rows)} VGGSound rows, {len(have)} video ids already cached\n")
    for cls, items in sorted(picked.items()):
        print(f"  {cls:<16}{len(items):>5} selected  (of {stats[f'{cls}:candidates']} unique videos)")
    if args.dry_run:
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    ok = Counter()
    jobs = [(cls, item) for cls, items in picked.items() for item in items]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(download, item, cls, args.out_dir, args.seconds, "vs"): cls
            for cls, item in jobs
        }
        for n, fut in enumerate(as_completed(futures), 1):
            cls = futures[fut]
            try:
                rec = fut.result()
            except Exception:  # noqa: BLE001 - one dead video must not stop the fetch
                rec = None
            ok[cls if rec else f"{cls}:failed"] += 1
            if n % 25 == 0:
                print(f"  {n}/{len(jobs)}  ok={sum(v for k, v in ok.items() if ':' not in k)}", flush=True)

    print("\nfetched:")
    for k in sorted(ok):
        print(f"  {k:<24}{ok[k]:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
