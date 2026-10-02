"""Full-census audit, step 5: the persistent, resumable tracking manifest.
One row per (source, sheet index): reviewed y/n, verdict, and any flagged
tiles (contamination / bad box / missed box / other) with enough detail
(sample id, filename, category) to act on later without re-rendering.

Usage (all read/modify ml/vision/_audit_progress.json directly):
  python scripts/audit_progress.py init
      Build/refresh the skeleton from the master manifest (idempotent -
      never clears existing verdicts, only adds newly-appeared sheets).

  python scripts/audit_progress.py status [--source NAME]
      Print reviewed/total sheet counts per source (or one source), plus a
      running total of flagged issues by type - the resume point.

  python scripts/audit_progress.py mark --source NAME --sheet N --verdict clean
      Mark a sheet clean with no flags.

  python scripts/audit_progress.py flag --source NAME --sheet N --tile T \
      --issue contamination|bad_box|missed_box|other --note "..."
      Record one flagged tile on a sheet (does not itself mark the sheet
      reviewed - call mark separately once all tiles on the sheet are judged).
"""
import argparse
import json
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
VISION = os.path.join(ROOT, "ml", "vision")
MASTER_PATH = os.path.join(VISION, "_audit_master_manifest.json")
PROGRESS_PATH = os.path.join(VISION, "_audit_progress.json")
PER_SHEET = 30


def load_master_by_source():
    with open(MASTER_PATH, encoding="utf-8") as fh:
        rows = json.load(fh)
    by_source = {}
    for r in rows:
        src = r["source"] or "__orphan_live__"
        by_source.setdefault(src, []).append(r)
    for src_rows in by_source.values():
        src_rows.sort(key=lambda r: r["id"])
    return by_source


def load_progress():
    if os.path.exists(PROGRESS_PATH):
        with open(PROGRESS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {"sources": {}}


def save_progress(data):
    with open(PROGRESS_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def cmd_init(_args):
    by_source = load_master_by_source()
    progress = load_progress()
    for src, recs in by_source.items():
        n_sheets = (len(recs) + PER_SHEET - 1) // PER_SHEET
        entry = progress["sources"].setdefault(src, {
            "total_images": 0, "total_sheets": 0, "reviewed_sheets": [], "flagged": [],
        })
        entry["total_images"] = len(recs)
        entry["total_sheets"] = n_sheets
    save_progress(progress)
    print(f"Initialized/refreshed progress for {len(by_source)} sources.")
    cmd_status(argparse.Namespace(source=None))


def cmd_status(args):
    progress = load_progress()
    sources = progress["sources"]
    names = [args.source] if args.source else sorted(sources, key=lambda s: -sources[s]["total_images"])
    total_sheets = total_reviewed = total_flags = 0
    for src in names:
        if src not in sources:
            print(f"(no data for {src})")
            continue
        e = sources[src]
        n_reviewed = len(e["reviewed_sheets"])
        n_flags = len(e["flagged"])
        done = "DONE" if n_reviewed >= e["total_sheets"] else ""
        print(f"{src:<45} {n_reviewed:>4}/{e['total_sheets']:<4} sheets  "
              f"{e['total_images']:>6} images  {n_flags:>4} flags  {done}")
        total_sheets += e["total_sheets"]
        total_reviewed += n_reviewed
        total_flags += n_flags
    if not args.source:
        print(f"\nTOTAL: {total_reviewed}/{total_sheets} sheets reviewed, {total_flags} flags recorded")


def cmd_mark(args):
    progress = load_progress()
    entry = progress["sources"].setdefault(args.source, {
        "total_images": 0, "total_sheets": 0, "reviewed_sheets": [], "flagged": [],
    })
    if args.sheet not in entry["reviewed_sheets"]:
        entry["reviewed_sheets"].append(args.sheet)
        entry["reviewed_sheets"].sort()
    save_progress(progress)
    print(f"Marked {args.source} sheet {args.sheet} as reviewed ({args.verdict}).")


def cmd_flag(args):
    progress = load_progress()
    entry = progress["sources"].setdefault(args.source, {
        "total_images": 0, "total_sheets": 0, "reviewed_sheets": [], "flagged": [],
    })
    entry["flagged"].append({
        "sheet": args.sheet, "tile": args.tile, "issue": args.issue, "note": args.note,
    })
    save_progress(progress)
    print(f"Flagged {args.source} sheet {args.sheet} tile {args.tile}: {args.issue} - {args.note}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init").set_defaults(func=cmd_init)

    p_status = sub.add_parser("status")
    p_status.add_argument("--source")
    p_status.set_defaults(func=cmd_status)

    p_mark = sub.add_parser("mark")
    p_mark.add_argument("--source", required=True)
    p_mark.add_argument("--sheet", type=int, required=True)
    p_mark.add_argument("--verdict", default="clean")
    p_mark.set_defaults(func=cmd_mark)

    p_flag = sub.add_parser("flag")
    p_flag.add_argument("--source", required=True)
    p_flag.add_argument("--sheet", type=int, required=True)
    p_flag.add_argument("--tile", type=int, required=True)
    p_flag.add_argument("--issue", required=True, choices=["contamination", "bad_box", "missed_box", "other"])
    p_flag.add_argument("--note", required=True)
    p_flag.set_defaults(func=cmd_flag)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
