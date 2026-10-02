"""Add extra training data to the frozen split without redrawing the test set.

The frozen split exists so two runs differ only by what was actually changed.
Redrawing it to absorb new data would forfeit that: a chainsaw score that moved
could be the new data or the new test set, and there would be no way to tell.

So this appends new recordings to the *train* side only. The test set stays
byte-identical to `split.json`, which makes the comparison a clean one - same
held-out recordings, more training data, one variable.

Guards, because both would silently invalidate the result:
  * a new recording whose group is already on the test side is dropped;
  * the resulting test set is asserted identical to the input's.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--index", required=True, help="index.json built with --audioset")
    ap.add_argument("--source", default="audioset", help="only add records from this source")
    ap.add_argument("--out", default=os.path.join("ml", "acoustic", "harness", "split_audioset.json"))
    args = ap.parse_args()

    with open(args.split, encoding="utf-8") as fh:

        spec = json.load(fh)
    rows = list(spec["records"])
    known = {r["group"] for r in rows}
    test_groups = {r["group"] for r in rows if r["split"] == "test"}

    with open(args.index, encoding="utf-8") as fh:

        idx = json.load(fh)
    added, dropped = [], Counter()
    for r in idx["records"]:
        if r["source"] != args.source:
            continue
        if r["group"] in test_groups:
            dropped["group_on_test_side"] += 1
            continue
        if r["group"] in known and any(x["file"] == r["file"] for x in rows):
            dropped["already_present"] += 1
            continue
        added.append({**r, "split": "train"})

    merged = rows + added
    before = sorted(x["file"] for x in rows if x["split"] == "test")
    after = sorted(x["file"] for x in merged if x["split"] == "test")
    if before != after:
        print("test set changed - refusing to write", flush=True)
        return 1

    by_label = Counter(r["label"] for r in added)
    print(f"added {len(added)} training files from {args.source!r}")
    for label, n in sorted(by_label.items()):
        recs = len({r['group'] for r in added if r['label'] == label})
        print(f"  {label:<16}{n:>6} files  {recs:>5} recordings")
    if dropped:
        print("dropped:", dict(dropped))
    print(f"test set unchanged: {len(after)} files")

    spec["records"] = merged
    spec["augmented_with"] = args.source
    with open(args.out, "w") as fh:
        json.dump(spec, fh, indent=1)
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
