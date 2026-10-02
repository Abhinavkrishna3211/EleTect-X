"""Build the board-captures-fox-encounter1 source from the real 11 Sept fox/jackal
encounter recorded on the deployed camera (see docs/KNOWN_GAPS.md, encounter
20260911T203127 - "non-target-species false-species-attribution").

Source: device/mpu/bench/camera_check/fox_encounter_20260911T203127/ - 1,715 raw
IR-night JPEG frames (1920x1080, ~11.5fps) plus detections_windowed.jsonl, the
model's own 36-record box track for the encounter. The track was produced by
the *currently deployed* two-class (Elephant/Boar) impulse, so every record
carries label "Boar" - that is the misidentification this source exists to fix,
not a fact about the animal. Frame review identified the animal as a fox or
golden jackal by gait, build, and snout shape; see KNOWN_GAPS for the full
description. This script does not re-derive that identification - it is taken
as given, the same way every other DATASETS source's label is taken from its
provenance rather than re-verified here.

The 36 raw detection records over-sample a track that visits only ~14 distinct
saved frames at ~11.5fps (many records share one frame; consecutive records a
few hundred ms apart often round to the same on-disk JPEG). This script:

  1. Re-derives the frame<->detection nearest-timestamp pairing (bisect on the
     JPEG filename's embedded wall-clock float vs each record's wall_s).
  2. Keeps one representative frame per distinct match, in temporal order.
  3. Drops any frame where the fox is not visibly present at the reported box
     on by-eye inspection, rather than uploading a box the image does not
     support - the same standing rule boar-representation-audit.md applies to
     every other source. One frame (00142500, the JSONL's final record, conf
     0.52) was dropped on this basis: nothing resembling an animal is visible
     in that exact frame despite the nonzero reported confidence, most likely
     because the true detection instant falls in the gap between two saved
     frames larger than usual. See fox-representation-audit.md point 1 for the
     full by-eye walkthrough of all 14 candidate frames.
  4. Relabels every kept box "Fox" (the detector's own boxes correctly
     localize the animal in every kept frame - confirmed by eye per candidate
     frame - only the species label was wrong) and writes a Roboflow-shaped
     _annotations.coco.json next to the copied images, exactly like every
     other local_root source edge_impulse_upload_vision.py's parse_coco()
     reads.

Filenames use one session prefix, "fx1_burst_<NN>.jpg", so
edge_impulse_upload_vision.py's group_key() collapses the entire encounter
(11 main-track frames spanning ~13s, plus 2 frames from a second brief
appearance ~31-34s later - the fox doubling back through the same gap) into a
single group. That is deliberate, not an oversight: this is one continuous
sighting of one individual against one fixed background, and splitting it
across train/test would leak the exact scene the eval is meant to test
against. The whole group lands on one side of the seeded train/test split.

Box coordinates are kept as EI reported them (x, y = top-left, matching
device/mpu/perception/detector.py's own reading of the classify API's
bounding_boxes shape) after by-eye confirmation that the box contains the
animal in each kept frame. No bounding-box annotation tool was available for
this pass, so tightening is not pixel-exact the way a hand-drawn box would
be - flagged plainly in fox-representation-audit.md rather than claimed as
precise. This mirrors board-captures-night1/day1's zero-box convention except
these are real boxes, not Background.

Usage (no network access, no arguments - the frame list and boxes are fixed
findings from the by-eye audit, not re-derived at run time):

    python scripts/build_fox_encounter1_vision.py

Writes into ml/datasets/vision/raw/board-captures-fox-encounter1/images/
(gitignored). Prints the final image + box count - paste into the
board-captures-fox-encounter1 DATASETS entry's expect_images/page_boxes.
"""

import json
import os
import shutil

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
SRC_DIR = os.path.join(
    _ROOT, "device", "mpu", "bench", "camera_check", "fox_encounter_20260911T203127"
)
OUT_DIR = os.path.join(
    _ROOT, "ml", "datasets", "vision", "raw", "board-captures-fox-encounter1", "images"
)

# (source filename, box [x, y, w, h]) - box is the nearest detections_windowed.jsonl
# record's box for that frame, re-derived by nearest wall_s match and confirmed by
# eye to contain the animal. Temporal order; frames 00-10 are the main ~13s track,
# 11-12 are the fox's brief return ~31-34s later (see docstring).
KEPT_FRAMES = [
    ("01789158676.598374_00141863.jpg", [1420.0, 472.5, 280.0, 168.75]),
    ("01789158677.608560_00141875.jpg", [1420.0, 438.75, 280.0, 281.25]),
    ("01789158680.586724_00141910.jpg", [1200.0, 517.5, 280.0, 202.5]),
    ("01789158681.604573_00141922.jpg", [1140.0, 551.25, 280.0, 168.75]),
    ("01789158682.536782_00141933.jpg", [980.0, 551.25, 440.0, 202.5]),
    ("01789158683.734364_00141947.jpg", [920.0, 551.25, 420.0, 247.5]),
    ("01789158684.585332_00141957.jpg", [1060.0, 551.25, 280.0, 168.75]),
    ("01789158685.599773_00141969.jpg", [920.0, 551.25, 280.0, 281.25]),
    ("01789158686.622974_00141981.jpg", [920.0, 596.25, 280.0, 315.0]),
    ("01789158687.552125_00141992.jpg", [700.0, 641.25, 440.0, 270.0]),
    ("01789158689.713581_00142017.jpg", [560.0, 675.0, 360.0, 236.25]),
    ("01789158720.535445_00142372.jpg", [560.0, 551.25, 280.0, 202.5]),
    ("01789158730.491470_00142486.jpg", [1200.0, 517.5, 280.0, 157.5]),
]

IMAGE_WIDTH = 1920
IMAGE_HEIGHT = 1080


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    coco_images = []
    coco_annotations = []
    next_ann_id = 1

    for idx, (src_name, box) in enumerate(KEPT_FRAMES):
        src_path = os.path.join(SRC_DIR, src_name)
        if not os.path.exists(src_path):
            raise FileNotFoundError(f"expected source frame missing: {src_path}")

        dest_name = f"fx1_burst_{idx:02d}.jpg"
        dest_path = os.path.join(OUT_DIR, dest_name)
        shutil.copyfile(src_path, dest_path)

        image_id = idx
        coco_images.append(
            {"id": image_id, "file_name": dest_name, "width": IMAGE_WIDTH, "height": IMAGE_HEIGHT}
        )
        x, y, w, h = box
        coco_annotations.append(
            {
                "id": next_ann_id,
                "image_id": image_id,
                "category_id": 1,
                "bbox": [round(x), round(y), round(w), round(h)],
            }
        )
        next_ann_id += 1

    categories = [{"id": 1, "name": "Fox"}]
    doc = {"images": coco_images, "annotations": coco_annotations, "categories": categories}
    with open(os.path.join(OUT_DIR, "_annotations.coco.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh)

    print(f"Copied {len(coco_images)} frames, {len(coco_annotations)} boxes into {OUT_DIR}")
    print(f"expect_images = {len(coco_images)}")
    print(f"page_boxes = {len(coco_annotations)}")
    print("Single group (all frames share the 'fx1_burst' group_key prefix).")


if __name__ == "__main__":
    main()
