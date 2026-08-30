"""One-shot cleanup: remove the "Image<N>_"/"images<N>_" generic-uploader-named
contamination confirmed in the 28 Aug data-quality re-verification pass (third
pass) from Edge Impulse project 1097972, including any pseudo-IR synthetic
frames derived from those same source images.

Why this is a separate pass from a plain re-upload: elephant-detection-cxnt1-v2
was uploaded to this project before scripts/edge_impulse_upload_vision.py
carried the exclude_generic_named_scrape filter (see
_is_generic_named_scrape's docstring there, and ml/vision/README.md's "28 Aug -
data-quality re-verification, third pass" entry, for how the 164-filename
population was found and visually audited - 16/16 sampled were not real
Asian-elephant field photography). Filtering it out of the local manifest does
not remove what is already sitting live in the project - confirmed empirically
via ml/datasets/vision/raw/uploaded-1097972-elephant-detection-cxnt1-v2.json,
which records all 164 as already uploaded.

Matches by filename, reusing the exact same predicate the upload script's own
parse_coco() filter uses, imported directly, so a sample is deleted here if
and only if the same file would be silently dropped on the next real upload -
no separate matching logic to drift out of sync. Follows the same structure
and live raw-data list/delete protocol as
cleanup_broadcast_contamination_vision.py (28 Aug, second pass) - see that
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
    _is_generic_named_scrape,
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
    if _is_generic_named_scrape(source):
        return "generic_named_scrape"
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
