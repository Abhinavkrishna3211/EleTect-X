#!/usr/bin/env python3
"""Bench-only correlator: stimulus timestamp log x captured [seismic] console log.

For each stimulus window (baseline, each tone, the sweep, the impulse train),
pulls the [seismic] sta/lta/ratio samples whose HOST arrival timestamp falls
inside that window and reports mean/max ratio plus the delta against the
quiet-baseline mean. Also counts real [trigger] threshold-crossing lines
inside each window, as corroborating (not primary) evidence.

This is a chain-health/repeatability check against desk-speaker-coupled
excitation, NOT real footfall data - see docs/KNOWN_GAPS.md's geophone
section. Its output must never be used to set STA_LTA_TRIGGER_RATIO,
STA_LTA_DETRIGGER_RATIO, STA_SAMPLES, or LTA_SAMPLES in config.h.

Usage:
    python correlate_geophone_excitation.py \
        --stimulus bench-logs/stimulus_<ts>.jsonl \
        --capture bench-logs/geophone_excitation_<date>.log
"""
import argparse
import json
import re
import statistics as stats

SEISMIC_RE = re.compile(
    r"\[seismic\] t=(?P<t>\d+) sta=(?P<sta>[-\d.eE+]+) lta=(?P<lta>[-\d.eE+]+) ratio=(?P<ratio>[-\d.eE+]+)"
)
TRIGGER_RE = re.compile(r"\[trigger\] t=(?P<t>\d+)")


def load_stimulus(path: str):
    events = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def load_capture(path: str):
    ratio_samples = []  # (recv_ts, sta, lta, ratio)
    trigger_samples = []  # recv_ts
    unparsed = 0
    total = 0
    with open(path) as f:
        for line in f:
            total += 1
            parts = line.rstrip("\n").split("\t", 1)
            if len(parts) != 2:
                unparsed += 1
                continue
            recv_ts_str, payload = parts
            try:
                recv_ts = float(recv_ts_str)
            except ValueError:
                unparsed += 1
                continue
            m = SEISMIC_RE.search(payload)
            if m:
                ratio_samples.append((recv_ts, float(m.group("sta")), float(m.group("lta")), float(m.group("ratio"))))
                continue
            if TRIGGER_RE.search(payload):
                trigger_samples.append(recv_ts)
    return ratio_samples, trigger_samples, total, unparsed


def window_samples(ratio_samples, start_ts, end_ts):
    return [r for r in ratio_samples if start_ts <= r[0] <= end_ts]


def window_triggers(trigger_samples, start_ts, end_ts):
    return [t for t in trigger_samples if start_ts <= t <= end_ts]


def summarize(samples):
    ratios = [r[3] for r in samples]
    if not ratios:
        return None
    return {
        "n": len(ratios),
        "mean": stats.mean(ratios),
        "max": max(ratios),
        "stdev": stats.pstdev(ratios) if len(ratios) > 1 else 0.0,
    }


def main(stimulus_path: str, capture_path: str) -> None:
    events = load_stimulus(stimulus_path)
    ratio_samples, trigger_samples, total_lines, unparsed = load_capture(capture_path)

    print(f"capture: {total_lines} lines total, {len(ratio_samples)} [seismic] lines, "
          f"{len(trigger_samples)} [trigger] lines, {unparsed} unparsed/non-matching lines")
    print()

    baseline_events = [e for e in events if e["label"] == "baseline_quiet" or e["label"].startswith("quiet_gap")]
    baseline_all = []
    for e in baseline_events:
        baseline_all.extend(window_samples(ratio_samples, e["start_ts"], e["end_ts"]))
    baseline_summary = summarize(baseline_all)

    if baseline_summary is None:
        print("NO baseline [seismic] samples captured in any quiet window - cannot compute deltas. "
              "Check capture log for gaps (see [trigger]-only EVENT/COOLDOWN dead zones caveat).")
        baseline_mean = None
    else:
        baseline_mean = baseline_summary["mean"]
        print(f"BASELINE (all quiet windows combined): n={baseline_summary['n']} "
              f"mean_ratio={baseline_summary['mean']:.4f} max={baseline_summary['max']:.4f} "
              f"stdev={baseline_summary['stdev']:.4f}")
    print()

    rows = []
    for e in events:
        if e["label"] == "baseline_quiet" or e["label"].startswith("quiet_gap"):
            continue
        samples = window_samples(ratio_samples, e["start_ts"], e["end_ts"])
        triggers = window_triggers(trigger_samples, e["start_ts"], e["end_ts"])
        summary = summarize(samples)
        row = {"label": e["label"], "freq_hz": e.get("freq_hz"), "summary": summary,
               "n_triggers": len(triggers), "window_s": e["end_ts"] - e["start_ts"]}
        rows.append(row)

        if summary is None:
            print(f"{e['label']:30s}  NO [seismic] samples in window ({row['window_s']:.1f}s) - "
                  f"dead zone (likely EVENT/COOLDOWN blanking, see caveat) or capture gap.")
            continue

        delta = (summary["mean"] - baseline_mean) if baseline_mean is not None else float("nan")
        noise_floor = baseline_summary["stdev"] if baseline_summary else 0.0
        discernible = abs(delta) > 2 * noise_floor if baseline_summary else None
        flag = "" if discernible else "  <-- NO DISCERNIBLE RESPONSE vs baseline noise floor"
        print(f"{e['label']:30s}  n={summary['n']:3d}  mean={summary['mean']:.4f}  "
              f"max={summary['max']:.4f}  delta_vs_baseline={delta:+.4f}  "
              f"triggers={len(triggers)}{flag}")

    print()
    print("Reminder: this is a desk-speaker-coupled excitation check (chain-health/repeatability), "
          "not real footfall data. Do not use these numbers to set STA_LTA_TRIGGER_RATIO, "
          "STA_LTA_DETRIGGER_RATIO, STA_SAMPLES, or LTA_SAMPLES.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stimulus", required=True)
    parser.add_argument("--capture", required=True)
    args = parser.parse_args()
    main(args.stimulus, args.capture)
