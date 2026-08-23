"""Upload real, CC BY 4.0 Roboflow wildlife datasets to Edge Impulse as FOMO training data.

Pulls openly-licensed, bounding-box-annotated datasets straight from Roboflow's
export API, converts their COCO annotations into Edge Impulse's bounding_boxes.labels
ingestion format, and uploads them into the EleTect-X-Vision project:

  - "Elephant": roboflow-universe-projects/elephant-detection-cxnt1, version 2
    ("resized640"), CC BY 4.0. 3,280 images / 4,478 boxes, 640x640.
    Version 2 is used rather than version 4 deliberately: v4 holds the same 3,280
    source images plus a 5x Roboflow augmentation of the train split only (12,460
    total). Those extra frames carry no new information, would put the class ratio
    against boar at 6.6:1 instead of 1.7:1, and Edge Impulse applies its own
    augmentation during FOMO training regardless. v2 is the un-augmented base set.
  - "Boar": trackabox-4ejy9/wild-boar-a1flm, version 1, CC BY 4.0.
    1,901 images / 2,739 boxes, 416x416. Roboflow labels this class "Pig"; the
    dataset is titled "Wild Boar" and its filenames are wild-boar frame captures
    (wb_frames...), so the class is relabeled to "Boar" here rather than carrying
    the misleading name into this project. The project also carries a stray,
    zero-annotation category literally named "`" - it is dropped, and counted.
  - "Boar" (top-up): boarwatch/wild-boar-deterrent-pzq5t, version 1, CC BY 4.0.
    8,857 images / 13,894 boxes, 416x416, class "0" renamed to "Boar". Added to close
    the instance gap against Elephant (stock FOMO knobs - resolution, cycles, class
    weighting, augmentation - are exhausted; see ml/vision/README.md's iteration
    log). A byte-identical fork of this same 8,857-image dataset is also listed as
    deepanshu-thapa-bgz3j/wild-boar-deterrent; only the boarwatch listing is used,
    so the same photos are never counted twice under two names.
    Its filenames collapse to only 2,483 real groups behind the 8,857 images (most
    of the "extra" images are re-exports of the same source photo at a second
    resolution, not new content) - see SAMPLE_SEED below. group_key()'s frame-tail
    stripping (built for Trackabox's genuine wb_framesNNNNN video-frame sequences)
    over-merges this set's catalog-style sequential IDs (Wild_Boar_0001,
    Wild_Boar_0002, ... are DIFFERENT source photos, not consecutive video frames -
    confirmed by checking date_captured, which is flat upload-time metadata, not a
    real capture timestamp, so it cannot distinguish the two cases; distinguished
    instead by the exact-stem duplicate-group size topping out at 6, versus the
    1,155-image mega-group frame-tail stripping produces when wrongly applied here).
    group_key_exact() is used for this source instead: only Roboflow's own
    "_jpg.rf.<hash>" rewrite is stripped, so same-photo re-exports still collapse
    into one group but distinct sequentially-numbered photos do not.
    Only ~1,379 of the 2,483 groups are sampled (one representative image per
    group, group order shuffled under SAMPLE_SEED) - enough to bring Boar's total
    from 1,901 to 3,280, exactly matching Elephant, without pulling in either
    redundant re-exports of the same photo or more images than Elephant has.

552 of the 3,280 elephant images and 4 of the 1,901 trackabox boar images carry no
bounding box at all. Those are not defects and are not discarded: the elephant set
ships deliberate non-animal scenes (casino, hospital-corridor, Kindergarden_classroom,
pantry, Libreria) as hard negatives. They are uploaded with an empty boundingBoxes
list, which is how Edge Impulse marks a background sample, so FOMO learns what "no
animal" looks like instead of only ever seeing frames that contain one.

Both datasets are general daytime/colour wildlife photography. Neither is
IR-illuminated night camera-trap footage, while ADR 0001
(docs/decisions/0001-usb-camera-imx462.md) puts >70% of elephant raids at night
behind 940nm active IR. This script closes "a two-class FOMO model is trained on
real, licensed data" - it does not establish anything about night field
performance. See ml/vision/README.md for the full caveat list.

The split is group-aware, not per-image. Both sets mix standalone photos with
runs of consecutive video frames (elephant "E026-..." x155, "casino-..." x103;
boar "Wild_Boar-..." x306, "wb_framesa00001-..." x254), and Roboflow gives the
boar set no test split at all (train 1,901, valid 0, test 0). A naive per-image
80/20 would put near-identical adjacent frames on both sides and inflate the
held-out number. Images are grouped by source-clip stem and whole groups are
assigned to one side - the same "split by event, not by sample" discipline
scripts/edge_impulse_upload_seismic.py already uses. The assignment is seeded
and written to ml/vision/dataset_manifest.json so the split behind the reported
number is reproducible from a fresh clone.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1094260
    set ROBOFLOW_API_KEY=...
    python scripts\\edge_impulse_upload_vision.py

    python scripts\\edge_impulse_upload_vision.py --dry-run --limit 20

Downloaded zips and extracted images land in ml/datasets/vision/raw/, which is
already gitignored (.gitignore covers ml/datasets/**/*.zip and ml/datasets/**/raw/),
so ~300MB of source imagery never enters the repo.

Requires only the standard library - no pip install needed.
"""

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

INGEST = "https://ingestion.edgeimpulse.com/api"
STUDIO = "https://studio.edgeimpulse.com/v1/api"
ROBOFLOW = "https://api.roboflow.com"

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
CACHE_DIR = os.path.join(_ROOT, "ml", "datasets", "vision", "raw")
MANIFEST = os.path.join(_ROOT, "ml", "vision", "dataset_manifest.json")

# Fixed so the split is reproducible; recorded in the manifest and the README. Also
# reused to shuffle group order when a source declares sample_target (BoarWatch).
SPLIT_SEED = 20260822
TEST_FRACTION = 0.20
# A group is only allowed into the test side if it still fits this far over target,
# so one 306-image clip cannot drag the held-out share far past 20%.
TEST_OVERSHOOT = 1.10
# Edge Impulse caps a files request at 1000 files / 100MB per file. 64 keeps each
# request well under any request-size limit while still being ~80 requests total.
BATCH_SIZE = 64
MAX_RETRIES = 4

DATASETS = [
    {
        "label": "Elephant",
        "workspace": "roboflow-universe-projects",
        "project": "elephant-detection-cxnt1",
        "version": 2,
        "slug": "elephant-detection-cxnt1-v2",
        "expect_images": 3280,
        # Cross-check only. The Roboflow project page reports 4,478 boxes; the frozen
        # v2 export actually carries 4,477 (432 test + 3,166 train + 879 valid). The
        # export is what gets uploaded, so the export is what the README reports.
        "page_boxes": 4478,
        "rename": {},
        "drop": set(),
    },
    {
        "label": "Boar",
        "workspace": "trackabox-4ejy9",
        "project": "wild-boar-a1flm",
        "version": 1,
        "slug": "wild-boar-a1flm-v1",
        "expect_images": 1901,
        # The project page reports 2,739 boxes; the v1 export carries 3,003, all of
        # them category "Pig". The page's per-class tally reflects the project's
        # current label state, not this frozen version - the export wins.
        "page_boxes": 2739,
        "rename": {"Pig": "Boar"},
        # The project declares a stray category literally named "`". It carries no
        # annotations in this export, but the guard stays so it can never sneak in.
        "drop": {"`"},
    },
    {
        "label": "Boar",
        "workspace": "boarwatch",
        "project": "wild-boar-deterrent-pzq5t",
        "version": 1,
        "slug": "wild-boar-deterrent-pzq5t-v1",
        "expect_images": 8857,
        "page_boxes": 13894,
        "rename": {"0": "Boar"},
        "drop": set(),
        # See the module docstring: this source's filenames are catalog-style
        # sequential IDs, not video-frame bursts, so group_key_exact() (Roboflow-
        # hash-suffix-only) is used instead of group_key()'s frame-tail stripping.
        "group_mode": "exact",
        # Brings Boar's total from 1,901 (trackabox alone) to 3,280 - Elephant's
        # exact count. One representative image is kept per sampled group.
        "sample_target": 1379,
    },
]

# Roboflow rewrites every exported filename as <stem>_<ext>.rf.<32 hex>.<ext>.
_RF_SUFFIX = re.compile(r"_(jpg|jpeg|png|bmp|webp)\.rf\.[0-9a-f]{6,}\.\w+$", re.IGNORECASE)
# A trailing frame counter, e.g. "wb_framesb--85-" -> clip "wb_framesb", "0004-124-" -> "0004".
_FRAME_TAIL = re.compile(r"^(.*?)[-_]+\d+$")


def _request(url, api_key=None, method="GET", body=None):
    headers = {}
    if api_key:
        headers["x-api-key"] = api_key
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def ensure_object_detection(project_id, api_key):
    """Flip the project to bounding-box labeling; bbox ingestion is lossy otherwise.

    A fresh Edge Impulse project defaults to labelingMethod "single_label", which
    ignores the boundingBoxes in an upload. This is checked, not assumed.
    """
    info = _request(f"{STUDIO}/{project_id}", api_key=api_key)
    project = info.get("project", {})
    current = project.get("labelingMethod")
    print(f"Edge Impulse project {project_id} ({project.get('name')}): labelingMethod={current}")
    if current == "object_detection":
        return
    _request(
        f"{STUDIO}/{project_id}",
        api_key=api_key,
        method="POST",
        body={"labelingMethod": "object_detection"},
    )
    print(f"  changed labelingMethod {current!r} -> 'object_detection'")


def roboflow_export_link(ds, rf_key):
    """Ask Roboflow for a COCO export of one dataset version, waiting if it is generating."""
    url = f"{ROBOFLOW}/{ds['workspace']}/{ds['project']}/{ds['version']}/coco?api_key={rf_key}"
    for attempt in range(MAX_RETRIES):
        doc = _request(url)
        export = doc.get("export") or {}
        if export.get("link"):
            return export["link"], export.get("size")
        wait = 15 * (attempt + 1)
        print(f"  export still generating (progress={doc.get('progress')}), waiting {wait}s")
        time.sleep(wait)
    raise RuntimeError(f"{ds['slug']}: Roboflow never returned an export link")


def fetch_dataset(ds, rf_key):
    """Download + extract one dataset version, reusing the cache when it is intact."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    zip_path = os.path.join(CACHE_DIR, f"{ds['slug']}-coco.zip")
    out_dir = os.path.join(CACHE_DIR, ds["slug"])

    link, size_mb = roboflow_export_link(ds, rf_key)
    # Roboflow reports the export size in megabytes (1e6 bytes), not mebibytes.
    expect_bytes = int(size_mb * 1e6) if size_mb else None
    have = os.path.getsize(zip_path) if os.path.exists(zip_path) else 0
    if have and (expect_bytes is None or abs(have - expect_bytes) < max(1024, expect_bytes * 0.01)):
        print(f"  cached {os.path.basename(zip_path)} ({have / 1e6:.1f} MB) - skipping download")
    else:
        print(f"  downloading {size_mb:.1f} MB -> {zip_path}")
        urllib.request.urlretrieve(link, zip_path)
        print(f"  downloaded {os.path.getsize(zip_path) / 1e6:.1f} MB")

    if os.path.isdir(out_dir):
        print(f"  already extracted at {out_dir}")
    else:
        print(f"  extracting -> {out_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(out_dir)
    return out_dir


def group_key(fname):
    """Collapse a Roboflow filename to the source clip it came from.

    Strips Roboflow's "_jpg.rf.<hash>.jpg" rewrite, then one trailing frame
    counter, so consecutive frames of one clip share a key and never straddle
    the train/test boundary. Standalone photos keep their own stem and stay
    their own single-image group.
    """
    stem = os.path.splitext(_RF_SUFFIX.sub("", fname))[0].rstrip("-_ ")
    match = _FRAME_TAIL.match(stem)
    return match.group(1) if match and match.group(1) else stem


def group_key_exact(fname):
    """Like group_key(), but without the trailing-frame-number collapse.

    Correct for sources whose filenames are catalog-style sequential IDs
    (Wild_Boar_0001, Wild_Boar_0002, ... - each number a different source photo)
    rather than genuine consecutive video frames. Applying group_key() there
    would merge hundreds of distinct photos into one artificial mega-group. Same-
    photo re-exports (identical stem, different resolution) still collapse into
    one group, since only Roboflow's own hash suffix is stripped.
    """
    return os.path.splitext(_RF_SUFFIX.sub("", fname))[0].rstrip("-_ ")


def sample_by_group(records, target, label, seed=SPLIT_SEED):
    """Pick one representative image from each of a shuffled subset of groups.

    Used to bring a heavily-grouped source down to a target image count while
    maximizing real visual diversity per image added: one image per group beats
    many images from few groups, since within-group images are re-exports of the
    same photo. Groups are consumed in seeded-shuffle order until target images
    are selected or groups run out.
    """
    groups = {}
    for rec in records:
        groups.setdefault(rec["group"], []).append(rec)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)

    selected = []
    for key in keys:
        if len(selected) >= target:
            break
        rep = sorted(groups[key], key=lambda r: r["name"])[0]
        selected.append(rep)

    print(
        f"  {label}: sampling {target} of {len(groups)} groups "
        f"({len(records)} raw images) -> {len(selected)} images selected "
        f"(seed {seed}, 1 representative image/group)"
    )
    if len(selected) < target:
        print(
            f"    NOTE: only {len(groups)} groups exist, target {target} not reached "
            f"({target - len(selected)} short)"
        )
    return selected


def parse_coco(root, ds):
    """Read every _annotations.coco.json under root into EI-shaped records.

    Roboflow writes one annotation file per split directory. All of them are
    merged here because this script does its own group-aware split; Roboflow's
    own train/valid/test division is discarded (and for the boar set there is
    none - all 1,901 images sit in train).
    """
    group_fn = group_key_exact if ds.get("group_mode") == "exact" else group_key
    records = []
    drops = {"zero_area": 0, "dropped_class": 0, "missing_file": 0}
    background = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        if "_annotations.coco.json" not in filenames:
            continue
        with open(os.path.join(dirpath, "_annotations.coco.json")) as fh:
            doc = json.load(fh)
        # Roboflow emits a root supercategory ("supercategory": "none") that never
        # carries annotations; keep only the real leaf classes.
        leaves = {
            c["id"]: c["name"]
            for c in doc.get("categories", [])
            if c.get("supercategory", "none") != "none"
        }
        cats = leaves or {c["id"]: c["name"] for c in doc.get("categories", [])}
        images = {img["id"]: img for img in doc.get("images", [])}

        by_image = {}
        for ann in doc.get("annotations", []):
            raw = cats.get(ann["category_id"])
            if raw is None or raw in ds["drop"]:
                drops["dropped_class"] += 1
                continue
            img = images.get(ann["image_id"])
            if img is None:
                continue
            x, y, w, h = (round(v) for v in ann["bbox"])
            x, y = max(0, x), max(0, y)
            w, h = min(w, img["width"] - x), min(h, img["height"] - y)
            if w <= 0 or h <= 0:
                drops["zero_area"] += 1
                continue
            by_image.setdefault(ann["image_id"], []).append(
                {"label": ds["rename"].get(raw, raw), "x": x, "y": y, "width": w, "height": h}
            )

        for img_id, img in images.items():
            # An image with no boxes is a deliberate negative, not a defect: the
            # elephant set ships 552 non-elephant scenes (casino, hospital-corridor,
            # Kindergarden_classroom, pantry...). Uploaded with an empty
            # boundingBoxes list, they are exactly the background examples FOMO
            # needs to learn what "no animal" looks like, so they are kept.
            boxes = by_image.get(img_id, [])
            if not boxes:
                background += 1
            path = os.path.join(dirpath, img["file_name"])
            if not os.path.exists(path):
                drops["missing_file"] += 1
                continue
            records.append(
                {
                    "path": path,
                    "name": img["file_name"],
                    "group": group_fn(img["file_name"]),
                    "boxes": boxes,
                }
            )
    records.sort(key=lambda r: r["name"])
    return records, drops, background


def split_by_group(records, label):
    """Assign whole source-clip groups to training/testing at ~80/20."""
    groups = {}
    for rec in records:
        groups.setdefault(rec["group"], []).append(rec)
    keys = sorted(groups)
    random.Random(SPLIT_SEED).shuffle(keys)

    target = len(records) * TEST_FRACTION
    testing, n_test = set(), 0
    for key in keys:
        size = len(groups[key])
        if n_test + size <= target * TEST_OVERSHOOT:
            testing.add(key)
            n_test += size
    for rec in records:
        rec["category"] = "testing" if rec["group"] in testing else "training"

    clustered = sum(len(v) for v in groups.values() if len(v) > 1)
    biggest = sorted(((len(v), k) for k, v in groups.items()), reverse=True)[:4]
    print(f"  {label}: {len(records)} images in {len(groups)} groups (seed {SPLIT_SEED})")
    print(f"    largest clips: {', '.join(f'{k} x{n}' for n, k in biggest)}")
    print(f"    {clustered} images ({clustered / len(records) * 100:.0f}%) sit in multi-image clips")
    print(
        f"    training {len(records) - n_test} / testing {n_test} "
        f"({n_test / len(records) * 100:.1f}% held out)"
    )
    if clustered < len(records) * 0.05:
        print(
            "    WARNING: almost every group holds a single image - grouping is a near no-op "
            "here and this split is effectively random. Carry that into the README."
        )
    return groups, clustered


def _content_type(name):
    ext = os.path.splitext(name)[1].lower()
    return {".png": "image/png", ".bmp": "image/bmp", ".webp": "image/webp"}.get(ext, "image/jpeg")


def _multipart(parts):
    """Encode (filename, content_type, bytes) parts as one multipart/form-data body.

    Every part uses the field name "data", which is what the ingestion API's files
    endpoint expects - including for the bounding_boxes.labels part that rides
    along in the same batch and carries the labels for the images beside it.
    """
    boundary = f"----EleTectX{random.getrandbits(64):016x}"
    body = bytearray()
    for fname, ctype, data in parts:
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="data"; filename="{fname}"\r\n'.encode()
        body += f"Content-Type: {ctype}\r\n\r\n".encode()
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return boundary, bytes(body)


def upload_batch(api_key, category, batch):
    """POST one batch of images plus their bounding_boxes.labels to the ingestion API."""
    # The legacy "bounding_boxes.labels" schema - a flat filename -> boxes map under
    # an explicit type - is the one this endpoint accepts. The newer "info.labels"
    # files[] shape documented on the annotation spec page is rejected here: sent
    # under this filename it fails with {"error":"Invalid type"}, and sent as
    # info.labels it is treated as a data file ("Invalid mimetype"). Verified against
    # the live API, not assumed - a wrong shape uploads the images with no boxes
    # at all rather than failing loudly.
    labels = {
        "version": 1,
        "type": "bounding-box-labels",
        "boundingBoxes": {r["name"]: r["boxes"] for r in batch},
    }
    parts = [("bounding_boxes.labels", "application/json", json.dumps(labels).encode())]
    for rec in batch:
        with open(rec["path"], "rb") as fh:
            parts.append((rec["name"], _content_type(rec["name"]), fh.read()))
    boundary, body = _multipart(parts)

    for attempt in range(MAX_RETRIES):
        req = urllib.request.Request(
            f"{INGEST}/{category}/files",
            data=body,
            method="POST",
            headers={
                "x-api-key": api_key,
                "x-disallow-duplicates": "1",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                resp.read()
            return None
        except urllib.error.HTTPError as err:
            detail = err.read().decode()[:300]
            if err.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    HTTP {err.code}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return err.code, detail
        except urllib.error.URLError as err:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * 2**attempt
                print(f"    {err.reason}, retrying in {wait}s")
                time.sleep(wait)
                continue
            return 0, str(err.reason)
    return 0, "exhausted retries"


def _ledger_path(slug):
    """Resume ledger, kept in the gitignored cache - not the committed manifest."""
    return os.path.join(CACHE_DIR, f"uploaded-{slug}.json")


def upload_dataset(api_key, ds, records):
    """Upload one class in batches, skipping anything a previous run already sent."""
    path = _ledger_path(ds["slug"])
    done = set()
    if os.path.exists(path):
        with open(path) as fh:
            done = set(json.load(fh))
    pending = [r for r in records if r["name"] not in done]
    if done:
        print(f"  resuming: {len(done)} already uploaded, {len(pending)} remaining")

    ok, failed = 0, []
    for category in ("training", "testing"):
        subset = [r for r in pending if r["category"] == category]
        for i in range(0, len(subset), BATCH_SIZE):
            batch = subset[i : i + BATCH_SIZE]
            err = upload_batch(api_key, category, batch)
            if err:
                failed.append((ds["label"], category, batch[0]["name"], err[0], err[1]))
                print(f"  [{category}] {ds['label']:8s} batch of {len(batch):3d} -> FAILED {err[0]}")
                continue
            ok += len(batch)
            done.update(r["name"] for r in batch)
            with open(path, "w") as fh:
                json.dump(sorted(done), fh)
            print(f"  [{category}] {ds['label']:8s} batch of {len(batch):3d} -> uploaded ({ok} so far)")
    return ok, failed


def write_manifest(entries):
    """Commit the split assignment so the reported number is reproducible from a clone."""
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    doc = {"split_seed": SPLIT_SEED, "test_fraction": TEST_FRACTION, "classes": entries}
    with open(MANIFEST, "w") as fh:
        json.dump(doc, fh, indent=1)
        fh.write("\n")
    print(f"\nWrote split ledger -> {MANIFEST}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="do everything except upload")
    ap.add_argument("--limit", type=int, help="use only the first N images per class")
    args = ap.parse_args()

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    rf_key = os.environ.get("ROBOFLOW_API_KEY")
    if not api_key or not project_id or not rf_key:
        print(
            "Set EI_API_KEY, EI_PROJECT_ID and ROBOFLOW_API_KEY environment variables first.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.dry_run:
        ensure_object_detection(project_id, api_key)

    all_failed, manifest, report_rows = [], {}, []
    for ds in DATASETS:
        print(f"\n=== {ds['label']}: {ds['workspace']}/{ds['project']} v{ds['version']} (CC BY 4.0) ===")
        root = fetch_dataset(ds, rf_key)
        records, drops, background = parse_coco(root, ds)
        boxes = sum(len(r["boxes"]) for r in records)
        labelled = len(records) - background
        print(f"  parsed {len(records)} images / {boxes} boxes")
        print(f"    {labelled} carry >=1 box, {background} are background (zero boxes, kept)")
        print(f"    project page reports {ds['expect_images']} images / {ds['page_boxes']} boxes")
        if boxes != ds["page_boxes"]:
            print(
                f"    NOTE: export carries {boxes} boxes, page says {ds['page_boxes']} - the page "
                f"tallies the project's live label state, this frozen export is what is uploaded"
            )
        for reason, count in drops.items():
            if count:
                print(f"    dropped {count} ({reason})")
        gap = ds["expect_images"] - len(records) - drops["missing_file"]
        if gap:
            print(f"    UNEXPLAINED GAP: {gap} images unaccounted for - do not trust these counts")

        if ds.get("sample_target"):
            records = sample_by_group(records, ds["sample_target"], ds["label"])
            boxes = sum(len(r["boxes"]) for r in records)
            background = sum(1 for r in records if not r["boxes"])
            labelled = len(records) - background
            print(
                f"    post-sample: {len(records)} images / {boxes} boxes "
                f"({labelled} boxed, {background} background)"
            )

        groups, clustered = split_by_group(records, ds["label"])
        if args.limit:
            records = records[: args.limit]
            print(f"    --limit {args.limit}: truncated to {len(records)} images")

        entry = {
            "source": f"{ds['workspace']}/{ds['project']}/{ds['version']}",
            "license": "CC BY 4.0",
            "relabelled_from": ds["rename"] or None,
            "dropped_classes": sorted(ds["drop"]) or None,
            "images": len(records),
            "images_with_boxes": labelled,
            "background_images": background,
            "boxes": boxes,
            "groups": len(groups),
            "images_in_multi_image_groups": clustered,
            "drops": drops,
            "training": sorted(r["name"] for r in records if r["category"] == "training"),
            "testing": sorted(r["name"] for r in records if r["category"] == "testing"),
        }
        # A label (e.g. "Boar") can now come from more than one source - merge into
        # a combined entry with a per-source breakdown, rather than overwrite.
        if ds["label"] in manifest:
            prior = manifest[ds["label"]]
            sources = prior.get("sources") or [
                {k: v for k, v in prior.items() if k not in ("training", "testing")}
            ]
            sources.append({k: v for k, v in entry.items() if k not in ("training", "testing")})
            manifest[ds["label"]] = {
                "sources": sources,
                "images": prior["images"] + entry["images"],
                "images_with_boxes": prior["images_with_boxes"] + entry["images_with_boxes"],
                "background_images": prior["background_images"] + entry["background_images"],
                "boxes": prior["boxes"] + entry["boxes"],
                "groups": prior["groups"] + entry["groups"],
                "images_in_multi_image_groups": (
                    prior["images_in_multi_image_groups"] + entry["images_in_multi_image_groups"]
                ),
                "training": sorted(prior["training"] + entry["training"]),
                "testing": sorted(prior["testing"] + entry["testing"]),
            }
        else:
            manifest[ds["label"]] = entry

        row = {
            "label": ds["label"],
            "slug": ds["slug"],
            "expect_images": ds["expect_images"],
            "images": entry["images"],
            "images_with_boxes": entry["images_with_boxes"],
            "background_images": entry["background_images"],
            "train": len(entry["training"]),
            "test": len(entry["testing"]),
            "uploaded": 0,
        }
        if args.dry_run:
            print(f"  --dry-run: not uploading {len(records)} images")
            report_rows.append(row)
            continue
        ok, failed = upload_dataset(api_key, ds, records)
        all_failed.extend(failed)
        row["uploaded"] = ok
        report_rows.append(row)

    write_manifest(manifest)

    print("\nReconciliation (source -> uploaded, every drop named above):")
    header = f"  {'class':10s} {'slug':>26s} {'source':>7s} {'parsed':>7s} {'boxed':>7s} {'bkgnd':>7s}"
    print(f"{header} {'train':>7s} {'test':>7s} {'uploaded':>9s}")
    for row in report_rows:
        print(
            f"  {row['label']:10s} {row['slug']:>26s} {row['expect_images']:7d} {row['images']:7d} "
            f"{row['images_with_boxes']:7d} {row['background_images']:7d} "
            f"{row['train']:7d} {row['test']:7d} {row['uploaded']:9d}"
        )
    for label in sorted({r["label"] for r in report_rows}):
        total = sum(r["images"] for r in report_rows if r["label"] == label)
        print(f"  {label} combined total: {total} images")

    if all_failed:
        print("\nFailures:")
        for f in all_failed:
            print(" ", f)
        sys.exit(1)
    if not args.dry_run:
        print(
            f"\nCheck the result at "
            f"https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training"
        )


if __name__ == "__main__":
    main()
