"""One-shot cleanup: remove African-bush-elephant species contamination confirmed
in the 28 Aug data-quality re-verification pass (fourth pass) from Edge Impulse
project 1097972, including any pseudo-IR synthetic frames derived from those same
source images.

Why this is a separate pass from a plain re-upload: elephant-detection-cxnt1-v2
was uploaded to this project before scripts/edge_impulse_upload_vision.py's
_is_named_african_elephant() knew about the "af_<id>" filename convention (see
that function's docstring, and ml/vision/README.md's "28 Aug - data-quality
re-verification, fourth pass" entry, for how the 233-filename population was
found via diag_reconcile_vision.py's live-orphan report and visually confirmed
6/6 African bush elephant on a seeded sample). Filtering it out of the local
manifest does not remove what is already sitting live in the project.

Matches by filename, reusing the exact same predicates the upload script's own
parse_coco() filter uses (_is_named_african_elephant plus the pre-existing
AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES list, so this catches both the
newly-added af_ prefix contamination and any of the older visually-confirmed
stock-photo contamination that might still be live), imported directly, so a
sample is deleted here if and only if the same file would be silently dropped
on the next real upload - no separate matching logic to drift out of sync.
Follows the same structure and live raw-data list/delete protocol as
cleanup_generic_scrape_contamination_vision.py (28 Aug, third pass) - see that
script for the raw-data pagination and filename-normalization notes, not
repeated here.

Deliberately NOT run automatically by the upload script - this touches live
project data and is meant to be run once, by hand.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_impulse_upload_vision import (  # noqa: E402
    AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES,
    _is_named_african_elephant,
    _original_filename,
)

STUDIO = "https://studio.edgeimpulse.com/v1/api"
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)


def _request(url, api_key, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def remote_samples(project_id, api_key):
    """Every raw-data sample in the project, both categories, paginated."""
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


def is_contaminated(remote_filename):
    source = _EXT_SUFFIX.sub("", _original_filename(remote_filename))
    if _is_named_african_elephant(source):
        return "african_elephant_named"
    if source in AFRICAN_ELEPHANT_VISUALLY_CONFIRMED_FILENAMES:
        return "african_elephant_visually_confirmed"
    return None


def main():
    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID", "1097972")
    if not api_key:
        print("EI_API_KEY not set - source secrets/vision_pipeline.env first", file=sys.stderr)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = []
    reasons = {}
    for s in remote:
        reason = is_contaminated(s["filename"])
        if reason:
            to_delete.append(s)
            reasons[reason] = reasons.get(reason, 0) + 1

    print(f"Matched {len(to_delete)} remote samples as contaminated:")
    for reason, n in sorted(reasons.items()):
        print(f"  {reason}: {n}")

    by_cat = {}
    for s in to_delete:
        by_cat[s["_category"]] = by_cat.get(s["_category"], 0) + 1
    for cat, n in sorted(by_cat.items()):
        print(f"  in {cat}: {n}")

    if not to_delete:
        print("Nothing to delete - either already cleaned up or no matches found.")
        return

    if dry_run:
        print("--dry-run: not deleting anything")
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
