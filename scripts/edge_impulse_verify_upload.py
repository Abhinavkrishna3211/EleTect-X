"""Check that an Edge Impulse project holds exactly what split.json says it should.

The companion to scripts/edge_impulse_upload_from_split.py, and not an optional
one. That script's own guarantees stop at the last HTTP 200 it received: it
knows what it sent, not what the project ended up holding. Three things can
open a gap between those, and none of them announce themselves in the Studio UI:

  - A previous run that was interrupted after uploading but before flushing its
    ledger. The resumed run re-sends those files, and the ingestion API accepts
    them as new samples rather than collapsing them onto the originals - there
    is no content-hash deduplication (measured on project 1109511, 2026-09-23:
    25 re-sent clips became 25 extra samples, taking 4293 to 4318).
  - Uploading over a project that still holds an older split, where the same
    clip can end up in training under one split and testing under the other.
  - Any label or category the upload got wrong for a subset of files.

The first two matter for different reasons. Duplicates inside one category only
reweight a class, which is wasteful. The same clip held in *both* categories is
a train/test leak - the exact failure ADR 0025 was written to close, arriving
through the upload path rather than through the split. So this script reports
them separately and treats only the cross-category case as the serious one.

Exit status is the point: 0 when the project matches the split cell for cell,
1 otherwise, so a training run can be gated on it rather than started hopefully.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import urllib.error
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"


def fetch_samples(project_id: str, key: str, category: str) -> list[dict]:
    """Every sample in one category, paged out in full.

    The raw-data endpoint caps a page at 1000, so a 4000-sample project read
    without paging silently looks like a 1000-sample one - which would make this
    check pass on a project that is missing three quarters of its data.
    """
    out: list[dict] = []
    offset = 0
    while True:
        url = (f"{STUDIO}/{project_id}/raw-data?category={category}"
               f"&limit=1000&offset={offset}&excludeSensors=true")
        req = urllib.request.Request(url, headers={"x-api-key": key})
        with urllib.request.urlopen(req, timeout=120) as resp:
            page = json.loads(resp.read())
        got = page.get("samples", [])
        out.extend(got)
        if len(got) < 1000:
            return out
        offset += 1000


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    args = ap.parse_args()

    key = os.environ.get("EI_API_KEY", "").strip()
    project_id = os.environ.get("EI_PROJECT_ID", "").strip()
    if not key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID.", file=sys.stderr)
        return 2

    with open(args.split, encoding="utf-8") as fh:
        records = json.load(fh)["records"]
    want: collections.Counter = collections.Counter()
    for rec in records:
        want[("training" if rec["split"] == "train" else "testing", rec["label"])] += 1

    have: collections.Counter = collections.Counter()
    by_name: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for category in ("training", "testing"):
        try:
            samples = fetch_samples(project_id, key, category)
        except urllib.error.HTTPError as e:
            print(f"cannot read {category}: HTTP {e.code}", file=sys.stderr)
            return 2
        for s in samples:
            have[(category, s.get("label"))] += 1
            by_name[s.get("filename")].append((category, s.get("label")))

    print(f"{'category':10s} {'label':16s} {'want':>6} {'have':>6}  delta")
    mismatched = 0
    for cell in sorted(set(want) | set(have)):
        w, h = want[cell], have[cell]
        if w != h:
            mismatched += 1
        print(f"{cell[0]:10s} {cell[1]!s:16s} {w:>6} {h:>6} "
              f" {h - w:+d}{'   <-- MISMATCH' if w != h else ''}")
    print(f"\ntotal: want {sum(want.values())}, have {sum(have.values())}")

    dups = {fn: places for fn, places in by_name.items() if len(places) > 1}
    straddle = {fn: places for fn, places in dups.items()
                if len({cat for cat, _ in places}) > 1}
    if dups:
        print(f"\n{len(dups)} filename(s) appear more than once "
              f"({sum(len(v) - 1 for v in dups.values())} redundant copies)")
        for fn in list(dups)[:10]:
            print(f"    {fn}: {dups[fn]}")
    if straddle:
        print(f"\nLEAK: {len(straddle)} filename(s) held in BOTH categories:", file=sys.stderr)
        for fn in list(straddle)[:10]:
            print(f"    {fn}: {straddle[fn]}", file=sys.stderr)

    if straddle:
        print("\nFAIL: the project leaks across the split - do not train on it.", file=sys.stderr)
        return 1
    if mismatched:
        print(f"\nFAIL: {mismatched} label/category cell(s) disagree with {args.split}.",
              file=sys.stderr)
        return 1
    if dups:
        print("\nFAIL: counts match per cell but duplicate filenames are present.",
              file=sys.stderr)
        return 1
    print(f"\nOK: project {project_id} matches {args.split} exactly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
