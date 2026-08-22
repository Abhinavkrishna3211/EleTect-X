"""Upload real bench-captured geophone windows to Edge Impulse as training data.

Extracts the 12 genuine 512-sample raw-volt windows captured during the 14/15
Aug stomp sessions (scripts/bench-logs/stomp_test_20260814_verbose.log and
stomp_protocol_20260815.log) and splits each into two real, honestly-labeled
segments:

  - "quiet": the first 128 samples (512ms) of the window - real pre-event
    ambient signal, confirmed clear of the transient in every captured case
    (every logged trigger's idx field is 511, meaning the transient sits at
    the very last sample of the window, never earlier).
  - "footfall": the last 64 samples (256ms) up to and including the trigger
    sample - the real captured stomp transient.

This is a small, honest proof-of-concept dataset (n=12 per class), not a
field-validated one - report it as such. No synthetic or fabricated data is
generated; every value here is a real geophone reading from the 14/15 Aug
bench sessions (see docs/KNOWN_GAPS.md's stomp-test entries).

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1094084
    python scripts\\edge_impulse_upload_seismic.py

scripts/bench-logs/ is gitignored, so the raw session logs are not in a fresh
clone. The same 12 windows are committed verbatim as
ml/seismic/bench_windows_20260814_15.json, and this script falls back to that
artifact when the logs are absent - so the dataset behind the reported accuracy
is reproducible by anyone with the repo, not only on the machine that captured it.

Requires only the standard library - no pip install needed.
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

INGEST = "https://ingestion.edgeimpulse.com/api"
BENCH_LOG_DIR = os.path.join(os.path.dirname(__file__), "bench-logs")
SOURCE_FILES = ["stomp_protocol_20260815.log", "stomp_test_20260814_verbose.log"]
FROZEN_DATASET = os.path.join(
    os.path.dirname(__file__), os.pardir, "ml", "seismic", "bench_windows_20260814_15.json"
)

QUIET_LEN = 128
FOOTFALL_LEN = 64


def load_frozen_windows():
    """Read the committed copy of the same 12 windows the logs hold.

    Same shape parse_windows() returns, so build_samples() cannot tell the two
    apart. The artifact was generated from these exact logs, and each event
    carries the sha256 of its own comma-joined values so a reader can check
    the committed numbers against a re-capture rather than trust the file.
    """
    with open(FROZEN_DATASET) as fh:
        doc = json.load(fh)
    return [
        {
            "source": e["source_log"],
            "t_ms": e["t_ms"],
            "rate_hz": e["rate_hz"],
            "idx": e["trigger_idx"],
            "ratio": e["trigger_ratio"],
            "values": e["values_v"],
        }
        for e in doc["events"]
    ]


def parse_windows():
    if not all(os.path.exists(os.path.join(BENCH_LOG_DIR, f)) for f in SOURCE_FILES):
        print(f"bench-logs/ not present - reading frozen dataset {FROZEN_DATASET}")
        return load_frozen_windows()
    events = []
    for fname in SOURCE_FILES:
        path = os.path.join(BENCH_LOG_DIR, fname)
        with open(path) as fh:
            lines = fh.readlines()
        for i, line in enumerate(lines):
            if "[window]" not in line:
                continue
            hdr = re.search(r"t=(\d+) n=(\d+) rate_hz=(\d+)", line)
            t_ms, n, rate_hz = int(hdr.group(1)), int(hdr.group(2)), int(hdr.group(3))
            idx, ratio = None, None
            for j in range(i - 1, max(0, i - 5), -1):
                if "[trigger]" in lines[j]:
                    tm = re.search(r"ratio=([\d.]+) idx=(\d+)", lines[j])
                    if tm:
                        ratio, idx = float(tm.group(1)), int(tm.group(2))
                    break
            raw_csv = lines[i + 1].strip().split("\t")[-1]
            vals = [float(x) for x in raw_csv.split(",")]
            assert len(vals) == n, f"{fname}: expected {n} samples, got {len(vals)}"
            events.append(
                {"source": fname, "t_ms": t_ms, "rate_hz": rate_hz, "idx": idx, "ratio": ratio, "values": vals}
            )
    return events


def build_samples(events):
    samples = []
    for k, e in enumerate(events):
        vals = e["values"]
        idx = e["idx"] if e["idx"] is not None else len(vals) - 1
        quiet_seg = vals[0:QUIET_LEN]
        start = max(0, idx + 1 - FOOTFALL_LEN)
        footfall_seg = vals[start : idx + 1]
        category = "training" if k < 9 else "testing"
        samples.append(("quiet", f"{e['source']}_{e['t_ms']}_quiet.json", quiet_seg, e["rate_hz"], category))
        samples.append(
            ("footfall", f"{e['source']}_{e['t_ms']}_footfall.json", footfall_seg, e["rate_hz"], category)
        )
    return samples


def upload(api_key, samples):
    ok, failed = 0, []
    for label, fname, seg, rate_hz, category in samples:
        payload = {
            "protected": {"ver": "v1", "alg": "none", "iat": int(time.time())},
            "signature": "empty",
            "payload": {
                "device_name": "eletect-x-bench-sm24",
                "device_type": "SM24-INA333-ADS1115-bench",
                "interval_ms": round(1000.0 / rate_hz, 4),
                "sensors": [{"name": "geophone_v", "units": "v"}],
                "values": [[v] for v in seg],
            },
        }
        req = urllib.request.Request(
            f"{INGEST}/{category}/data",
            data=json.dumps(payload).encode(),
            method="POST",
            headers={
                "x-api-key": api_key,
                "x-label": label,
                "x-file-name": fname,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req) as resp:
                resp.read()
                ok += 1
                print(f"  [{category}] {label:9s} {fname} -> uploaded")
        except urllib.error.HTTPError as err:
            failed.append((fname, err.code, err.read().decode()))
            print(f"  [{category}] {label:9s} {fname} -> FAILED {err.code}")
    return ok, failed


def main():
    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    if not api_key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID environment variables first.", file=sys.stderr)
        sys.exit(1)

    events = parse_windows()
    print(f"Parsed {len(events)} real captured windows from bench logs:")
    for e in events:
        print(f"  {e['source']} t={e['t_ms']}ms idx={e['idx']} ratio={e['ratio']}")

    samples = build_samples(events)
    print(f"\nUploading {len(samples)} samples ({len(events)} quiet + {len(events)} footfall)...")
    ok, failed = upload(api_key, samples)

    print(f"\n{ok}/{len(samples)} uploaded successfully.")
    if failed:
        print("Failures:")
        for f in failed:
            print(" ", f)
        sys.exit(1)
    print(f"\nCheck the result at https://studio.edgeimpulse.com/studio/{project_id}/acquisition/training")


if __name__ == "__main__":
    main()
