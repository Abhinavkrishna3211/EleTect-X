"""Island Conservation Camera Traps "pig" category - by-eye verification pass,
Phase 4.2 (12 Sept 2026), same discipline as the SA-FARI six-point checklist in
boar-representation-audit.md: before any frame from a new source touches a
training job, draw a seeded sample, render contact sheets with boxes, and look
at every one by eye. This is the pass boar-representation-audit.md's 4 Sept
entry flagged as the open follow-up for this source ("per-island pig count not
found... whether island night-flash IR imagery is well represented... whether
'pig' means the same feral/wild Sus scrofa phenotype").

Source: LILA BC, https://lila.science/datasets/island-conservation-camera-traps/
License: CDLA-Permissive-1.0 (matches the fully-commercial-permissive sources
already in this project's corpus - no NC-style sign-off question like SA-FARI).
Metadata: island_conservation_camera_traps_1.02.json (COCO Camera Traps format,
73MB, category id 37 = "pig"). Images: public GCS bucket
gs://public-datasets-lila/islandconservationcameratraps/public/<file_name>,
fetched here over HTTPS via storage.googleapis.com - no auth needed, matches
the metadata zip's own hosting.

Direct read of the metadata (not the LILA site's rounded dataset-wide figures):
2,588 "pig" boxes across 2,288 distinct images, 28 camera locations, exactly
two countries by location-name prefix - micronesia (1,185 images) and
puertorico (1,103 images). Hour-of-day histogram from each image's own
`datetime` field (camera-local clock, not necessarily true local time, but a
consistent per-camera proxy) shows real spread across night hours, not a
daylight-only source - see this script's own printed histogram for the exact
counts. bbox area fractions run min 0.0018 / median 0.123 / max 0.984 against
each image's own width/height - well clear of MIN_BOX_AREA_FRACTION (0.0003)
used elsewhere in this project's pipeline, no degenerate near-zero boxes.

This script only audits; it does not build a training source. That is a
separate follow-up once/if this sample passes by eye.
"""
import collections
import json
import os
import random
import urllib.error
import urllib.parse
import urllib.request

from audit_boar_sample import RAW, contact_sheet

META_PATH = os.path.join(
    os.environ.get("TEMP", ""), "ic_audit", "ic_meta",
    "island_conservation_camera_traps_1.02.json",
)
GCS_BASE = "https://storage.googleapis.com/public-datasets-lila/islandconservationcameratraps/public"
PIG_CATEGORY_ID = 37

OUT_DIR = os.path.join(RAW, "_audit_tmp")
CACHE_DIR = os.path.join(OUT_DIR, "ic_pig_frames_cache")


def load_pig_records(meta_path):
    with open(meta_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    images_by_id = {im["id"]: im for im in doc["images"]}
    boxes_by_image = collections.defaultdict(list)
    for ann in doc["annotations"]:
        if ann["category_id"] == PIG_CATEGORY_ID:
            boxes_by_image[ann["image_id"]].append(ann["bbox"])
    return images_by_id, boxes_by_image


def hour_bucket(datetime_str):
    if not datetime_str:
        return None
    try:
        hour = int(datetime_str.split(" ")[1].split(":")[0])
    except (IndexError, ValueError):
        return None
    if 6 <= hour < 18:
        return "day"
    return "night"


def fetch_image(file_name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    local = os.path.join(CACHE_DIR, file_name.replace("/", "_"))
    if not os.path.exists(local):
        url = f"{GCS_BASE}/{urllib.parse.quote(file_name)}"
        urllib.request.urlretrieve(url, local)
    return local


def main():
    images_by_id, boxes_by_image = load_pig_records(META_PATH)
    pig_image_ids = sorted(boxes_by_image)
    print(f"pig images: {len(pig_image_ids)}, pig boxes: "
          f"{sum(len(v) for v in boxes_by_image.values())}")

    locs = collections.Counter(images_by_id[i]["location"] for i in pig_image_ids)
    print(f"locations with pig: {len(locs)}")

    buckets = collections.defaultdict(list)
    for iid in pig_image_ids:
        im = images_by_id[iid]
        bucket = hour_bucket(im.get("datetime"))
        buckets[(im["location"], bucket)].append(iid)

    print("hour-of-day histogram:")
    hour_hist = collections.Counter()
    for iid in pig_image_ids:
        dt = images_by_id[iid].get("datetime")
        if dt:
            try:
                hour_hist[int(dt.split(" ")[1].split(":")[0])] += 1
            except (IndexError, ValueError):
                pass
    for h in range(24):
        print(f"  {h:02d}:00  {hour_hist.get(h, 0)}")

    # Stratified seeded sample: draw from every (location, day/night) cell
    # that has at least one image, up to a per-cell cap, so the audit covers
    # the real spread of locations and day/night rather than whatever the
    # busiest single location happens to dominate.
    seed = 20260912
    rng = random.Random(seed)
    PER_CELL_CAP = 3
    sample_ids = []
    for key in sorted(buckets, key=lambda k: (k[0], k[1] or "")):
        cell = buckets[key]
        sample_ids.extend(rng.sample(cell, min(PER_CELL_CAP, len(cell))))
    print(f"stratified sample size: {len(sample_ids)} "
          f"across {len(buckets)} (location, day/night) cells")

    os.makedirs(OUT_DIR, exist_ok=True)
    records = []
    skipped = []
    for iid in sample_ids:
        im = images_by_id[iid]
        try:
            local = fetch_image(im["file_name"])
        except urllib.error.HTTPError as exc:
            skipped.append((im["file_name"], exc.code))
            continue
        boxes = [(round(x), round(y), round(w), round(h)) for x, y, w, h in boxes_by_image[iid]]
        records.append({
            "name": f"{im['location']}/{im['datetime']}/{os.path.basename(im['file_name'])}",
            "path": local,
            "boxes": boxes,
        })
    if skipped:
        print(f"skipped {len(skipped)} images that 404'd on the GCS bucket:")
        for fn, code in skipped:
            print(f"  {code} {fn}")

    for i in range(0, len(records), 15):
        chunk = records[i : i + 15]
        sheet_path = os.path.join(OUT_DIR, f"ic_pig_{i:03d}.png")
        contact_sheet(chunk, sheet_path)
        with open(os.path.join(OUT_DIR, f"ic_pig_{i:03d}.json"), "w") as fh:
            json.dump([r["name"] for r in chunk], fh, indent=2)


if __name__ == "__main__":
    main()
