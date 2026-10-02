"""One-shot cleanup: remove every live Fox-labeled sample from Edge Impulse
project 1097972 so the live impulse can be retrained on the exact champion
recipe (Boar/Elephant/Background only) and Studio's live Testing tab shows
real champion-equivalent numbers again.

Why this exists rather than a plain re-upload skip: scripts/edge_impulse_upload_vision.py
is append-only - dropping the four Fox DATASETS entries stops them being re-sent, but
the 1,379 samples already sitting live stay live, and reconcile_project_counts() would
then hard-fail because the project holds more than the fresh manifest expects. Same
situation, and same fix, as cleanup_pzq5t_boar_removal_vision.py and
cleanup_thai_elephant_vision.py - except Fox removal is a whole-class drop, not a
single-source drop, so this deletes by label rather than by a frozen source's filename
set.

Why Fox is being dropped from the live project (not from the codebase's research
record): see ml/vision/README.md's 14 Sept entry. Short version - the user asked
Edge Impulse Studio's live project to reflect the actual champion (Boar/Elephant/
Background, deployed as etx_cpu_final_0830.eim), and build_impulse() in
edge_impulse_train_vision.py deletes and rebuilds the impulse on every run, so as
long as Fox samples were live any retrain would still produce a 3-class model. The
Fox work itself is not abandoned - it stayed a research branch (real recall gains on
the motivating encounter, but no clean win across every metric this project tracks)
and its source imagery is not lost: deepnetworkdevelopment-fox-detection-7iqxq-v2,
mgr-l8rhf-fox-sldyl-v1 and kawaharalabo-far-infrared-rays-animals-v5 remain pullable
from Roboflow at their recorded versions, and board-captures-fox-encounter1 remains
on disk under ml/datasets/vision/raw/.

Deletes every raw-data sample (both training and testing categories) whose label's
first comma-joined token is "Fox" - matches the same parsing convention already used
in score_held_out() and fox_source_breakdown.py for this project's comma-joined
per-box label field.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"


def _request(url, api_key, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def remote_samples(project_id, api_key):
    samples = []
    for category in ("training", "testing"):
        offset = 0
        limit = 1000
        while True:
            data = _request(
                f"{STUDIO}/{project_id}/raw-data?category={category}&limit={limit}&offset={offset}",
                api_key,
            )
            if not data.get("success"):
                raise RuntimeError(f"raw-data list failed: {data}")
            batch = data.get("samples", [])
            for s in batch:
                s["_category"] = category
            samples.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
    return samples


def main():
    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID", "1097972")
    if not api_key:
        print("EI_API_KEY not set - source secrets/vision_pipeline.env first", file=sys.stderr)
        sys.exit(1)

    # Opt in to the destructive path, do not opt out of it. This deletes live
    # samples from a shared Edge Impulse project; there is no undo and no
    # confirmation prompt, and this script's own docstring says it is meant to
    # be run once, by hand. Defaulting to delete meant the bare command - the
    # one you type when you are reading the file to find out what it does - was
    # the irreversible one. --dry-run is still accepted and still means a dry
    # run, so nothing anyone already had in their shell history changed meaning.
    dry_run = "--apply" not in sys.argv

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = []
    for s in remote:
        raw_label = (s.get("label") or "-").strip()
        if raw_label.split(",")[0].strip() == "Fox":
            to_delete.append(s)

    by_cat = {}
    for s in to_delete:
        by_cat[s["_category"]] = by_cat.get(s["_category"], 0) + 1
    print(f"Matched {len(to_delete)} live Fox samples:")
    for cat, n in sorted(by_cat.items()):
        print(f"  in {cat}: {n}")

    if not to_delete:
        print("Nothing to delete.")
        return

    if dry_run:
        print("Nothing deleted. Re-run with --apply to delete for real.")
        for s in to_delete[:15]:
            print(f"  [{s['_category']}] id={s['id']} label={s.get('label')!r} filename={s['filename']!r}")
        return

    deleted = 0
    failed = []
    for i, sample in enumerate(to_delete, 1):
        sid = sample["id"]
        try:
            resp = _request(f"{STUDIO}/{project_id}/raw-data/{sid}", api_key, method="DELETE")
            if resp.get("success"):
                deleted += 1
            else:
                failed.append((sid, resp))
        except urllib.error.HTTPError as err:
            failed.append((sid, err.read().decode()[:200]))
        if i % 100 == 0:
            print(f"  {i}/{len(to_delete)} processed")
        time.sleep(0.05)

    print(f"Deleted {deleted}/{len(to_delete)} matched samples.")
    if failed:
        print(f"{len(failed)} deletions failed:")
        for sid, reason in failed[:20]:
            print(f"  id={sid}: {reason}")


if __name__ == "__main__":
    main()
