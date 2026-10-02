"""Full-census audit, step 4: render one contact sheet (or list sheet counts)
from ml/vision/_audit_master_manifest.json for by-eye review of a single
dataset source - boxes drawn in red, filename + live label + box count
captioned per tile, so cross-class contamination, bad boxes, and missed
boxes are all visible in one look per tile.

Usage:
  python scripts/audit_render_sheet.py --list
      Print every source with its live image count and sheet count.

  python scripts/audit_render_sheet.py --source <name> --sheet <n>
      Render sheet <n> (0-indexed) for that source to
      ml/vision/_audit_sheets/<source>/<source>_<n:04d>.png, plus a paired
      .json index (same order as tiles) with id/filename/label/boxes/status
      for the reviewer to cite when flagging a tile.

  python scripts/audit_render_sheet.py --source <name> --all
      Render every not-yet-rendered sheet for that source.

Chunking is deterministic (sorted by live sample id), so re-running is
idempotent and safe to resume mid-source.
"""
import argparse
import json
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
VISION = os.path.join(ROOT, "ml", "vision")
MASTER_PATH = os.path.join(VISION, "_audit_master_manifest.json")
SHEETS_DIR = os.path.join(VISION, "_audit_sheets")

COLS = 6
CELL = 220
PER_SHEET = 30  # COLS * 5 rows


def load_master():
    with open(MASTER_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def group_by_source(rows):
    by_source = {}
    for r in rows:
        src = r["source"] or "__orphan_live__"
        by_source.setdefault(src, []).append(r)
    for src_rows in by_source.values():
        src_rows.sort(key=lambda r: r["id"])
    return by_source


def font():
    try:
        return ImageFont.truetype("arial.ttf", 12)
    except Exception:  # noqa: BLE001 - any font failure falls back, none is fatal here
        return ImageFont.load_default()


def render_chunk(chunk, out_png):
    n = len(chunk)
    rows = (n + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * CELL, rows * (CELL + 30)), "white")
    draw = ImageDraw.Draw(sheet)
    fnt = font()
    for i, rec in enumerate(chunk):
        path = rec["local_path"]
        cx, cy = (i % COLS) * CELL, (i // COLS) * (CELL + 30)
        if not path or not os.path.exists(path):
            draw.rectangle([cx + 5, cy + 20, cx + CELL - 5, cy + CELL - 5], outline="orange", width=2)
            draw.text((cx + 5, cy + 22), "NO LOCAL FILE", fill="red", font=fnt)
        else:
            im = Image.open(path).convert("RGB")
            d = ImageDraw.Draw(im)
            for b in rec["boundingBoxes"]:
                x, y, w, h = b["x"], b["y"], b["width"], b["height"]
                d.rectangle([x, y, x + w, y + h], outline="red", width=max(2, im.width // 160))
                d.text((x + 2, y + 2), b["label"], fill="red")
            im.thumbnail((CELL - 10, CELL - 10))
            sheet.paste(im, (cx + 5, cy + 25))
        label = (rec["label"] or "-").split(",")[0].strip() or "bg"
        cap = f"{i}:{label}/{len(rec['boundingBoxes'])}box {rec['filename'][:24]}"
        draw.text((cx + 3, cy + 2), cap, fill="black", font=fnt)
    sheet.save(out_png)


def sheets_for(rows):
    return [rows[i:i + PER_SHEET] for i in range(0, len(rows), PER_SHEET)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source")
    ap.add_argument("--sheet", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    rows = load_master()
    by_source = group_by_source(rows)

    if args.list or not args.source:
        print(f"{'source':<45} {'images':>7} {'sheets':>7}")
        total_img = total_sheets = 0
        for src, recs in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
            n_sheets = len(sheets_for(recs))
            print(f"{src:<45} {len(recs):>7} {n_sheets:>7}")
            total_img += len(recs)
            total_sheets += n_sheets
        print(f"{'TOTAL':<45} {total_img:>7} {total_sheets:>7}")
        return

    recs = by_source.get(args.source)
    if recs is None:
        print(f"Unknown source '{args.source}'. Use --list to see valid names.")
        return
    chunks = sheets_for(recs)
    out_dir = os.path.join(SHEETS_DIR, args.source)
    os.makedirs(out_dir, exist_ok=True)

    targets = range(len(chunks)) if args.all else [args.sheet if args.sheet is not None else 0]
    for idx in targets:
        if idx >= len(chunks):
            print(f"sheet {idx} out of range (source has {len(chunks)} sheets)")
            continue
        chunk = chunks[idx]
        out_png = os.path.join(out_dir, f"{args.source}_{idx:04d}.png")
        out_json = os.path.join(out_dir, f"{args.source}_{idx:04d}.json")
        render_chunk(chunk, out_png)
        with open(out_json, "w", encoding="utf-8") as fh:
            json.dump(
                [{"tile": i, "id": r["id"], "filename": r["filename"],
                  "category": r["category"], "label": r["label"],
                  "boxes": r["boundingBoxes"]} for i, r in enumerate(chunk)],
                fh, indent=2,
            )
        print(f"wrote {out_png} ({len(chunk)} tiles) [{idx + 1}/{len(chunks)}]")


if __name__ == "__main__":
    main()
