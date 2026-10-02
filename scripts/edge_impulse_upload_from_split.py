"""Upload the acoustic corpus to Edge Impulse using the frozen, group-aware split.

Why this exists alongside `edge_impulse_upload_acoustic.py`. That script decides
train vs test per source, with a different rule for each: ESC-50 by the dataset's
fold column, Mendeley chronologically, Freesound by a seeded sample. None of
those rules knows what a *recording* is, so copies of one recording - the
`.norm`/`.e2.norm` variant pair, ESC-50 takes A/B/C of one Freesound id, the
`_aug_N` elephant clips, and consecutive 10 s slices of a single field session -
routinely landed on opposite sides. ADR 0025 measures what that was worth:
25.4% of `elephant_call` leaked at the variant level alone, and the field
chainsaw slice scored a flawless 100% because five chunks of the one session
being tested were sitting in training.

The fix is not a better per-source rule. It is to stop deciding here at all:
`split.json` is frozen once, by `freeze_split.py`, on the recording groups that
`build_index.py` assigns, and this script does nothing but honour it. A file's
category is read from the split, never computed. That makes the Studio
dashboard's held-out number directly comparable to the harness's instead of
being optimistic by an unknown, per-class-uneven margin.

Upload a corpus split this way into a project that already holds the old one and
the result is neither. Measured against project 1109511 on 2026-09-23: 25 clips
were re-sent after an interrupted run had already uploaded them, and the
ingestion API accepted all 25 as *new samples* rather than collapsing them onto
the existing ones. There is no content-hash deduplication to rely on. Two
consequences, the second much worse than the first: duplicates silently reweight
whichever class they land in, and a clip re-sent under a different split ends up
held in training and testing at once - a leak of exactly the kind ADR 0025
exists to prevent, arriving through the upload path instead of the split.
This targets an empty project for that reason, and refuses to run against one
that already holds samples unless told otherwise. Verifying the per-label,
per-category counts against the split afterwards is not optional - it is the
only thing that catches a partial previous run.
"""

from __future__ import annotations

import argparse
import collections
import concurrent.futures
import json
import os
import sys
import time

import requests

INGEST = "https://ingestion.edgeimpulse.com/api"
STUDIO = "https://studio.edgeimpulse.com/v1/api"


def studio_sample_count(project_id: str, key: str) -> int | None:
    """Total samples already in the project, or None if the API will not say."""
    try:
        r = requests.get(
            f"{STUDIO}/{project_id}/raw-data/count",
            headers={"x-api-key": key}, timeout=30,
        )
        if r.ok:
            return int(r.json().get("count", 0))
    except requests.RequestException:
        pass
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-nonempty", action="store_true",
                    help="upload even though the project already holds samples (see module docstring)")
    ap.add_argument("--ledger", default=os.path.join("ml", "acoustic", "ei_upload_ledger.json"),
                    help="records what was accepted, so an interrupted run resumes")
    ap.add_argument("--limit", type=int, default=0, help="stop after N uploads (smoke test)")
    ap.add_argument("--workers", type=int, default=8,
                    help="parallel upload connections; 1 restores serial uploading")
    args = ap.parse_args()

    with open(args.split, encoding="utf-8") as fh:
        spec = json.load(fh)
    records = spec["records"]

    by = collections.Counter((r["label"], r["split"]) for r in records)
    print(f"{args.split}: {len(records)} files")
    for (label, split), n in sorted(by.items()):
        print(f"  {label:<16} {split:<6} {n:>5}")
    groups = {r["group"] for r in records}
    tr_g = {r["group"] for r in records if r["split"] == "train"}
    te_g = {r["group"] for r in records if r["split"] == "test"}
    print(f"  {len(groups)} recordings; train {len(tr_g)} / test {len(te_g)}")
    straddle = tr_g & te_g
    if straddle:
        raise SystemExit(
            f"FATAL: {len(straddle)} recording(s) appear on both sides of the split, "
            f"e.g. {sorted(straddle)[:3]} - the split file is not leak-free, refusing to upload"
        )
    print("  no recording straddles the split")

    if args.dry_run:
        print("\ndry run - nothing uploaded")
        return 0

    key = os.environ.get("EI_API_KEY", "").strip()
    project_id = os.environ.get("EI_PROJECT_ID", "").strip()
    if not key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID (or pass --dry-run).", file=sys.stderr)
        return 2

    n_have = studio_sample_count(project_id, key)
    if n_have:
        print(f"\nproject {project_id} already holds {n_have} samples.")
        if not args.allow_nonempty:
            print("Refusing: Edge Impulse dedupes on content hash, so clips already present "
                  "under the old split would keep their old category and this upload would "
                  "produce a mixture of both splits. Use an empty project, or pass "
                  "--allow-nonempty if you know the project is clean.", file=sys.stderr)
            return 2

    ledger: dict[str, str] = {}
    if os.path.exists(args.ledger):
        with open(args.ledger, encoding="utf-8") as fh:
            ledger = json.load(fh)
        print(f"ledger: {len(ledger)} file(s) already uploaded, skipping those")

    todo = [r for r in records if r["file"] not in ledger]
    if args.limit:
        todo = todo[: args.limit]
    print(f"uploading {len(todo)} file(s) to project {project_id}\n")

    ok = fail = 0
    t0 = time.time()

    def send(r):
        """One record -> (record, category, error or None).

        Retries only the two failures that are about the connection rather than
        the file: a transient network drop, and the ingestion API's own rate
        limiter. A 4xx that names the file is a real rejection and is reported.
        """
        path = r["path"]
        if not os.path.exists(path):
            return r, None, f"MISSING {path}"
        category = "training" if r["split"] == "train" else "testing"
        delay = 2.0
        for attempt in range(4):
            try:
                with open(path, "rb") as fh:
                    resp = requests.post(
                        f"{INGEST}/{category}/files",
                        headers={"x-api-key": key, "x-label": r["label"]},
                        files={"data": (r["file"], fh, "audio/wav")},
                        timeout=120,
                    )
            except requests.RequestException as e:
                if attempt == 3:
                    return r, None, f"ERROR {r['file']}: {e}"
                time.sleep(delay)
                delay *= 2
                continue
            if resp.status_code == 200:
                return r, category, None
            if resp.status_code in (429, 502, 503, 504) and attempt < 3:
                time.sleep(delay)
                delay *= 2
                continue
            return r, None, f"HTTP {resp.status_code} {r['file']}: {resp.text[:160]}"
        return r, None, f"{r['file']}: retries exhausted"

    # Uploads are latency-bound, not CPU-bound: one file per request against a
    # remote endpoint runs at ~0.4/s, which is ~3 h for this corpus. The ledger
    # already makes the run resumable, so the only thing a pool changes is how
    # many requests are in flight. --workers 1 restores the serial behaviour.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(send, r) for r in todo]
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            r, category, err = fut.result()
            if err:
                print(f"  {err}", flush=True)
                fail += 1
            else:
                ledger[r["file"]] = category
                ok += 1
            if i % 200 == 0 or i == len(todo):
                rate = i / max(time.time() - t0, 1e-9)
                print(f"  {i}/{len(todo)}  ok={ok} fail={fail}  {rate:.1f}/s"
                      f"  eta {(len(todo) - i) / max(rate, 1e-9) / 60:.1f} min", flush=True)
                with open(args.ledger, "w", encoding="utf-8") as fh:
                    json.dump(ledger, fh)

    with open(args.ledger, "w", encoding="utf-8") as fh:
        json.dump(ledger, fh)
    print(f"\n{ok} uploaded, {fail} failed, ledger -> {args.ledger}")
    print(f"https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
