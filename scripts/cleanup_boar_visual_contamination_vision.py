"""One-shot cleanup: remove the Boar visual-contamination filenames confirmed
across the two manual visual-audit passes (56 filenames, then an 11-filename
second pass over a fresh n=24 sample) from Edge Impulse project 1097972,
including any pseudo-IR synthetic frame derived from one of them.

Why this is a separate pass from a plain re-upload: wild-boar-a1flm-v1 and
wild-boar-deterrent-pzq5t-v1 were uploaded to this project before
scripts/edge_impulse_upload_vision.py's BOAR_VISUALLY_CONTAMINATED_FILENAMES
carried this pass's 11 new entries (see that constant's docstring, and
ml/vision/README.md's "28 Aug - data-quality re-verification" entries, for how
each filename was individually opened and visually confirmed - domestic pig,
warthog, watermarked stock, or otherwise not a real wild-boar field frame).
Filtering them out of the local manifest does not remove what is already
sitting live in the project.

Matches by filename against BOAR_VISUALLY_CONTAMINATED_FILENAMES, imported
directly, so a sample is deleted here if and only if the same file would be
silently dropped on the next real upload - no separate matching logic to drift
out of sync. Follows the same live raw-data list/delete protocol as the other
cleanup_*_vision.py scripts in this directory - see
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
    BOAR_VISUALLY_CONTAMINATED_FILENAMES,
    _original_filename,
)

STUDIO = "https://studio.edgeimpulse.com/v1/api"
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)
# The remote "filename" field has already had its final extension stripped by
# Edge Impulse; normalize both sides the same way before comparing against the
# local set, whose entries are full local filenames (with extension).
_CONTAMINATED_NO_EXT = frozenset(
    _EXT_SUFFIX.sub("", n) for n in BOAR_VISUALLY_CONTAMINATED_FILENAMES
)


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
    return source in _CONTAMINATED_NO_EXT


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

    to_delete = [s for s in remote if is_contaminated(s["filename"])]

    print(f"Matched {len(to_delete)} remote samples as contaminated (incl. any pseudo-IR derivatives):")
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
