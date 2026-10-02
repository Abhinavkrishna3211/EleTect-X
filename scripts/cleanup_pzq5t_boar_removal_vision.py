"""One-shot cleanup: remove every already-uploaded boarwatch/wild-boar-deterrent-pzq5t
v1 image (and any pseudo-IR frame derived from one) from Edge Impulse project
1097972.

Why this exists rather than a plain re-upload skip: scripts/edge_impulse_upload_vision.py
is append-only - dropping the pzq5t DATASETS entry stops it being re-sent, but the
~1,379 samples already sitting live stay live, and reconcile_project_counts() then
hard-fails because the project holds more than the fresh manifest expects. Same
situation, and same fix, as cleanup_thai_elephant_vision.py (wholesale source
removal, 28 Aug).

Why pzq5t is being dropped: see the removed DATASETS entry in
edge_impulse_upload_vision.py and ml/vision/README.md's 11 Sept Phase 3 entry.
Short version - ~40% of every split of the frozen v1 export carries baked-in
Roboflow "Cutout" augmentation (solid black rectangles composited over the photo)
plus ~25% other contamination, it was only ever instance-count padding, and the
Boar class has since gained cleaner domain-matched sources that did not exist when
it was added.

Deletes every live sample whose normalized original filename (extension stripped,
pseudo-IR prefix stripped via _original_filename) is in the frozen v1 export's
filename set. Roboflow stamps a per-export content hash into every filename, so a
filename hit is an unambiguous pzq5t-lineage sample - a direct upload or a
pseudoir_<n>_<pzq5t-stem> derivative. Mirrors
cleanup_boar_visual_contamination_vision.py's matching exactly so there is no
separate logic to drift.

sha256 content hashes are computed from the same local files and used only for a
report line: an image byte-identical to a pzq5t frame but live under a different
(kept) source's filename is left in place - it is correctly attributed, the fresh
manifest still expects it, and deleting it would open a reconcile shortfall.

Deliberately NOT run automatically by the upload script - this touches live project
data and is meant to be run once, by hand, after the EI version snapshot
(pre-boar-label-cleanup-20260911) and before the next real upload.
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edge_impulse_upload_vision import _original_filename

STUDIO = "https://studio.edgeimpulse.com/v1/api"
ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "ml", "datasets", "vision", "raw", "wild-boar-deterrent-pzq5t-v1",
)
SUBFOLDERS = ("train", "valid", "test")
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)


def _request(url, api_key, method="GET"):
    req = urllib.request.Request(url, method=method, headers={"x-api-key": api_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def local_index():
    """(names_no_ext, sha256s) for every image in the frozen pzq5t v1 export."""
    names = set()
    hashes = set()
    for sub in SUBFOLDERS:
        d = os.path.join(ROOT, sub)
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")):
                continue
            names.add(_EXT_SUFFIX.sub("", name))
            with open(os.path.join(d, name), "rb") as fh:
                hashes.add(hashlib.sha256(fh.read()).hexdigest())
    return names, hashes


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

    print("Indexing local wild-boar-deterrent-pzq5t-v1 files...")
    names_no_ext, sha256s = local_index()
    print(f"  {len(names_no_ext)} filenames, {len(sha256s)} distinct content hashes")

    print(f"Listing all raw-data samples in project {project_id}...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    # Filename match is authoritative: Roboflow stamps a per-export content hash
    # into every filename (<stem>_jpg.rf.<hash>), so a normalized filename hit is
    # unambiguously a pzq5t-lineage sample - either a direct upload or a
    # pseudoir_<n>_<pzq5t-stem> derivative (make_pseudo_ir recolors the pixels, so
    # its sha256 no longer matches, but the embedded original filename still does).
    # sha256-only hits are a different animal: an image byte-identical to a pzq5t
    # frame that is live under a DIFFERENT source's filename (a1flm, wcs-sus-scrofa,
    # trail-camera and pzq5t share some underlying scrape images; dedupe_by_content
    # kept whichever source was processed first). Those samples are correctly
    # attributed to a source that is staying, the fresh manifest still expects
    # them, and deleting them would open a reconcile shortfall - so they are
    # reported here and left in place.
    to_delete, hash_only = [], []
    for s in remote:
        norm = _EXT_SUFFIX.sub("", _original_filename(s["filename"]))
        if norm in names_no_ext:
            to_delete.append(s)
        elif s.get("sha256Hash") in sha256s:
            hash_only.append(s)

    pseudo = [s for s in to_delete if s["filename"].startswith("pseudoir_")]
    by_cat = {}
    for s in to_delete:
        by_cat[s["_category"]] = by_cat.get(s["_category"], 0) + 1
    print(
        f"Matched {len(to_delete)} live samples to pzq5t by filename "
        f"({len(to_delete) - len(pseudo)} direct + {len(pseudo)} pseudo-IR derivatives):"
    )
    for cat, n in sorted(by_cat.items()):
        print(f"  in {cat}: {n}")
    print(
        f"{len(hash_only)} further live samples are byte-identical to pzq5t content but "
        "attributed to another (kept) source - left in place, see comment in main()."
    )

    if not to_delete:
        print("Nothing to delete - either already cleaned up or no matches found.")
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
