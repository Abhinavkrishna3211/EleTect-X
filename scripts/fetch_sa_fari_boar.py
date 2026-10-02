"""Fetch the SA-FARI wild-boar tracklet frames vetted in boar-representation-audit.md.

Source: "SA-FARI: A Large-Scale Multimodal Dataset for Africa Camera Trap Animal
Detection" (Conservation X Labs x Meta, arXiv 2511.15622). Gated on Hugging Face
(facebook/SA-FARI, CC-BY-NC 4.0, licence compatibility already ruled owner-cleared
- see boar-representation-audit.md), but the actual video frames live on a public,
non-gated GCS bucket - only the two annotation JSONs need HF auth.

15 videos carry a real wild-boar/pig masklet (category_id 111 "pig" or 43640
"wild boar", both Sus scrofa per the dataset's own taxonomy - filtered via
video_np_pairs' num_masklets>0, independently re-derived from the raw
annotation JSON and cross-checked against the original by-eye vetting: 7 test-
split videos at campo9/campo4/campo2, 8 train-split videos at campo3/campo5, no
location overlap between the two groups. See sa_fari_boar_positive_videos.json
(built by a one-off inspection pass, not checked in - rebuild it from the raw
annotation JSONs if it goes missing; the manifest shape is documented in
scripts/audit_sa_fari_boar_sample.py's docstring).

Each SA-FARI annotation stores a per-frame bbox list already in COCO [x, y, w,
h] pixel form (aligned 1:1 with the video's file_names list, ~6fps-subsampled) -
no mask decode needed. A None entry means the tracked animal was out of frame /
untracked at that instant and is skipped; two annotations on one video can both
have a box on the same frame (two boars visible together) and both are kept.

Thinning: a boxed tracklet segment holds many near-identical consecutive frames
(a boar ambling through one 6fps-sampled clip). Keeping all ~1,217 raw boxed
frame-instances across 15 videos would load the corpus with heavily-correlated
near-duplicates for a comparatively small number of distinct sightings. Each
video's boxed frame indices are thinned to a stride evenly spaced across the
sighting, capped at MAX_FRAMES_PER_VIDEO, matching this repo's existing
small-real-source scale (user-videos-29aug-boar kept 26 frames from 3 clips).

Group-aware split: filenames encode the camp location (sf_<location>_<compound
id>.jpg, digits run together with no separator between the per-location video
index and the frame index) so scripts/edge_impulse_upload_vision.py's
group_key() collapses ALL frames from ALL videos at one physical camera
location into a single group. That keeps split_by_group()'s seeded train/test
shuffle from ever putting two videos filmed at the same camp (same background,
same fixed angle) on opposite sides of the split - a stronger leakage guard
than per-video grouping alone, and the same boundary the original by-eye vetting
already established (campo9/campo4/campo2 vs campo3/campo5).

Writes a Roboflow-shaped `_annotations.coco.json` next to the images, so
edge_impulse_upload_vision.py's parse_coco() reads this local_root source
exactly like every other one - no special-casing on the upload side.

Usage (run after downloading the two SA-FARI annotation JSONs with HF_TOKEN;
see boar-representation-audit.md for the download command):

    python scripts\\fetch_sa_fari_boar.py --manifest <path to sa_fari_boar_positive_videos.json>

Downloaded images land in ml/datasets/vision/raw/sa-fari-boar/images/, already
gitignored. Prints the real, pixel-verified image + box count at the end -
paste those into the sa-fari-boar DATASETS entry's expect_images/page_boxes.
"""

import argparse
import json
import os
import urllib.error
import urllib.request

from PIL import Image

GCS_BASE = "https://storage.googleapis.com/cxl-public-camera-trap/sa_fari"
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
IMAGE_ROOT = os.path.join(_ROOT, "ml", "datasets", "vision", "raw", "sa-fari-boar")

MAX_FRAMES_PER_VIDEO = 20
BOAR_CATEGORY_IDS = {111, 43640}

# boar-representation-audit.md point 2: 13/15 videos show an unambiguous boar by
# eye; these two show only a faint, small dark shape at long IR range - "not
# confidently distinguishable from any other dark shape at that resolution by
# eye alone." No per-image confidence-weighting mechanism exists in this
# pipeline (every upload path treats a box as an equally strong label), so with
# a zero-miss/near-zero-FP bar the defensible choice is to drop them outright
# rather than upload an ambiguous label as if it were as strong as the other 13.
MARGINAL_VIDEOS = {"sa_fari_000820", "sa_fari_004160"}


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "eletect-x-vision-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp, open(dest, "wb") as fh:
        fh.write(resp.read())


def thinned_frame_indices(n_available, cap=MAX_FRAMES_PER_VIDEO):
    """Evenly-spaced indices into a sorted boxed-frame-index list, capped at `cap`."""
    if n_available <= cap:
        return list(range(n_available))
    stride = n_available / cap
    return sorted({round(i * stride) for i in range(cap)})[:cap]


def collect_frames(manifest):
    """Per video: boxed (frame_idx -> [box, ...]) dict, thinned, keyed by split+video."""
    by_video = []
    for split in ("test", "train"):
        for v in manifest[split]:
            if v["video_name"] in MARGINAL_VIDEOS:
                continue
            boxed = {}
            for ann in v["annotations"]:
                if ann["category_id"] not in BOAR_CATEGORY_IDS:
                    continue
                for idx, box in enumerate(ann["bboxes"]):
                    if box is None:
                        continue
                    boxed.setdefault(idx, []).append(box)
            if not boxed:
                continue
            sorted_idx = sorted(boxed)
            keep_positions = thinned_frame_indices(len(sorted_idx))
            keep_idx = [sorted_idx[p] for p in keep_positions]
            by_video.append({
                "split": split,
                "video_name": v["video_name"],
                "location_id": v["location_id"],
                "file_names": v["file_names"],
                "width": v["width"],
                "height": v["height"],
                "boxed": {idx: boxed[idx] for idx in keep_idx},
            })
    return by_video


def assign_local_video_indices(by_video):
    """Per-location running index, 2 digits, used to keep compound filenames unique."""
    counters = {}
    for entry in by_video:
        loc = entry["location_id"]
        entry["local_video_idx"] = counters.get(loc, 0)
        counters[loc] = counters.get(loc, 0) + 1
    return by_video


def fetch_images(by_video, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    coco_images, coco_annotations = [], []
    failures = []
    next_image_id = 1
    next_ann_id = 1

    for entry in by_video:
        split_dir = "sa_fari_test" if entry["split"] == "test" else "sa_fari_train"
        for frame_idx, boxes in sorted(entry["boxed"].items()):
            rel_path = entry["file_names"][frame_idx]
            url = f"{GCS_BASE}/{split_dir}/JPEGImages_6fps/{rel_path}"
            fname = f"sf_{entry['location_id']}_{entry['local_video_idx']:02d}{frame_idx:05d}.jpg"
            dest = os.path.join(out_dir, fname)

            if not os.path.exists(dest):
                try:
                    _download(url, dest)
                except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
                    print(f"  FAILED download {url}: {exc}")
                    failures.append({"url": url, "error": str(exc)})
                    continue

            try:
                with Image.open(dest) as im:
                    im.load()
                    width, height = im.size
            except Exception as exc:  # noqa: BLE001 - any decode failure disqualifies the file
                print(f"  FAILED decode {fname}: {exc}")
                failures.append({"url": url, "error": str(exc)})
                os.remove(dest)
                continue

            image_id = next_image_id
            next_image_id += 1
            coco_images.append({"id": image_id, "file_name": fname, "width": width, "height": height})
            for box in boxes:
                x, y, w, h = box
                coco_annotations.append({
                    "id": next_ann_id,
                    "image_id": image_id,
                    "category_id": 1,
                    "bbox": [round(x), round(y), round(w), round(h)],
                })
                next_ann_id += 1

    categories = [{"id": 1, "name": "Boar"}]
    doc = {"images": coco_images, "annotations": coco_annotations, "categories": categories}
    with open(os.path.join(out_dir, "_annotations.coco.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    if failures:
        with open(os.path.join(out_dir, "failed.json"), "w", encoding="utf-8") as fh:
            json.dump(failures, fh, indent=2)

    return coco_images, coco_annotations, failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, help="path to sa_fari_boar_positive_videos.json")
    args = parser.parse_args()

    with open(args.manifest, encoding="utf-8") as fh:
        manifest = json.load(fh)

    by_video = collect_frames(manifest)
    by_video = assign_local_video_indices(by_video)

    print(f"{len(by_video)} videos contribute boxed frames after thinning (cap {MAX_FRAMES_PER_VIDEO}/video):")
    total_frames = 0
    for entry in by_video:
        n = len(entry["boxed"])
        total_frames += n
        print(f"  [{entry['split']}] {entry['video_name']} loc={entry['location_id']} -> {n} frames")
    print(f"  {total_frames} total frames to fetch")

    out_dir = os.path.join(IMAGE_ROOT, "images")
    images, annotations, failures = fetch_images(by_video, out_dir)

    print()
    print(f"Fetched {len(images)} images, {len(annotations)} boxes, {len(failures)} failure(s)")
    print(f"expect_images = {len(images)}")
    print(f"page_boxes = {len(annotations)}")
    by_loc = {}
    for entry in by_video:
        by_loc[entry["location_id"]] = by_loc.get(entry["location_id"], 0) + len(entry["boxed"])
    print("Per-location frame counts (= group_key() groups after upload):")
    for loc, n in sorted(by_loc.items()):
        print(f"  {loc}: {n}")


if __name__ == "__main__":
    main()
