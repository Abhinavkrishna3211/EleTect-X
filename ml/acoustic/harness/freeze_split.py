"""Freeze one group-aware train/test split and never redraw it.

Two problems this fixes, both measured rather than assumed:

1. **Leakage.** `build_index.py` shows 25.4% of `elephant_call` is duplicate
   recordings, and the upload script splits that corpus with a file-level
   shuffle (`edge_impulse_upload_acoustic.py:799`). Splitting on `group` keeps
   every copy of a recording on one side of the boundary.

2. **Unmeasurable change.** ml/acoustic/README.md caveat 13 records per-class
   swings of 15-20 points between runs that differ only in training randomness.
   Part of that is the split itself moving under each rebuild. Freezing it to
   disk means two runs differ only by what was actually changed.

Also carves a **field slice**: the clips recorded on this project's own hardware
(XIAO ESP32S3 / laptop / phone). Public-corpus accuracy and field accuracy are
different claims, and the field number is the one that predicts deployment.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter, defaultdict

TEST_FRACTION = 0.20


def group_table(records: list[dict]) -> dict[str, dict]:
    """Collapse file records into one entry per source recording."""
    groups: dict[str, dict] = {}
    for r in records:
        g = groups.setdefault(
            r["group"], {"label": r["label"], "source": r["source"], "files": [], "field": False}
        )
        g["files"].append(r)
        if r["source"] == "field_capture":
            g["field"] = True
    return groups


def split(groups: dict[str, dict], seed: int, test_fraction: float):
    """Stratified by class, grouped by recording, seeded.

    Field-captured recordings are allocated to test first, up to half the class
    test budget, so the field slice is large enough to mean something without
    starving training of the only in-domain audio available.
    """
    rng = random.Random(seed)
    by_label: dict[str, list[str]] = defaultdict(list)
    for gid, g in groups.items():
        by_label[g["label"]].append(gid)

    assign: dict[str, str] = {}
    for _label, gids in sorted(by_label.items()):
        gids = sorted(gids)
        rng.shuffle(gids)
        n_test = max(1, round(len(gids) * test_fraction))

        field = [g for g in gids if groups[g]["field"]]
        other = [g for g in gids if not groups[g]["field"]]
        rng.shuffle(field)
        rng.shuffle(other)

        take_field = min(len(field), n_test // 2)
        chosen = field[:take_field] + other[: n_test - take_field]
        chosen_set = set(chosen)
        for g in gids:
            assign[g] = "test" if g in chosen_set else "train"
    return assign


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default=os.path.join("ml", "acoustic", "harness", "index.json"))
    ap.add_argument("--out", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--seed", type=int, default=20260923)
    ap.add_argument("--test-fraction", type=float, default=TEST_FRACTION)
    args = ap.parse_args()

    with open(args.index, encoding="utf-8") as fh:

        idx = json.load(fh)
    records = idx["records"]
    groups = group_table(records)
    assign = split(groups, args.seed, args.test_fraction)

    # A recording is scored once. Each test recording contributes exactly one
    # file - the canonical `.norm` render where it exists, otherwise its single
    # alternate normalisation, since many stems are cached only as `.eN.norm`.
    # Dropping those outright would silently shrink the thin classes' test sets.
    # Training keeps every variant: there the duplication is free augmentation.
    rows = []
    test_seen: set[str] = set()
    by_group_sorted = sorted(
        records, key=lambda r: (r["group"], r["variant"] != "base", r["file"])
    )
    for r in by_group_sorted:
        side = assign[r["group"]]
        if side == "test":
            if r["group"] in test_seen:
                continue
            test_seen.add(r["group"])
        rows.append({**r, "split": side})

    files = Counter((r["label"], r["split"]) for r in rows)
    recs = defaultdict(set)
    for r in rows:
        recs[(r["label"], r["split"])].add(r["group"])
    field_test = Counter(r["label"] for r in rows if r["split"] == "test" and r["source"] == "field_capture")

    print(f"seed {args.seed}, grouped by recording, {args.test_fraction:.0%} test\n")
    print(f"{'class':<16}{'train files':>12}{'train recs':>12}{'test files':>12}{'test recs':>11}{'field test':>12}")
    for label in idx["classes"]:
        print(
            f"{label:<16}{files[(label, 'train')]:>12}{len(recs[(label, 'train')]):>12}"
            f"{files[(label, 'test')]:>12}{len(recs[(label, 'test')]):>11}{field_test[label]:>12}"
        )

    # Assert the property the whole harness rests on.
    train_groups = {r["group"] for r in rows if r["split"] == "train"}
    test_groups = {r["group"] for r in rows if r["split"] == "test"}
    overlap = train_groups & test_groups
    print(f"\nrecordings shared across the boundary: {len(overlap)}")
    if overlap:
        print("  LEAKAGE - split is invalid")
        return 1
    print("  clean - no recording appears on both sides")

    with open(args.out, "w") as fh:
        json.dump(
            {
                "seed": args.seed,
                "test_fraction": args.test_fraction,
                "classes": idx["classes"],
                "window_s": idx["window_s"],
                "records": rows,
            },
            fh,
            indent=1,
        )
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
