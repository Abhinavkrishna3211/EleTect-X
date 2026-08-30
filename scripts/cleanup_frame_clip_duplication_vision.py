"""One-shot cleanup: remove the frame-clip duplication cut confirmed in the
28 Aug frame-clip audit from Edge Impulse project 1097972, including any
pseudo-IR synthetic frame derived from one of the cut source images.

Why this is a separate pass from a plain re-upload: elephant-detection-cxnt1-v2's
"frame" clip (984 images, frame4338-frame5791, ~39% of the whole source - one
continuous dashcam sequence, the viral RAJAMURUGAN "elephant reaching into a
stopped truck" video, baked-in "U TURN" overlay text) was live-uploaded in full
before cap_named_group() existed in scripts/edge_impulse_upload_vision.py. The
user's 28 Aug decision on this finding (see that function's docstring, and
ml/vision/README.md's frame-clip entry) was to keep the clip as legitimate
training data - it is a real elephant, not a species/broadcast defect - but cut
its duplication down to 10 diverse frames spread evenly across the clip's
numeric range. Capping the local manifest does not remove the other 974 frames
already sitting live in the project.

Computes the exact kept-vs-dropped split by running the real upload pipeline's
own parse_coco() -> cap_named_group() locally, imported directly rather than
re-implemented, so a sample is deleted here if and only if the next real upload
would not include it. Follows the same live raw-data list/delete protocol as
the other cleanup_*_vision.py scripts in this directory - see
cleanup_species_contamination_vision.py for the pagination and filename-
normalization notes, not repeated here.

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
    DATASETS,
    _original_filename,
    cap_named_group,
    fetch_dataset,
    parse_coco,
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


def dropped_frame_filenames(rf_key):
    """The exact set of source filenames (extension stripped) cap_named_group()
    cuts from the elephant-detection-cxnt1-v2 "frame" clip, derived by running
    the real upload pipeline's own parse_coco() + cap_named_group() locally -
    not re-implemented, so this can never drift from what a fresh upload does.
    """
    ds = next(d for d in DATASETS if d["slug"] == "elephant-detection-cxnt1-v2")
    root = fetch_dataset(ds, rf_key)
    records, _drops, _background = parse_coco(root, ds)
    before = {r["name"] for r in records if r["group"] == "frame"}
    after = {
        r["name"]
        for r in cap_named_group(records, "frame", ds["group_caps"]["frame"], ds["label"])
        if r["group"] == "frame"
    }
    return {_EXT_SUFFIX.sub("", name) for name in before - after}


def main():
    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID", "1097972")
    rf_key = os.environ.get("RF_API_KEY") or os.environ.get("ROBOFLOW_API_KEY")
    if not api_key:
        print("EI_API_KEY not set - source secrets/vision_pipeline.env first", file=sys.stderr)
        sys.exit(1)

    dry_run = "--dry-run" in sys.argv

    print("Computing the frame-clip drop set from the local source + pipeline...")
    drop_names = dropped_frame_filenames(rf_key)
    print(f"  {len(drop_names)} source filenames to drop")

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = [
        s
        for s in remote
        if _EXT_SUFFIX.sub("", _original_filename(s["filename"])) in drop_names
    ]

    print(f"Matched {len(to_delete)} remote samples to delete (incl. any pseudo-IR derivatives):")
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
