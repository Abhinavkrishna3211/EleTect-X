"""One-shot revert: remove the 1,596 swg-empty Background images added to Edge
Impulse project 1097972 on 13 Sept 2026 (the "empty-only uncap" pass, EI version
snapshot id 53707954, jobs 53728184/53728795/53728824-53728909).

Why this exists: that pass raised TARGET_PER_PERIOD_EMPTY from 1200 to 2000 in
fetch_swg_camera_traps.py (pig target left untouched at 1200, so Boar stayed
pinned at exactly 1,800 - confirmed by the upload dry-run's "0 new groups" for
swg-eurasian-wild-pig). The resulting full 5-point threshold sweep showed:

  - Background FP rate at threshold 0.05 (the deployed operating point) got
    WORSE, not better: 0.170 vs the champion's 0.166. No sweep point improved
    by more than 1.3pt, let alone the >2pt-across->=3-points bar.
  - Elephant recall dropped 2.0-3.3pt at every single one of the 5 thresholds
    (0.906->0.886, 0.893->0.865, 0.875->0.842, 0.856->0.825, 0.806->0.785) -
    consistent, decisive, far past the 1.5pt noise floor.
  - Boar recall drifted down slightly (up to -1.1pt at threshold 0.5), at/near
    the 1pt noise floor - not the primary problem, but not an improvement either.

This is the same shared-backbone auto-class-weight reweighting effect already
documented twice for Boar-volume changes (see boar-representation-audit.md),
now confirmed a third time for a pure Background-volume change: growing one
class's sample count shifts the others' effective training weight, and here it
cost Elephant recall specifically. See ml/vision/README.md's 13 Sept entry for
the full sweep table and verdict.

Per the standing project directive ("never regress and lose previous model or
its settings ... it should be reproducible"), the corpus itself is reverted,
not just the recipe - leaving the extra 1,596 images live would mean a future
run of the unchanged champion recipe no longer reproduces the documented
champion baseline (Boar R 0.852 / Elephant R 0.906 / BG FP 0.166 @ 0.05).

Reconstructs the OLD (pre-bump) 2,399-image swg-empty selection by calling
fetch_swg_camera_traps.select_empty() with target_per_period=1200 (the value
in place when the champion was last reproduced) directly against the cached
metadata - no network re-fetch, no re-download. Diffs that against the current
on-disk _annotations.coco.json (3,998 images) to get the exact filenames added
by the bump, then deletes only those from the live project by normalized
filename, mirroring cleanup_pzq5t_boar_removal_vision.py's matching exactly.

Deliberately NOT run automatically - this touches live project data. Run once,
by hand, after confirming the sweep verdict in the README.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_impulse_upload_vision import _original_filename
from fetch_swg_camera_traps import IMAGE_ROOT, ensure_meta, select_empty

STUDIO = "https://studio.edgeimpulse.com/v1/api"
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)
OLD_TARGET_PER_PERIOD = 1200


def _request(url, api_key, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def old_filename_set():
    """Recompute the pre-bump (target=1200) empty selection's saved filenames.

    select_empty() returns each candidate's ORIGINAL GCS path in "file_name"
    (e.g. "public/vietnam/loc_0846/2019/04/image_00169.jpg") - fetch_images()
    renames every download to "<id>.jpg" (the LILA image id, always unique)
    before writing the coco doc, so that is the identifier that must be
    compared here, not a basename of the original path (many locations share
    generic basenames like "image_00001.jpg", which collapses under a naive
    os.path.basename() set and undercounts badly).
    """
    class_doc, _ = ensure_meta()
    old_selected = select_empty(class_doc, target_per_period=OLD_TARGET_PER_PERIOD)
    return {f"{im['id']}.jpg" for im in old_selected}


def current_filename_set():
    """The full current on-disk annotations (target=2000, 3,998 images)."""
    ann_path = os.path.join(IMAGE_ROOT, "empty", "_annotations.coco.json")
    with open(ann_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return {im["file_name"] for im in doc["images"]}


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

    print("Recomputing pre-bump (target=1200) swg-empty selection from cached metadata...")
    old_names = old_filename_set()
    print(f"  {len(old_names)} images in the pre-bump selection")

    print("Reading current on-disk swg-empty annotations (target=2000)...")
    current_names = current_filename_set()
    print(f"  {len(current_names)} images in the current selection")

    added_names = current_names - old_names
    print(f"  {len(added_names)} images were added by the bump")
    missing = old_names - current_names
    if missing:
        # A pre-bump image absent from the larger current selection is only
        # safe to ignore if it is a permanent decode failure (present in both
        # runs' failed.json, so it was never written to either coco.json) -
        # anything else means the prefix assumption broke and this script's
        # whole approach is unsound.
        failed_path = os.path.join(IMAGE_ROOT, "empty", "failed.json")
        with open(failed_path, encoding="utf-8") as fh:
            failed_ids = {f"{f['id']}.jpg" for f in json.load(fh)}
        unexplained = missing - failed_ids
        if unexplained:
            print(f"  WARNING: {len(unexplained)} pre-bump images are missing and NOT explained by failed.json - stop and check")
            return
        print(f"  {len(missing)} pre-bump image(s) missing from the current selection, all explained by failed.json (permanent decode failures) - continuing")

    added_stems = {_EXT_SUFFIX.sub("", os.path.basename(n)) for n in added_names}

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = []
    for s in remote:
        norm = _EXT_SUFFIX.sub("", _original_filename(s["filename"]))
        if norm in added_stems:
            to_delete.append(s)

    by_cat = {}
    for s in to_delete:
        by_cat[s["_category"]] = by_cat.get(s["_category"], 0) + 1
    print(f"Matched {len(to_delete)} live samples to the bump-added filename set:")
    for cat, n in sorted(by_cat.items()):
        print(f"  in {cat}: {n}")

    unmatched = len(added_stems) - len(to_delete)
    if unmatched:
        # Expected in small numbers: edge_impulse_upload_vision.py's own
        # content-duplicate dedup drops a few of the newly-drawn images before
        # upload (byte-identical to an already-live frame from the same burst -
        # see its "dropped N (content_duplicate)" line from the upload run),
        # so those were never live to begin with. A large gap means something
        # else is wrong - stop rather than guess.
        print(f"  {unmatched} of the added filenames were never live (upload-time content-dedup) - expected in small numbers")
        if unmatched > 20:
            print("  WARNING: gap too large to attribute to content-dedup alone - stop and check before deleting")
            return

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
