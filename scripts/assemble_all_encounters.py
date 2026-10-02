#!/usr/bin/env python3
"""Assemble every encounter directory under a HOME_TEST_MODE encounters/ tree into its own MP4.

One night can produce several separate Boar/Elephant encounters - each already
lives in its own timestamped directory under .../data/home_test/encounters/
(device/mpu/services/home_test.py's _start_encounter names it
"%Y%m%dT%H%M%S"). This script is the batch counterpart to
scripts/assemble_encounter.py: it walks every such subdirectory, skips any
that already have an up-to-date clip, and assembles the rest, so a whole
night's encounters become a whole night's separate MP4s in one command
instead of one scp+assemble invocation per encounter.

Usage:
    python scripts/assemble_all_encounters.py <encounters_root> [--output-dir DIR]
                                               [--fps FPS] [--force]

    python scripts/assemble_all_encounters.py \
        content/footage/pre_deployment_backup_20260907/home_test/encounters \
        --output-dir content/footage/clips
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from assemble_encounter import assemble


def main() -> int:
    """CLI entry point: assemble every encounter subdirectory found under root."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("encounters_root", type=Path, help="a HOME_TEST_MODE encounters/ directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="where clips are written, one <encounter_name>.mp4 per encounter "
        "(default: alongside each encounter, as clip.mp4)",
    )
    parser.add_argument("--fps", type=float, default=None, help="override measured fps for every clip")
    parser.add_argument(
        "--force", action="store_true", help="re-assemble even if an output file already exists"
    )
    args = parser.parse_args()

    if not args.encounters_root.is_dir():
        print(f"error: not a directory: {args.encounters_root}", file=sys.stderr)
        return 1

    encounter_dirs = sorted(p for p in args.encounters_root.iterdir() if p.is_dir())
    if not encounter_dirs:
        print(f"no encounter subdirectories found in {args.encounters_root}", file=sys.stderr)
        return 1

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    failures = []
    for encounter_dir in encounter_dirs:
        output_path = (
            args.output_dir / f"{encounter_dir.name}.mp4"
            if args.output_dir is not None
            else encounter_dir / "clip.mp4"
        )
        print(f"\n=== {encounter_dir.name} ===")
        if output_path.exists() and not args.force:
            print(f"skip: {output_path} already exists (--force to redo)")
            continue
        rc = assemble(encounter_dir, output_path, args.fps, "*.jpg")
        if rc != 0:
            failures.append(encounter_dir.name)

    print(f"\n{len(encounter_dirs) - len(failures)}/{len(encounter_dirs)} encounters assembled.")
    if failures:
        print("failed: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
