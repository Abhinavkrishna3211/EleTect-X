"""Fetch a Boar domain-match + true-negative subset from LILA BC's SWG Camera Traps set.

Populates the two `local_root` DATASETS entries in edge_impulse_upload_vision.py
that scripts/edge_impulse_upload_vision.py cannot fill itself:

  - "Boar" / swg-eurasian-wild-pig: Eurasian Wild Pig (Sus scrofa) frames - the
    same species as Kerala's wild boar, real forest camera-trap imagery. A far
    closer domain match than the current catalog-photography Boar sources.
  - "Background" / swg-empty: real camera-trap blanks, day and IR-lit night,
    for the true-negative / false-positive-rate measurement the current corpus
    cannot support (every existing image contains its target class).

Source: the Saola Working Group's "Northern and Central Annamites Camera Traps
2.0" (Vietnam/Laos), published on LILA BC under the misleading short name
"SWG Camera Traps". CDLA-Permissive-2.0, hosted on GCS, no auth needed.
https://storage.googleapis.com/public-datasets-lila/swg-camera-traps/

3a-adjacent finding worth recording plainly: this dataset has NO elephant
category among its 120 species (confirmed against the full category list) - it
helps Boar and the true-negative gap only, not the Elephant species-correctness
gap that Phase 4 addresses separately via Roboflow's Asian-elephant sources.

Real-box coverage finding: the classification file labels 234,736 images
eurasian_wild_pig, but only 12,529 of those (5.3%) have an actual bounding box
in the companion bbox_species file - the rest are whole-frame classification
labels only, no box geometry. A whole-image "Boar" record with zero boxes would
train FOMO to treat a frame that DOES contain a pig as background, which is
worse than not adding the source at all. So the pig selection pool here is
deliberately restricted to the 12,529 real-box images, not the full 234,736 -
see select() below. The empty/background pool needs no boxes and draws from
the full 264,755-image empty category.

Day/night split: the dataset carries no explicit day/night flag, so it is
derived from each image's own recorded capture hour (image["datetime"], stored
as local camera time, no real timezone conversion applied by the recorder):
night = hour < 6 or hour >= 18, a tropical Vietnam/Laos dawn/dusk boundary.
This is a documented judgment call, not a value taken from the dataset itself.

Selection is group-aware (one representative image per seq_id, LILA's own
burst/sequence grouping) so near-identical consecutive frames from one trigger
event cannot dominate the sample, then seeded-shuffled and capped at
TARGET_PER_PERIOD per day/night per category (up to 2*TARGET_PER_PERIOD images
per category total, less if a pool runs out first).
Only "public/"-prefixed file paths are considered - a direct-download check
(curl -sI) found "private/"-prefixed paths 404 with no notice on the dataset
page; this excludes a negligible fraction of each pool (26 of 237,353 for pig,
0 for empty).

Each downloaded image is opened and fully decoded with Pillow before being
counted - a file that downloaded but won't decode is not silently included.
Requires Pillow (already present on this machine for make_pseudo_ir_vision.py's
JPEG work; noted here as the same deliberate departure from the stdlib-only
convention most of this repo's scripts follow).

Writes a Roboflow-shaped `_annotations.coco.json` next to the images in each
category folder, so scripts/edge_impulse_upload_vision.py's existing
parse_coco() reads a `local_root` source exactly like a Roboflow export - no
special-casing needed on the upload side.

Usage (run from a machine with normal internet access):

    python scripts\\fetch_swg_camera_traps.py

Prints the real, pixel-verified image count for each category at the end -
paste those into the DATASETS entries' expect_images fields.

Downloaded zips, extracted metadata, and images land in
ml/datasets/vision/raw/, already gitignored.
"""

import json
import os
import random
import time
import urllib.error
import urllib.request
import zipfile

from PIL import Image

BASE = "https://storage.googleapis.com/public-datasets-lila/swg-camera-traps"
CLASS_ZIP_URL = f"{BASE}/swg_camera_traps.zip"
BBOX_ZIP_URL = f"{BASE}/swg_camera_traps.bounding_boxes.with_species.zip"
IMAGE_BASE = f"{BASE}/"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
META_DIR = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "swg-camera-traps-meta")
IMAGE_ROOT = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "swg-camera-traps")

SEED = 20260822
# Raised from 300 (27 Aug baseline: 550 boar / 630 empty already live in project
# 1097972) to spend more of the real, domain-matched pool the first pass left
# unused - pig-with-boxes candidates cap out around 12.5k images (a few
# thousand seq_id groups after burst dedup) and empty at 264,755, so 1200/period
# stays well inside both pools' real headroom rather than approaching either
# ceiling. Same SEED means the previously-selected 550/630 stay a strict
# prefix of the larger draw (day_groups[:300] subset of day_groups[:1200]) -
# nothing already downloaded or already uploaded is invalidated by this bump.
TARGET_PER_PERIOD = 1200  # day + night -> up to 2400 images per category
MAX_RETRIES = 4


def _is_night(datetime_str):
    return int(datetime_str[11:13]) < 6 or int(datetime_str[11:13]) >= 18


def _download(url, path):
    for attempt in range(MAX_RETRIES):
        try:
            urllib.request.urlretrieve(url, path)
            return
        except (urllib.error.URLError, OSError) as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"    retry {attempt + 1}/{MAX_RETRIES} after {exc} - waiting {wait}s")
            time.sleep(wait)


def ensure_meta():
    """Download + extract the two annotation zips, reusing them if already present."""
    os.makedirs(META_DIR, exist_ok=True)
    class_zip = os.path.join(META_DIR, "swg_camera_traps.zip")
    bbox_zip = os.path.join(META_DIR, "swg_camera_traps.bounding_boxes.with_species.zip")
    class_dir = os.path.join(META_DIR, "class_level")
    bbox_dir = os.path.join(META_DIR, "bbox_species")

    if not os.path.exists(class_zip):
        print(f"  downloading {CLASS_ZIP_URL}")
        _download(CLASS_ZIP_URL, class_zip)
    if not os.path.isdir(class_dir):
        with zipfile.ZipFile(class_zip) as zf:
            zf.extractall(class_dir)

    if not os.path.exists(bbox_zip):
        print(f"  downloading {BBOX_ZIP_URL}")
        _download(BBOX_ZIP_URL, bbox_zip)
    if not os.path.isdir(bbox_dir):
        with zipfile.ZipFile(bbox_zip) as zf:
            zf.extractall(bbox_dir)

    class_json = next(
        os.path.join(class_dir, f) for f in os.listdir(class_dir) if f.endswith(".json")
    )
    bbox_json = next(
        os.path.join(bbox_dir, f) for f in os.listdir(bbox_dir) if f.endswith(".json")
    )
    with open(class_json) as fh:
        class_doc = json.load(fh)
    with open(bbox_json) as fh:
        bbox_doc = json.load(fh)
    return class_doc, bbox_doc


def check_elephant_absent(class_doc):
    names = [c["name"] for c in class_doc["categories"]]
    hits = [n for n in names if "eleph" in n.lower()]
    print(f"  species check: elephant category present? {'YES: ' + str(hits) if hits else 'NO'}")
    return hits


def select_pig_with_boxes(class_doc, bbox_doc, target_per_period=TARGET_PER_PERIOD, seed=SEED):
    """Pig frames restricted to the subset that carries a real bounding box.

    See module docstring: only 12,529 of 234,736 classified pig images have one.
    An image without a real box would be a mislabeled background record, not a
    Boar detection example, so it is excluded rather than uploaded weakly.
    """
    class_cats = {c["id"]: c["name"] for c in class_doc["categories"]}
    pig_class_id = next(k for k, v in class_cats.items() if v == "eurasian_wild_pig")
    bbox_cats = {c["id"]: c["name"] for c in bbox_doc["categories"]}
    pig_bbox_id = next(k for k, v in bbox_cats.items() if v == "eurasian_wild_pig")

    boxes_by_image = {}
    for ann in bbox_doc["annotations"]:
        if ann["category_id"] != pig_bbox_id:
            continue
        x, y, w, h = ann["bbox"]
        boxes_by_image.setdefault(ann["image_id"], []).append(
            {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}
        )

    class_by_image = {}
    for ann in class_doc["annotations"]:
        if ann["category_id"] == pig_class_id:
            class_by_image[ann["image_id"]] = True

    images = class_doc["images"]
    candidates = [
        img
        for img in images
        if class_by_image.get(img["id"])
        and img["id"] in boxes_by_image
        and img["file_name"].startswith("public/")
        and not img.get("corrupt")
    ]
    print(
        f"  pig: {len(candidates)} candidates (public, non-corrupt, real box present) "
        f"out of {len(class_by_image)} classified eurasian_wild_pig images"
    )
    selected = _select_by_group(candidates, target_per_period, seed)
    return selected, boxes_by_image


def select_empty(class_doc, target_per_period=TARGET_PER_PERIOD, seed=SEED):
    class_cats = {c["id"]: c["name"] for c in class_doc["categories"]}
    empty_id = next(k for k, v in class_cats.items() if v == "empty")
    class_by_image = {}
    for ann in class_doc["annotations"]:
        if ann["category_id"] == empty_id:
            class_by_image[ann["image_id"]] = True

    images = class_doc["images"]
    candidates = [
        img
        for img in images
        if class_by_image.get(img["id"])
        and img["file_name"].startswith("public/")
        and not img.get("corrupt")
    ]
    print(f"  empty: {len(candidates)} candidates (public, non-corrupt)")
    return _select_by_group(candidates, target_per_period, seed)


def _select_by_group(candidates, target_per_period, seed):
    """One representative image per seq_id, day/night balanced, seeded shuffle."""
    groups = {}
    for img in candidates:
        groups.setdefault(img["seq_id"], []).append(img)

    day_groups, night_groups = [], []
    for imgs in groups.values():
        rep = min(imgs, key=lambda i: i["id"])
        (night_groups if _is_night(rep["datetime"]) else day_groups).append(rep)

    day_groups.sort(key=lambda i: i["id"])
    night_groups.sort(key=lambda i: i["id"])
    random.Random(seed).shuffle(day_groups)
    random.Random(seed).shuffle(night_groups)

    day_pick = day_groups[:target_per_period]
    night_pick = night_groups[:target_per_period]
    print(
        f"    {len(day_groups)} day groups -> {len(day_pick)} selected, "
        f"{len(night_groups)} night groups -> {len(night_pick)} selected"
    )
    if len(day_pick) < target_per_period or len(night_pick) < target_per_period:
        print(
            f"    NOTE: target {target_per_period}/period not reached for at least one period"
        )
    return day_pick + night_pick


def fetch_images(selected, out_dir, boxes_by_image=None, box_label=None):
    """Download + pixel-verify each selected image, write its coco annotation entry."""
    os.makedirs(out_dir, exist_ok=True)
    coco_images, coco_annotations = [], []
    failures = []
    next_ann_id = 1

    for i, img in enumerate(selected, 1):
        dest = os.path.join(out_dir, f"{img['id']}.jpg")
        if not os.path.exists(dest):
            url = IMAGE_BASE + img["file_name"]
            try:
                _download(url, dest)
            except (urllib.error.URLError, OSError) as exc:
                print(f"    FAILED download {img['file_name']}: {exc}")
                failures.append({"id": img["id"], "file_name": img["file_name"], "error": str(exc)})
                continue

        try:
            with Image.open(dest) as im:
                im.load()
                width, height = im.size
        except Exception as exc:  # noqa: BLE001 - any decode failure disqualifies the file
            print(f"    FAILED decode {img['file_name']}: {exc}")
            failures.append({"id": img["id"], "file_name": img["file_name"], "error": str(exc)})
            os.remove(dest)
            continue

        coco_images.append(
            {"id": img["id"], "file_name": f"{img['id']}.jpg", "width": width, "height": height}
        )
        if boxes_by_image is not None:
            for box in boxes_by_image.get(img["id"], []):
                coco_annotations.append(
                    {
                        "id": next_ann_id,
                        "image_id": img["id"],
                        "category_id": 1,
                        "bbox": [box["x"], box["y"], box["width"], box["height"]],
                    }
                )
                next_ann_id += 1

        if i % 100 == 0:
            print(f"    {i}/{len(selected)} processed")

    categories = [{"id": 1, "name": box_label}] if box_label else []
    doc = {"images": coco_images, "annotations": coco_annotations, "categories": categories}
    with open(os.path.join(out_dir, "_annotations.coco.json"), "w") as fh:
        json.dump(doc, fh)

    if failures:
        with open(os.path.join(out_dir, "failed.json"), "w") as fh:
            json.dump(failures, fh, indent=2)
        print(f"    {len(failures)} failures recorded in {out_dir}/failed.json")

    return len(coco_images)


def main():
    print("Fetching SWG Camera Traps metadata...")
    class_doc, bbox_doc = ensure_meta()
    check_elephant_absent(class_doc)

    print("\nSelecting pig frames (real-box subset only)...")
    pig_selected, boxes_by_image = select_pig_with_boxes(class_doc, bbox_doc)
    print("\nDownloading pig frames...")
    pig_count = fetch_images(
        pig_selected,
        os.path.join(IMAGE_ROOT, "eurasian_wild_pig"),
        boxes_by_image=boxes_by_image,
        box_label="Boar",
    )

    print("\nSelecting empty (background) frames...")
    empty_selected = select_empty(class_doc)
    print("\nDownloading empty frames...")
    empty_count = fetch_images(empty_selected, os.path.join(IMAGE_ROOT, "empty"))

    print(f"\nDone. expect_images: eurasian_wild_pig={pig_count}, empty={empty_count}")


if __name__ == "__main__":
    main()
