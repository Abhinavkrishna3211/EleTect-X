"""Fetch the real, species-correct Elephant (Asian) subset from LILA BC's WCS Camera Traps set.

Populates the "wcs-elephas-maximus" `local_root` DATASETS entry in
edge_impulse_upload_vision.py. Direct answer to the question "is adding African
elephant image data to the training set a good idea": checked WCS Camera Traps
(1.37M images, 12 countries, CDLA-Permissive-1.0, GCS-hosted, no auth) first for
a real Asian-elephant source before considering any African supplement.

Confirmed live (28 Aug) by downloading and inspecting the actual metadata:

  - Species list (wcs_specieslist.csv): "elephas maximus" (Asian elephant, the
    correct species for Kerala) = 325 annotated images. All 325 are country_code
    "idn" (Indonesia) - real tropical-forest camera-trap imagery, not zoo/catalog
    photography and not African savanna. A genuine domain-match improvement over
    the existing catalog-photography Elephant sources, same logic already applied
    to Boar via fetch_swg_camera_traps.py's SWG pull.
  - Bounding boxes (wcs_20220205_bboxes_with_classes.json): 194 of the 325 (60%)
    carry a real "elephas maximus" box. Restricted to those 194, same reasoning
    fetch_swg_camera_traps.py already documents for pig: a whole-frame label with
    no box geometry teaches a detector that a frame containing the animal is
    background, which is worse than not adding the source.
  - Real night coverage: capture hour (local camera time, no timezone conversion,
    from each image's own recorded datetime) spans a genuine spread across
    0-5 and 19-23, not a token few - printed per-run below, matches this
    project's stated night-priority deployment.

African-elephant sources (checked, not used): LILA's Nkhotakota Camera Traps has
10,664 African elephant images. (Correction, 28 Aug: an earlier pass here claimed
no public per-image bounding-box file exists for this set - that was wrong. LILA's
own page states a subset of 33,813 images across the full set does carry manually
drawn bounding boxes. Re-checked directly on the live page, not taken on faith.)
The box question turns out not to matter, because the disqualifier was never box
availability - it's species. African and Asian elephants differ enough
morphologically (ear size/shape, back profile, forehead) that bulk African
training data risks teaching the wrong gestalt for a recall-critical Kerala
detector rather than reinforcing the right one. Not pursued further - see the
DATASETS entry's own comment for the full reasoning.

Small (194 images) but real, species-correct, domain-matched, and box-verified -
added on its merits, not as a volume play; the structural Elephant-recall lever
stays dataset breadth + architecture search, not this alone.

Requires Pillow (same departure from the stdlib-only convention already noted in
fetch_swg_camera_traps.py, for the same reason - JPEG decode).

Usage:

    python scripts\\fetch_wcs_elephant.py

Prints the real, pixel-verified image count at the end - paste into the
DATASETS entry's expect_images field.

Downloaded zips, extracted metadata, and images land in ml/datasets/vision/raw/,
already gitignored.
"""

import json
import os
import time
import urllib.error
import urllib.request
import zipfile

from PIL import Image

BASE = "https://storage.googleapis.com/public-datasets-lila/wcs"
SPECIES_URL = f"{BASE}/wcs_specieslist.csv"
CLASS_ZIP_URL = f"{BASE}/wcs_camera_traps.json.zip"
BBOX_ZIP_URL = f"{BASE}/wcs_20220205_bboxes_with_classes.zip"
# Confirmed live: the metadata's file_name paths (e.g. "animals/0036/0493.jpg")
# resolve under this prefix, NOT under BASE/wcs/ - a direct 404 check ruled that
# out first.
IMAGE_BASE = "https://storage.googleapis.com/public-datasets-lila/wcs-unzipped/"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
META_DIR = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "wcs-camera-traps-meta")
IMAGE_ROOT = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "wcs-camera-traps")

MAX_RETRIES = 4
SPECIES_NAME = "elephas maximus"


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
    """Download + extract the species list and both annotation zips."""
    os.makedirs(META_DIR, exist_ok=True)
    species_csv = os.path.join(META_DIR, "wcs_specieslist.csv")
    class_zip = os.path.join(META_DIR, "wcs_camera_traps.json.zip")
    bbox_zip = os.path.join(META_DIR, "wcs_bboxes.zip")
    class_json = os.path.join(META_DIR, "wcs_camera_traps.json")
    bbox_json = os.path.join(META_DIR, "wcs_20220205_bboxes_with_classes.json")

    if not os.path.exists(species_csv):
        print(f"  downloading {SPECIES_URL}")
        _download(SPECIES_URL, species_csv)

    if not os.path.exists(class_zip):
        print(f"  downloading {CLASS_ZIP_URL} (~45MB)")
        _download(CLASS_ZIP_URL, class_zip)
    if not os.path.exists(class_json):
        with zipfile.ZipFile(class_zip) as zf:
            zf.extractall(META_DIR)

    if not os.path.exists(bbox_zip):
        print(f"  downloading {BBOX_ZIP_URL} (~24MB)")
        _download(BBOX_ZIP_URL, bbox_zip)
    if not os.path.exists(bbox_json):
        with zipfile.ZipFile(bbox_zip) as zf:
            zf.extractall(META_DIR)

    with open(class_json) as fh:
        class_doc = json.load(fh)
    with open(bbox_json) as fh:
        bbox_doc = json.load(fh)
    return class_doc, bbox_doc


def _is_night(datetime_str):
    # A handful of this dataset's "datetime" values are not well-formed strings
    # (found live: at least one float, presumably a parse artifact upstream in
    # LILA's own metadata) - treat those as unknown rather than crash the run.
    if not isinstance(datetime_str, str) or len(datetime_str) < 13:
        return None
    return int(datetime_str[11:13]) < 6 or int(datetime_str[11:13]) >= 18


def select_elephant_with_boxes(class_doc, bbox_doc):
    """Elephas maximus frames restricted to the subset that carries a real box.

    See module docstring: only 194 of 325 classified elephas maximus images have
    one. A whole-image record with zero boxes would train the detector to treat
    a frame that DOES contain an elephant as background - excluded, same
    discipline fetch_swg_camera_traps.py applies to pig.
    """
    class_cats = {c["id"]: c["name"] for c in class_doc["categories"]}
    class_species_id = next(k for k, v in class_cats.items() if v == SPECIES_NAME)
    bbox_cats = {c["id"]: c["name"] for c in bbox_doc["categories"]}
    bbox_species_id = next(k for k, v in bbox_cats.items() if v == SPECIES_NAME)

    boxes_by_image = {}
    for ann in bbox_doc["annotations"]:
        if ann["category_id"] != bbox_species_id:
            continue
        x, y, w, h = ann["bbox"]
        boxes_by_image.setdefault(ann["image_id"], []).append(
            {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}
        )

    class_img_ids = {a["image_id"] for a in class_doc["annotations"] if a["category_id"] == class_species_id}
    print(f"  {SPECIES_NAME}: {len(class_img_ids)} classified images total")

    imgs_by_id = {img["id"]: img for img in class_doc["images"]}
    countries = {}
    for iid in class_img_ids:
        img = imgs_by_id.get(iid)
        if img:
            countries[img["country_code"]] = countries.get(img["country_code"], 0) + 1
    print(f"    country breakdown: {countries}")

    candidates = [imgs_by_id[iid] for iid in class_img_ids if iid in boxes_by_image and iid in imgs_by_id]
    print(f"    {len(candidates)}/{len(class_img_ids)} carry a real bounding box - restricting to those")

    night_flags = [_is_night(img.get("datetime")) for img in candidates]
    night = sum(1 for f in night_flags if f is True)
    day = sum(1 for f in night_flags if f is False)
    unknown = sum(1 for f in night_flags if f is None)
    print(f"    day/night split of boxed candidates: {day} day, {night} night, {unknown} unknown/malformed timestamp")

    return candidates, boxes_by_image


def fetch_images(selected, out_dir, boxes_by_image, box_label):
    """Download + pixel-verify each selected image, write its coco annotation entry."""
    os.makedirs(out_dir, exist_ok=True)
    coco_images, coco_annotations = [], []
    failures = []
    next_ann_id = 1

    for i, img in enumerate(selected, 1):
        safe_name = img["id"].replace("/", "_")
        dest = os.path.join(out_dir, f"{safe_name}.jpg")
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

        coco_images.append({"id": img["id"], "file_name": f"{safe_name}.jpg", "width": width, "height": height})
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

        if i % 50 == 0:
            print(f"    {i}/{len(selected)} processed")

    doc = {"images": coco_images, "annotations": coco_annotations, "categories": [{"id": 1, "name": box_label}]}
    with open(os.path.join(out_dir, "_annotations.coco.json"), "w") as fh:
        json.dump(doc, fh)

    if failures:
        with open(os.path.join(out_dir, "failed.json"), "w") as fh:
            json.dump(failures, fh, indent=2)
        print(f"    {len(failures)} failures recorded in {out_dir}/failed.json")

    return len(coco_images)


def main():
    print("Fetching WCS Camera Traps metadata...")
    class_doc, bbox_doc = ensure_meta()

    print(f"\nSelecting {SPECIES_NAME} frames (real-box subset only)...")
    selected, boxes_by_image = select_elephant_with_boxes(class_doc, bbox_doc)

    print("\nDownloading elephant frames...")
    count = fetch_images(
        selected,
        os.path.join(IMAGE_ROOT, "elephas_maximus"),
        boxes_by_image=boxes_by_image,
        box_label="Elephant",
    )

    print(f"\nDone. expect_images: elephas_maximus={count}")


if __name__ == "__main__":
    main()
