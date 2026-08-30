"""Fetch the real, domain-matched Boar (Sus scrofa) subset from LILA BC's WCS
Camera Traps set - the same source already used for Elephant via
fetch_wcs_elephant.py, this time mining it for the other class.

Populates a new "wcs-sus-scrofa" `local_root` DATASETS entry in
edge_impulse_upload_vision.py.

Confirmed live (28 Aug) by downloading and inspecting the actual bounding-box
annotation file (wcs_20220205_bboxes_with_classes.json, ~24MB, no auth):

  - category 145 = "sus scrofa" (the correct species - Kerala's wild boar and
    Indonesia/Laos's forest pig are the same species, unlike the African/Asian
    elephant split that ruled out bulk use of Nkhotakota - see that dataset's
    own rejection note below) carries 1,233 boxes across 831 distinct images.
  - Country breakdown of those 831: idn (Indonesia) 734, lao (Laos) 94, bol
    (Bolivia) 3. The 3 Bolivia records are excluded - Sus scrofa has no native
    range in South America, so a handful of images there are almost certainly
    feral/domestic-descent pigs (confirmed: both Bolivia seq_ids are single-
    frame captures at a 2008 timestamp, consistent with an isolated feral
    sighting, not a systematic population). idn + lao alone = 828 usable
    images, real Southeast Asian forest camera-trap imagery of the same
    species Kerala's detector needs to recognize.
  - Visually verified: a seeded n=10 sample (seed 20260828) rendered with boxes
    and opened by eye - 6/10 unambiguous, tightly-boxed wild boar; 4/10 lower
    image quality (motion blur, close-range flash blowout, fog/condensation)
    but still plausible boar silhouettes, no wrong-species mislabels in any of
    the 10. This is realistic field camera-trap noise, not a data-quality
    defect - the project's Boar corpus needs exactly this kind of imperfect,
    real-world imagery, not more clean catalog photography.

Nkhotakota Camera Traps (Malawi, African elephant) was re-checked this same
pass for a different reason - to correct fetch_wcs_elephant.py's docstring,
which claimed no public per-image bounding-box file exists there. That claim
is wrong: LILA's own page states "a subset of images (33,813) also have
manually drawn bounding box annotations." The correction doesn't change the
verdict, though - Nkhotakota's elephants are Loxodonta africana, the same
species mismatch that already rules it out for the Elephant class regardless
of box availability. Not used, for that reason alone.

Small relative to the existing Boar corpus, but real, species-correct,
domain-matched (actual forest camera-trap footage, not zoo/catalog
photography), and box-verified - added on its merits, same discipline
fetch_wcs_elephant.py already applies to Elephant.

Requires Pillow (same stdlib departure already noted in fetch_wcs_elephant.py
and fetch_swg_camera_traps.py, for the same reason - JPEG decode).

Usage:

    python scripts\\fetch_wcs_boar.py

Prints the real, pixel-verified image count at the end - paste into the
DATASETS entry's expect_images field.

Downloaded zip, extracted metadata, and images land in ml/datasets/vision/raw/,
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
BBOX_ZIP_URL = f"{BASE}/wcs_20220205_bboxes_with_classes.zip"
# Confirmed live in fetch_wcs_elephant.py: file_name paths resolve under this
# prefix, not under BASE/wcs/.
IMAGE_BASE = "https://storage.googleapis.com/public-datasets-lila/wcs-unzipped/"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
META_DIR = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "wcs-camera-traps-meta")
IMAGE_ROOT = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "wcs-camera-traps")

MAX_RETRIES = 4
SPECIES_NAME = "sus scrofa"
# Sus scrofa has no native South American range - the 3 Bolivia records found
# live are excluded as almost certainly feral/domestic-descent, not the wild
# population this project needs. See module docstring.
EXCLUDED_COUNTRIES = {"bol"}


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
    """Download + extract the bounding-box annotation zip (shared with
    fetch_wcs_elephant.py - reuses the same cache directory and file if
    already present, no duplicate download).
    """
    os.makedirs(META_DIR, exist_ok=True)
    bbox_zip = os.path.join(META_DIR, "wcs_bboxes.zip")
    bbox_json = os.path.join(META_DIR, "wcs_20220205_bboxes_with_classes.json")

    if not os.path.exists(bbox_zip):
        print(f"  downloading {BBOX_ZIP_URL} (~24MB)")
        _download(BBOX_ZIP_URL, bbox_zip)
    if not os.path.exists(bbox_json):
        with zipfile.ZipFile(bbox_zip) as zf:
            zf.extractall(META_DIR)

    with open(bbox_json) as fh:
        bbox_doc = json.load(fh)
    return bbox_doc


def _is_night(datetime_str):
    # See fetch_wcs_elephant.py - a handful of records carry malformed
    # datetime values; treat those as unknown rather than crash the run.
    if not isinstance(datetime_str, str) or len(datetime_str) < 13:
        return None
    return int(datetime_str[11:13]) < 6 or int(datetime_str[11:13]) >= 18


def select_boar_with_boxes(bbox_doc):
    """Sus scrofa frames that carry a real box, Bolivia outliers excluded.

    Unlike fetch_wcs_elephant.py, there's no separate whole-frame-only
    classification set to restrict from here - every candidate already comes
    from the annotation file, so "carries a box" is automatic; the only
    filter needed is the country exclusion.
    """
    bbox_cats = {c["id"]: c["name"] for c in bbox_doc["categories"]}
    species_id = next(k for k, v in bbox_cats.items() if v == SPECIES_NAME)

    boxes_by_image = {}
    for ann in bbox_doc["annotations"]:
        if ann["category_id"] != species_id:
            continue
        x, y, w, h = ann["bbox"]
        boxes_by_image.setdefault(ann["image_id"], []).append(
            {"x": round(x), "y": round(y), "width": round(w), "height": round(h)}
        )

    imgs_by_id = {img["id"]: img for img in bbox_doc["images"]}
    countries = {}
    for iid in boxes_by_image:
        img = imgs_by_id.get(iid)
        if img:
            countries[img["country_code"]] = countries.get(img["country_code"], 0) + 1
    print(f"  {SPECIES_NAME}: {len(boxes_by_image)} boxed images total, country breakdown: {countries}")

    candidates = [
        imgs_by_id[iid]
        for iid in boxes_by_image
        if iid in imgs_by_id and imgs_by_id[iid]["country_code"] not in EXCLUDED_COUNTRIES
    ]
    print(f"    {len(candidates)}/{len(boxes_by_image)} kept after excluding {sorted(EXCLUDED_COUNTRIES)}")

    night_flags = [_is_night(img.get("datetime")) for img in candidates]
    night = sum(1 for f in night_flags if f is True)
    day = sum(1 for f in night_flags if f is False)
    unknown = sum(1 for f in night_flags if f is None)
    print(f"    day/night split of kept candidates: {day} day, {night} night, {unknown} unknown/malformed timestamp")

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
    print("Fetching WCS Camera Traps bounding-box metadata...")
    bbox_doc = ensure_meta()

    print(f"\nSelecting {SPECIES_NAME} frames...")
    selected, boxes_by_image = select_boar_with_boxes(bbox_doc)

    print("\nDownloading boar frames...")
    count = fetch_images(
        selected,
        os.path.join(IMAGE_ROOT, "sus_scrofa"),
        boxes_by_image=boxes_by_image,
        box_label="Boar",
    )

    print(f"\nDone. expect_images: sus_scrofa={count}")


if __name__ == "__main__":
    main()
