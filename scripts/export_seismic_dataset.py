"""Turn a node's camera-labelled seismic records into a trainable dataset.

Records come off a node on a site visit as one JSON file per encounter, under
a bucket directory naming what the camera made of it (ADR 0035). That shape is
right for a device that writes one file at a time and evicts under a cap; it
is the wrong shape for training anything. This script is the bridge.

Four things it does that a shell loop over the files would get wrong:

**It refuses a corpus it does not understand.** Every record carries a schema
number. A record from a newer node than this script is skipped and counted,
never silently half-read - the way a corpus acquires a column that means two
different things in two halves of itself.

**It cuts to the clean segment by default.** The horn and the geophone share
one structure, so every record of a confirmed animal contains the node's own
deterrent and every negative record does not. Train on that and the model
learns to detect the horn. `--clean-only` (the default) exports only the
samples before the first actuator fired; `--whole-record` is there for
studying the contamination itself.

**It re-derives rather than trusting.** Ranges, gait and behaviour in a stored
record were computed by the node's version of perception/kinematics.py against
whatever calibration it had. `--recalibrate` recomputes all of it from the
stored boxes and the stored waveform - which is the entire reason those raw
halves are kept.

**It writes one manifest for everything.** One row per exported record, so a
training script joins on a CSV rather than walking a directory and parsing
filenames.

Off-device: this runs on a laptop and may use numpy and the standard library
freely. device/mpu stays dependency-free; the import below reaches into it for
the record shape rather than duplicating it, because two definitions of a
corpus format is how the halves drift.

Usage:
    python scripts/export_seismic_dataset.py --root <pulled-dataset-dir> --out <dir>
    python scripts/export_seismic_dataset.py --root data/ --out out/ --bucket elephant
    python scripts/export_seismic_dataset.py --root data/ --out out/ \\
        --recalibrate device/mpu/data/camera_calibration.json --format manifest wav npy
"""

import argparse
import base64
import csv
import json
import os
import struct
import sys
import wave
from datetime import datetime, timezone

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.insert(0, os.path.join(ROOT, "device", "mpu"))

from perception import kinematics, seismic_dataset  # noqa: E402
from perception.seismic_stream import SeismicGap, SeismicSlice  # noqa: E402

# The highest schema this script knows how to read. Raised deliberately, in
# the same commit as whatever change to the record shape it covers.
MAX_SCHEMA = seismic_dataset.SCHEMA

MANIFEST_COLUMNS = (
    "record",
    "bucket",
    "source",
    "calibrated",
    "schema",
    "wall_time",
    "node_scope",
    "sta_lta_ratio",
    "mcu_probability",
    "seismic_available",
    "geophone_ok",
    "sample_rate_hz",
    "samples_total",
    "samples_exported",
    "missing_samples",
    "actuator_contaminated",
    "vision_polls",
    "could_see",
    "illuminated",
    "species_seen",
    "impact_count",
    "cadence_hz",
    "interval_mean_s",
    "interval_cv",
    "peak_max_counts",
    "direction",
    "relative_range",
    "median_range_m",
    "range_band",
    "motion",
    "speed_agreement",
    "vision_speed_mps",
    "seismic_speed_mps",
    "retreated",
)


def decode_counts(seismic):
    """The waveform back as a list of ints, or None.

    The encoding is named in the record rather than assumed, so an export
    against a future encoding fails loudly here instead of producing
    plausible noise.
    """
    if not seismic or not seismic.get("samples"):
        return None
    encoding = seismic.get("encoding")
    if encoding != "base64:int16le":
        raise ValueError(f"unknown waveform encoding {encoding!r}")
    raw = base64.b64decode(seismic["samples"])
    return list(struct.unpack(f"<{len(raw) // 2}h", raw))


def clean_cut(record, counts):
    """How many leading samples precede the first actuator fire.

    Everything before the fire; not "everything the actuator did not
    overlap". The horn rings after it stops, so the samples following a
    fire are suspect even where nothing was nominally driving.
    """
    seismic = record.get("seismic") or {}
    first_index = seismic.get("first_sample_index")
    starts = [
        a.get("start_index")
        for a in record.get("actuators", ())
        if a.get("start_index") is not None
    ]
    if first_index is None or not starts:
        return len(counts)
    return max(0, min(len(counts), min(starts) - first_index))


def rebuild_record(payload):
    """A SeismicRecord from a stored dict, for re-deriving against it.

    Only the fields derivation reads - the boxes, the waveform and the
    actuator spans. Everything else is carried through from the stored
    JSON, so this is a recomputation and not a reinterpretation.
    """
    seismic = payload.get("seismic")
    counts = decode_counts(seismic)
    slice_ = None
    if counts is not None:
        gaps = tuple(
            SeismicGap(g["start_index"], g["count"])
            for g in seismic.get("gaps", ())
        )
        slice_ = SeismicSlice(
            first_sample_index=seismic.get("first_sample_index", 0),
            counts=tuple(counts),
            gaps=gaps,
            geophone_ok=bool(seismic.get("geophone_ok", True)),
            lsb_volts=seismic.get("lsb_volts", 0.0),
        )
    vision = payload.get("vision", {})
    track = tuple(
        seismic_dataset.TrackFrame(
            poll=f["poll"],
            frame_index=f["frame_index"],
            timestamp_s=f["timestamp_s"],
            sample_index=f.get("sample_index"),
            boxes=tuple(
                seismic_dataset.TrackBox(
                    label=b["label"],
                    confidence=b["confidence"],
                    x=b["x"],
                    y=b["y"],
                    width=b["width"],
                    height=b["height"],
                )
                for b in f.get("boxes", ())
            ),
        )
        for f in vision.get("track", ())
    )
    actuators = tuple(
        seismic_dataset.ActuatorSpan(
            actuator=a["actuator"],
            start_monotonic_s=a["start_monotonic_s"],
            end_monotonic_s=a["end_monotonic_s"],
            start_index=a.get("start_index"),
            count=a.get("count", 0),
        )
        for a in payload.get("actuators", ())
    )
    event = payload.get("event", {})
    label = payload.get("label", {})
    return seismic_dataset.SeismicRecord(
        bucket=label.get("bucket", "unlabelled"),
        source=label.get("source", ""),
        event_wall_s=event.get("wall_s", 0.0),
        event_monotonic_s=event.get("monotonic_s", 0.0),
        node_scope=payload.get("node_scope", ""),
        sta_lta_ratio=event.get("sta_lta_ratio", 0.0),
        mcu_probability=event.get("mcu_probability", 0.0),
        feature_vector=tuple(event.get("feature_vector", ())),
        seismic_available=bool(event.get("seismic_available", False)),
        seismic=slice_,
        track=track,
        actuators=actuators,
        vision_polls=vision.get("polls", 0),
        vision_watch_s=vision.get("watch_s", 0.0),
        confirmed_on_poll=vision.get("confirmed_on_poll"),
        species_seen=tuple(vision.get("species_seen", ())),
        illuminated=bool(vision.get("illuminated", False)),
        could_see=bool(vision.get("could_see", False)),
        schema=payload.get("schema", 0),
    )


def primary_range(derived, species_seen):
    """The range track for the confirmed species, for the manifest row.

    A record may hold several; the manifest has one set of columns. The
    confirmed species is the one the row is about - with none confirmed,
    there is no honest choice and the columns stay empty.
    """
    ranges = derived.get("ranges") or []
    if len(species_seen) == 1:
        for track in ranges:
            if track["label"] == species_seen[0]:
                return track
    return None


def manifest_row(path, payload, exported_samples, clean):
    """One flat row describing one exported record."""
    label = payload.get("label", {})
    event = payload.get("event", {})
    seismic = payload.get("seismic") or {}
    vision = payload.get("vision", {})
    derived = payload.get("derived", {}) or {}
    gait = derived.get("gait") or {}
    behaviour = derived.get("behaviour") or {}
    retreat = derived.get("retreat") or {}
    species_seen = list(vision.get("species_seen", ()))
    ranged = primary_range(derived, species_seen) or {}
    wall = event.get("wall_s")
    return {
        "record": os.path.basename(path),
        "bucket": label.get("bucket", ""),
        "source": label.get("source", ""),
        "calibrated": label.get("calibrated", ""),
        "schema": payload.get("schema", ""),
        "wall_time": (
            datetime.fromtimestamp(wall, tz=timezone.utc).isoformat() if wall else ""
        ),
        "node_scope": payload.get("node_scope", ""),
        "sta_lta_ratio": event.get("sta_lta_ratio", ""),
        "mcu_probability": event.get("mcu_probability", ""),
        "seismic_available": event.get("seismic_available", ""),
        "geophone_ok": seismic.get("geophone_ok", ""),
        "sample_rate_hz": seismic.get("sample_rate_hz_nominal", ""),
        "samples_total": seismic.get("sample_count", 0),
        "samples_exported": exported_samples,
        "missing_samples": seismic.get("missing_samples", 0),
        # True when the exported span still contains a fire. With --clean-only
        # this is the flag that says the cut did not fully protect the row.
        "actuator_contaminated": bool(payload.get("actuators")) and not clean,
        "vision_polls": vision.get("polls", 0),
        "could_see": vision.get("could_see", ""),
        "illuminated": vision.get("illuminated", ""),
        "species_seen": "|".join(species_seen),
        "impact_count": gait.get("impact_count", ""),
        "cadence_hz": gait.get("cadence_hz", ""),
        "interval_mean_s": gait.get("interval_mean_s", ""),
        "interval_cv": gait.get("interval_cv", ""),
        "peak_max_counts": gait.get("peak_max_counts", ""),
        "direction": ranged.get("direction", ""),
        "relative_range": ranged.get("relative_range", ""),
        "median_range_m": ranged.get("median_range_m", ""),
        "range_band": ranged.get("range_band", ""),
        "motion": behaviour.get("motion", ""),
        "speed_agreement": behaviour.get("agreement", ""),
        "vision_speed_mps": behaviour.get("vision_speed_mps", ""),
        "seismic_speed_mps": behaviour.get("seismic_speed_mps", ""),
        # Stays blank for an undetermined verdict rather than reading False.
        "retreated": "" if retreat.get("retreated") is None else retreat["retreated"],
    }


def write_wav(path, counts, rate):
    """16-bit mono PCM at the nominal rate, for listening and for librosa.

    The rate is nominal (250 Hz against a measured ~227 Hz), so a WAV is a
    convenience view and the manifest's sample counts are the truth. A
    player that will not open 250 Hz is not a reason to resample here -
    resampling in the exporter would make the corpus and the WAVs disagree.
    """
    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(int(rate))
        fh.writeframes(struct.pack(f"<{len(counts)}h", *counts))


def write_csv(path, counts):
    """One sample per line, index and count - the no-dependency view."""
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(("sample_index", "counts"))
        writer.writerows(enumerate(counts))


def write_npy(path, counts):
    """int16 array for a training script; numpy is optional, not required."""
    import numpy as np

    np.save(path, np.asarray(counts, dtype="<i2"))


def export(args):
    """Walk the corpus, write what was asked for, and report what was skipped."""
    optics = None
    if args.recalibrate:
        optics = kinematics.load_optics(args.recalibrate)
        if not optics.calibrated:
            print(f"warning: {args.recalibrate} is not a usable calibration; "
                  f"falling back to the nominal focal length")

    formats = set(args.format)
    os.makedirs(args.out, exist_ok=True)
    rows = []
    skipped_schema = 0
    skipped_bucket = 0
    skipped_window = 0
    unreadable = 0
    no_waveform = 0

    for dirpath, _dirnames, filenames in sorted(os.walk(args.root)):
        bucket = os.path.basename(dirpath)
        if args.bucket and bucket not in args.bucket:
            skipped_bucket += sum(1 for f in filenames if f.endswith(".json"))
            continue
        for name in sorted(filenames):
            if not name.endswith(".json"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, ValueError) as exc:
                print(f"skip {path}: unreadable ({exc})")
                unreadable += 1
                continue

            schema = payload.get("schema", 0)
            if schema > MAX_SCHEMA:
                # Never half-read. A column that means two things in two
                # halves of a corpus is worse than a missing record.
                print(f"skip {path}: schema {schema} is newer than {MAX_SCHEMA}")
                skipped_schema += 1
                continue

            wall = (payload.get("event") or {}).get("wall_s", 0.0)
            if args.since and wall < args.since:
                skipped_window += 1
                continue
            if args.until and wall >= args.until:
                skipped_window += 1
                continue

            if optics is not None or args.rederive:
                payload = seismic_dataset.with_derived(
                    rebuild_record(payload), optics
                ).to_dict()

            counts = decode_counts(payload.get("seismic"))
            if counts is None:
                no_waveform += 1
                rows.append(manifest_row(path, payload, 0, clean=True))
                continue

            clean = True
            if args.clean_only:
                cut = clean_cut(payload, counts)
                clean = cut == len(counts) or cut > 0
                counts = counts[:cut]
            rows.append(manifest_row(path, payload, len(counts), clean))

            if not counts:
                continue
            stem = os.path.join(args.out, f"{bucket}__{os.path.splitext(name)[0]}")
            rate = (payload.get("seismic") or {}).get("sample_rate_hz_nominal", 250)
            if "wav" in formats:
                write_wav(stem + ".wav", counts, rate)
            if "csv" in formats:
                write_csv(stem + ".csv", counts)
            if "npy" in formats:
                write_npy(stem + ".npy", counts)

    if "manifest" in formats:
        manifest = os.path.join(args.out, "manifest.csv")
        with open(manifest, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"manifest: {manifest}")

    by_bucket = {}
    for row in rows:
        by_bucket[row["bucket"]] = by_bucket.get(row["bucket"], 0) + 1
    print(f"exported {len(rows)} record(s) to {args.out}")
    for bucket in sorted(by_bucket):
        print(f"  {bucket}: {by_bucket[bucket]}")
    if no_waveform:
        print(f"  ({no_waveform} with no waveform - vision half only)")
    for count, why in (
        (skipped_schema, "newer schema"),
        (skipped_bucket, "bucket not requested"),
        (skipped_window, "outside the time window"),
        (unreadable, "unreadable"),
    ):
        if count:
            print(f"skipped {count}: {why}")
    return 0


def parse_time(value):
    """An ISO-8601 instant or a bare epoch second, as an epoch float."""
    try:
        return float(value)
    except ValueError:
        return datetime.fromisoformat(value).timestamp()


def main(argv=None):
    """Parse arguments and run the export."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", required=True,
                        help="the pulled dataset directory (the one holding elephant/, "
                             "no_animal/, unlabelled/ ...)")
    parser.add_argument("--out", required=True, help="where to write the export")
    parser.add_argument("--bucket", nargs="*", default=(),
                        help="only these buckets (default: all)")
    parser.add_argument("--since", type=parse_time, default=None,
                        help="only records at or after this time")
    parser.add_argument("--until", type=parse_time, default=None,
                        help="only records before this time")
    parser.add_argument("--format", nargs="+", default=["manifest"],
                        choices=["manifest", "wav", "csv", "npy"],
                        help="what to write per record (default: manifest only)")
    clean = parser.add_mutually_exclusive_group()
    clean.add_argument("--clean-only", dest="clean_only", action="store_true",
                       default=True,
                       help="export only the samples before the first actuator fired "
                            "(the default)")
    clean.add_argument("--whole-record", dest="clean_only", action="store_false",
                       help="export the full waveform, deterrent included - for "
                            "studying the contamination, not for training")
    parser.add_argument("--recalibrate", default=None,
                        help="re-derive ranges, gait and behaviour using this "
                             "camera_calibration.json")
    parser.add_argument("--rederive", action="store_true",
                        help="re-derive with the nominal optics, e.g. after a change "
                             "to the impact detector")
    return export(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
