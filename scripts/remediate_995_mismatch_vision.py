"""One-shot remediation for the 995-sample live/manifest mismatch that
reconcile_project_counts() hard-failed on after the 28 Aug broadcast/African-
stock cleanup pass. See scripts/diag_reconcile_vision.py and the "28 Aug -
995-sample mismatch" entry in ml/vision/README.md for the full diagnosis.
Three independently-caused buckets, decomposed exactly (2555 orphans =
1368 cross-category + 1187 truly-gone; 1560 missing = 1368 + 192):

  1. ~1178 stale "public__..."-named swg-empty samples, live on project
     1097972 from before scripts/fetch_swg_camera_traps.py was rewritten to
     save images as "{lila_image_id}.jpg" instead of the flattened LILA path.
     Superseded, unreferenced by the current pipeline - deleted.
  2. ~1368 elephant-detection-cxnt1-v2 / pseudo-ir-elephant samples that are
     live and correct but filed under the "wrong" category relative to the
     freshly-regenerated manifest - a seeded shuffle over a pool this
     session's own contamination filters resized is not a stable-prefix
     operation, so the train/test split boundary moved for surviving
     samples. Nothing lost - moved to the category the manifest now expects
     via POST /raw-data/{id}/move, not deleted.
  3. ~192 new swg-eurasian-wild-pig (Boar) samples the manifest expects but
     that were never uploaded - already downloaded locally, just never
     pushed. Left for the caller to close with a plain (non-dry-run) run of
     scripts/edge_impulse_upload_vision.py after this script finishes; not
     handled here since it's a normal upload, not a remediation.

Only ever acts on samples whose normalized filename is confidently
classified into bucket 1 or 2 above by direct comparison against the fresh
manifest - never a blind prefix heuristic. Anything left over (the small
"truly gone, not public-prefixed" remainder) is printed and left untouched
for manual follow-up.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"
_EXT_SUFFIX = re.compile(r"\.(jpg|jpeg|png|bmp|webp)$", re.IGNORECASE)
_STALE_PUBLIC_PREFIX = re.compile(r"^public__")


def _request(url, api_key, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"x-api-key": api_key, "Content-Type": "application/json"})
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
    dry_run = "--dry-run" in sys.argv

    manifest = json.load(open(r"D:\projects\EleTect-X\ml\vision\dataset_manifest.json"))["classes"]
    expected_any = {}
    for label, entry in manifest.items():
        for category in ("training", "testing"):
            for name in entry[category]:
                norm = _EXT_SUFFIX.sub("", name)
                expected_any.setdefault(norm, []).append(category)

    print("Fetching remote sample list...")
    remote = remote_samples(project_id, api_key)
    print(f"  {len(remote)} remote samples")

    to_delete = []
    to_move = []
    unhandled = []
    for s in remote:
        norm = _EXT_SUFFIX.sub("", s["filename"])
        cats = expected_any.get(norm)
        if cats and s["_category"] not in cats:
            to_move.append((s, cats[0]))
        elif not cats and _STALE_PUBLIC_PREFIX.match(s["filename"]):
            to_delete.append(s)
        elif not cats:
            unhandled.append(s)

    print(f"\nBucket 1 (stale public__-named, delete): {len(to_delete)}")
    print(f"Bucket 2 (mis-categorized, move):          {len(to_move)}")
    print(f"Unhandled (truly gone, not public__-named): {len(unhandled)}")
    if unhandled:
        print("  sample of unhandled, left untouched:")
        for s in unhandled[:10]:
            print(f"    [{s['_category']}] id={s['id']} label={s.get('label')!r} filename={s['filename']!r}")

    if dry_run:
        print("\n--dry-run: not deleting or moving anything")
        return

    print(f"\nDeleting {len(to_delete)} stale samples...")
    deleted, del_failed = 0, []
    for i, s in enumerate(to_delete, 1):
        try:
            resp = _request(f"{STUDIO}/{project_id}/raw-data/{s['id']}", api_key, method="DELETE")
            if resp.get("success"):
                deleted += 1
            else:
                del_failed.append((s["id"], resp))
        except urllib.error.HTTPError as err:
            del_failed.append((s["id"], err.read().decode()[:200]))
        if i % 200 == 0:
            print(f"  {i}/{len(to_delete)} deletes processed")
        time.sleep(0.05)
    print(f"Deleted {deleted}/{len(to_delete)}.")
    if del_failed:
        print(f"{len(del_failed)} deletions failed:")
        for sid, reason in del_failed[:20]:
            print(f"  id={sid}: {reason}")

    print(f"\nMoving {len(to_move)} mis-categorized samples...")
    moved, move_failed = 0, []
    for i, (s, new_cat) in enumerate(to_move, 1):
        try:
            resp = _request(
                f"{STUDIO}/{project_id}/raw-data/{s['id']}/move",
                api_key,
                method="POST",
                body={"newCategory": new_cat},
            )
            if resp.get("success"):
                moved += 1
            else:
                move_failed.append((s["id"], resp))
        except urllib.error.HTTPError as err:
            move_failed.append((s["id"], err.read().decode()[:200]))
        if i % 200 == 0:
            print(f"  {i}/{len(to_move)} moves processed")
        time.sleep(0.05)
    print(f"Moved {moved}/{len(to_move)}.")
    if move_failed:
        print(f"{len(move_failed)} moves failed:")
        for sid, reason in move_failed[:20]:
            print(f"  id={sid}: {reason}")


if __name__ == "__main__":
    main()
