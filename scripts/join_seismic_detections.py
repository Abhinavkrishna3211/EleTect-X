#!/usr/bin/env python3
"""Join HOME_TEST_MODE's seismic CSV and vision detections JSONL by MPU wall time.

The two logs share one clock by construction: both are stamped with the
MPU's own time.time() on receipt - device/mpu/main.py's
debug_stream_raw_seismic_sample() writes "mpu_monotonic_s,mpu_wall_s,volts"
rows to HOME_TEST_SEISMIC_CSV_PATH, and device/mpu/services/home_test.py's
_log_detections() writes one JSON object per detection to
HOME_TEST_DETECTIONS_PATH with a "wall_s" field from the same clock. There is
no MCU-side millis() to reconcile and no offset regression to run - see the
plan note this script implements ("this also removes the clock-sync problem
the spec worried about").

For every seismic sample this labels the nearest vision detection in time and
whether that nearest detection falls within +/-window_s/2 of the sample -
that boolean is the "labelled window" the plan's Files section asks for: a
positive label means a vision-confirmed animal was in frame within window_s
of this raw geophone sample, which is what ml/seismic/'s still-missing
footfall classifier would train against.

Known gap: the geophone was not wired for the backyard test this was written
for, so HOME_TEST_SEISMIC_CSV_PATH is expected to be empty or absent on those
runs. This script's output format is fixed now so
whenever the geophone is wired again, the join needs no format change - it
is genuinely untestable against real seismic data until then. Use
--synthesize-demo to sanity-check the script itself against synthetic rows.

Usage:
    python scripts/join_seismic_detections.py \
        device/mpu/services/data/home_test/seismic_raw.csv \
        device/mpu/services/data/home_test/detections.jsonl \
        --output joined.csv
    python scripts/join_seismic_detections.py --synthesize-demo
"""

from __future__ import annotations

import argparse
import bisect
import csv
import json
import sys
from pathlib import Path
from typing import NamedTuple


class SeismicSample(NamedTuple):
    """One row of HOME_TEST_SEISMIC_CSV_PATH."""

    mpu_monotonic_s: float
    mpu_wall_s: float
    volts: float


class Detection(NamedTuple):
    """One JSON object from HOME_TEST_DETECTIONS_PATH, trimmed to what this script needs."""

    wall_s: float
    label: str
    confidence: float


def load_seismic_csv(path: Path) -> list[SeismicSample]:
    """Parse HOME_TEST_SEISMIC_CSV_PATH's header-less mpu_monotonic_s,mpu_wall_s,volts rows.

    Malformed lines are skipped with a warning rather than aborting the whole
    join - a single truncated row (plausible if this file is read mid-write,
    which is exactly the "join while the test is still running" case) should
    not lose every sample after it.
    """
    samples: list[SeismicSample] = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 3:
                print(
                    f"warning: {path}:{line_no}: expected 3 fields, got {len(parts)}",
                    file=sys.stderr,
                )
                continue
            try:
                samples.append(SeismicSample(float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                print(f"warning: {path}:{line_no}: non-numeric field, skipping", file=sys.stderr)
    samples.sort(key=lambda s: s.mpu_wall_s)
    return samples


def load_detections_jsonl(path: Path, target_labels: set[str] | None) -> list[Detection]:
    """Parse HOME_TEST_DETECTIONS_PATH, optionally filtered to a label set.

    target_labels of None keeps every detection, matching home_test.py's own
    "logging is never gated" stance - filtering, if any, happens here at
    join time, not at the source.
    """
    detections: list[Detection] = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"warning: {path}:{line_no}: invalid JSON, skipping", file=sys.stderr)
                continue
            label = record.get("label")
            if target_labels is not None and label not in target_labels:
                continue
            detections.append(
                Detection(
                    wall_s=float(record["wall_s"]),
                    label=label,
                    confidence=float(record.get("confidence", 0.0)),
                )
            )
    detections.sort(key=lambda d: d.wall_s)
    return detections


def nearest_detection(
    detections: list[Detection], detection_wall_times: list[float], wall_s: float
) -> tuple[Detection, float] | None:
    """Binary-search the detection closest in time to wall_s; returns (detection, signed delta_s).

    delta_s is detection.wall_s - wall_s: positive means the detection came
    after the seismic sample (the animal was seen after this ground tremor),
    negative means before.
    """
    if not detections:
        return None
    idx = bisect.bisect_left(detection_wall_times, wall_s)
    candidates = [i for i in (idx - 1, idx) if 0 <= i < len(detections)]
    best = min(candidates, key=lambda i: abs(detections[i].wall_s - wall_s))
    return detections[best], detections[best].wall_s - wall_s


def join(
    samples: list[SeismicSample],
    detections: list[Detection],
    window_s: float,
) -> list[dict[str, object]]:
    """Build one output row per seismic sample, labelled against the nearest detection."""
    detection_wall_times = [d.wall_s for d in detections]
    rows: list[dict[str, object]] = []
    for sample in samples:
        found = nearest_detection(detections, detection_wall_times, sample.mpu_wall_s)
        if found is None:
            rows.append(
                {
                    "mpu_monotonic_s": sample.mpu_monotonic_s,
                    "mpu_wall_s": sample.mpu_wall_s,
                    "volts": sample.volts,
                    "label": 0,
                    "nearest_detection_label": "",
                    "nearest_detection_confidence": "",
                    "nearest_detection_delta_s": "",
                }
            )
            continue
        detection, delta_s = found
        positive = abs(delta_s) <= (window_s / 2)
        rows.append(
            {
                "mpu_monotonic_s": sample.mpu_monotonic_s,
                "mpu_wall_s": sample.mpu_wall_s,
                "volts": sample.volts,
                "label": int(positive),
                "nearest_detection_label": detection.label,
                "nearest_detection_confidence": detection.confidence,
                "nearest_detection_delta_s": delta_s,
            }
        )
    return rows


def write_output_csv(rows: list[dict[str, object]], output_path: Path) -> None:
    """Write the joined rows as a CSV with a header, unlike the header-less input CSV."""
    fieldnames = [
        "mpu_monotonic_s",
        "mpu_wall_s",
        "volts",
        "label",
        "nearest_detection_label",
        "nearest_detection_confidence",
        "nearest_detection_delta_s",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(
    samples: list[SeismicSample], detections: list[Detection], rows: list[dict[str, object]]
) -> None:
    """Print coverage and label-balance stats so a thin dataset is obvious, not silent."""
    positives = sum(1 for r in rows if r["label"])
    print(f"seismic samples:   {len(samples)}")
    print(f"detections loaded: {len(detections)}")
    if samples:
        span = samples[-1].mpu_wall_s - samples[0].mpu_wall_s
        print(f"seismic span:      {span:.1f}s")
    if detections:
        labels = sorted({d.label for d in detections})
        print(f"detection labels:  {', '.join(labels)}")
    if rows:
        pct = 100.0 * positives / len(rows)
        print(f"positive rows:     {positives}/{len(rows)} ({pct:.1f}%)")
    else:
        print("positive rows:     0/0 (no seismic samples to label)")
    if samples and not detections:
        print("note: no detections loaded - every row will be labelled 0", file=sys.stderr)
    if not samples:
        print(
            "note: no seismic samples found - nothing to join (geophone unwired?)",
            file=sys.stderr,
        )


def synthesize_demo(window_s: float) -> int:
    """Run the join against small synthetic in-memory logs, to sanity-check this script.

    The real seismic CSV is expected to be empty while the geophone is unwired -
    this is how the join logic gets exercised before the geophone is ever
    wired back up.
    """
    samples = [SeismicSample(float(i), 1000.0 + i * 0.01, 0.001 * (i % 7)) for i in range(50)]
    detections = [
        Detection(wall_s=1000.20, label="Boar", confidence=0.82),
        Detection(wall_s=1000.45, label="Boar", confidence=0.71),
    ]
    rows = join(samples, detections, window_s)
    print_summary(samples, detections, rows)
    return 0


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("seismic_csv", type=Path, nargs="?", help="path to seismic_raw.csv")
    parser.add_argument("detections_jsonl", type=Path, nargs="?", help="path to detections.jsonl")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("joined.csv"),
        help="output CSV path (default: joined.csv)",
    )
    parser.add_argument(
        "--window-s",
        type=float,
        default=2.0,
        help="a detection within +/- window-s/2 of a sample labels it positive (default: 2.0)",
    )
    parser.add_argument(
        "--target-labels",
        default=None,
        help="comma-separated label allowlist (default: all labels count as positive)",
    )
    parser.add_argument(
        "--synthesize-demo",
        action="store_true",
        help="skip file input and run against synthetic data, to sanity-check the join logic",
    )
    args = parser.parse_args()

    if args.synthesize_demo:
        return synthesize_demo(args.window_s)

    if args.seismic_csv is None or args.detections_jsonl is None:
        parser.error(
            "seismic_csv and detections_jsonl are required unless --synthesize-demo is given"
        )

    target_labels = set(args.target_labels.split(",")) if args.target_labels else None

    samples = load_seismic_csv(args.seismic_csv) if args.seismic_csv.exists() else []
    detections = (
        load_detections_jsonl(args.detections_jsonl, target_labels)
        if args.detections_jsonl.exists()
        else []
    )

    rows = join(samples, detections, args.window_s)
    write_output_csv(rows, args.output)
    print_summary(samples, detections, rows)
    print(f"output:            {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
