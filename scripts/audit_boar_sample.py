"""One-off audit script: draw a fresh, seeded, non-overlapping sample of boxed
Boar images from both sources, render contact sheets with boxes drawn, so they
can be opened by eye - same discipline as the existing 28 Aug manual visual
audit (BOAR_VISUALLY_CONTAMINATED_FILENAMES in scripts/edge_impulse_upload_vision.py).

Run from anywhere on the machine that has the extracted raw/ dirs - path
resolution is relative to this file's location, not the caller's cwd.
"""
import json
import os
import random

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
RAW = os.path.join(ROOT, "ml", "datasets", "vision", "raw")

EXISTING_EXCLUDED = {
    "d7154f3779821de9_jpg.rf.1d06037a219971872ea97772dd37215b.jpg",
    "1IAYSQYFEA8Q_jpg.rf.b9bf0a5d5efd5babde44b78b17ac8c63.jpg",
    "5G43741K8NPY_jpg.rf.43d6f724201912de30fd7b8d0a2b6961.jpg",
    "d7c11e86dd8ffd38_jpg.rf.e741bcc33088655b9f26b660a3b58156.jpg",
    "AKBYJRHQCL5J_jpg.rf.db49f8499f1e12b2e71f40c6971120f1.jpg",
    "9965b39bd2656ca1_jpg.rf.8cd037d8aa09de93bcd6f662e88fc681.jpg",
    "RY1FXEUNVGYF_jpg.rf.bdcfc932a1ef5adc181d4b8c13d117c3.jpg",
    "ZZ2S3FNL3X4B_jpg.rf.88bdfd02fc4efb6e5ab728676bb88355.jpg",
    "0BG9FX1AKE79_jpg.rf.bde8aac5952fa41a6d1c1da7fce7169a.jpg",
    "GIJCZQVE6KUK_jpg.rf.68cb6c38ca7dc3a111f4d1a855a23449.jpg",
    "512PQCA13JE7_jpg.rf.f8a91269b9cc13f94d5df6bee60daeb3.jpg",
    "WFH57W23NPDJ_jpg.rf.54885b40b28242f465394e293655d47f.jpg",
}


def parse(root):
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        if "_annotations.coco.json" not in filenames:
            continue
        with open(os.path.join(dirpath, "_annotations.coco.json")) as fh:
            doc = json.load(fh)
        leaves = {c["id"]: c["name"] for c in doc.get("categories", []) if c.get("supercategory", "none") != "none"}
        cats = leaves or {c["id"]: c["name"] for c in doc.get("categories", [])}
        images = {img["id"]: img for img in doc.get("images", [])}
        by_image = {}
        for ann in doc.get("annotations", []):
            if cats.get(ann["category_id"]) is None:
                continue
            if cats.get(ann["category_id"]) == "`":
                continue
            x, y, w, h = (round(v) for v in ann["bbox"])
            by_image.setdefault(ann["image_id"], []).append((x, y, w, h))
        for img_id, img in images.items():
            boxes = by_image.get(img_id)
            if not boxes:
                continue
            path = os.path.join(dirpath, img["file_name"])
            if not os.path.exists(path):
                continue
            out.append({"name": img["file_name"], "path": path, "boxes": boxes})
    return out


def contact_sheet(records, out_path, cols=5, cell=260):
    rows = (len(records) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell + 24)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        font = ImageFont.load_default()
    for i, rec in enumerate(records):
        im = Image.open(rec["path"]).convert("RGB")
        d = ImageDraw.Draw(im)
        for (x, y, w, h) in rec["boxes"]:
            d.rectangle([x, y, x + w, y + h], outline="red", width=4)
        im.thumbnail((cell - 10, cell - 10))
        cx, cy = (i % cols) * cell, (i // cols) * (cell + 24)
        sheet.paste(im, (cx + 5, cy + 20))
        label = f"{i}: {rec['name'][:34]}"
        draw.text((cx + 5, cy + 2), label, fill="black", font=font)
    sheet.save(out_path)
    print(f"wrote {out_path} ({len(records)} images, {cols}x{rows})")


def main():
    a1flm = parse(os.path.join(RAW, "wild-boar-a1flm-v1"))
    pzq5t = parse(os.path.join(RAW, "wild-boar-deterrent-pzq5t-v1"))
    a1flm = [r for r in a1flm if r["name"] not in EXISTING_EXCLUDED]
    pzq5t = [r for r in pzq5t if r["name"] not in EXISTING_EXCLUDED]
    print(f"a1flm pool (boxed, not-yet-excluded): {len(a1flm)}")
    print(f"pzq5t pool (boxed, not-yet-excluded): {len(pzq5t)}")

    seed = 202608282  # second audit pass, same date, distinguishable from the first (20260828)
    r1 = random.Random(seed)
    r2 = random.Random(seed + 1)
    sample_a1flm = r1.sample(a1flm, min(30, len(a1flm)))
    sample_pzq5t = r2.sample(pzq5t, min(30, len(pzq5t)))

    out_dir = os.path.join(RAW, "_audit_tmp")
    os.makedirs(out_dir, exist_ok=True)
    for i in range(0, len(sample_a1flm), 15):
        chunk = sample_a1flm[i : i + 15]
        contact_sheet(chunk, os.path.join(out_dir, f"a1flm_{i:03d}.png"))
        with open(os.path.join(out_dir, f"a1flm_{i:03d}.json"), "w") as fh:
            json.dump([r["name"] for r in chunk], fh, indent=2)
    for i in range(0, len(sample_pzq5t), 15):
        chunk = sample_pzq5t[i : i + 15]
        contact_sheet(chunk, os.path.join(out_dir, f"pzq5t_{i:03d}.png"))
        with open(os.path.join(out_dir, f"pzq5t_{i:03d}.json"), "w") as fh:
            json.dump([r["name"] for r in chunk], fh, indent=2)


if __name__ == "__main__":
    main()
