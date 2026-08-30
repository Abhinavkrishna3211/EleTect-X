"""One-shot cleanup: remove the already-uploaded thai-elephant-dataset-v6 images
from Edge Impulse project 1097972.

Why this exists rather than a plain re-upload skip: Edge Impulse renames every
ingested file to an internal UUID and does not expose the original filename
back through GET raw-data, so the upload ledger (keyed by original filename)
cannot be used to target a delete. sha256 content hash is the one identifier
that survives ingestion unchanged - the ingestion response and the raw-data
listing both carry it - so this matches purely on file content, computed
locally from the same files scripts/edge_impulse_upload_vision.py sent.

See ml/vision/README.md's "28 Aug - bounding-box quality audit" entry and the
removed DATASETS entry in edge_impulse_upload_vision.py for why this source is
being dropped rather than kept: a direct visual audit found ~half its sample
is African elephant (wrong species for this project) with no filename-based
way to filter it, unlike elephant-detection-cxnt1-v2.

Deliberately NOT run automatically by the upload script - this touches live
project data and is meant to be run once, by hand, after confirming the
architecture sweep that trained on the contaminated data has finished (so the
sweep's own numbers stay internally consistent and comparable to each other).
"""
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"
ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ml", "datasets", "vision", "raw", "thai-elephant-dataset-v6",
)
SUBFOLDERS = ("train", "valid", "test")


def _request(url, api_key, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def local_hashes():
    """sha256 -> local path, for every image actually in the frozen v6 export."""
    hashes = {}
    for sub in SUBFOLDERS:
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.lower().endswith((".jpg", ".jpeg", ".png")):
                continue
            path = os.path.join(d, name)
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            hashes[digest] = path
    return hashes


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

    print("Hashing local thai-elephant-dataset-v6 files...")
    local = local_hashes()
    print(f"  {len(local)} local files hashed")

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = [s for s in remote if s.get("sha256Hash") in local]
    print(f"Matched {len(to_delete)} remote samples by content hash to thai-elephant-dataset-v6")
    if not to_delete:
        print("Nothing to delete - either already cleaned up or no hash matches found.")
        return

    if "--dry-run" in sys.argv:
        by_cat = {}
        for s in to_delete:
            by_cat[s.get("category", "?")] = by_cat.get(s.get("category", "?"), 0) + 1
        for cat, n in sorted(by_cat.items()):
            print(f"  in {cat}: {n}")
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

    unmatched_local = len(local) - len(to_delete)
    if unmatched_local:
        print(
            f"NOTE: {unmatched_local} local files had no remote hash match - either "
            "never uploaded (e.g. dropped by content-dedup on the way in) or already "
            "removed. Not an error, but worth a glance if the number is large."
        )


if __name__ == "__main__":
    main()
