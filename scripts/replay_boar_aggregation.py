#!/usr/bin/env python3
"""Replay a continuous edge-impulse-linux-runner log against ADR 0022's
per-poll vision watch, to measure what VISION_SPECIES_CONSECUTIVE_POLLS
actually buys against a real board run rather than a synthetic pass rate.

Written for the 30 Aug 2-hour live monitoring log
(/home/arduino/monitor_2h_20260830.log, 138.5MB, 1,169,788 lines, 40,422
classified frames across 13 runner-restart chunks - see
ml/vision/README.md's "30 Aug - 2-hour live monitoring" entry, which
reports the baseline this script's Metric A must reproduce: 12,747/40,422
frames (31.53%) carried a Boar box, zero carried an Elephant box).

Run this ON THE BOARD, over SSH - the log is too large to copy down and
this script needs nothing the board doesn't already have (Python 3
stdlib only, no repo import):

    ssh arduino@192.168.1.10
    python3 replay_boar_aggregation.py /home/arduino/monitor_2h_20260830.log

Methodology - three metrics, not one, because none of them alone answers
the question honestly:

  A. Frame baseline: the published number, reproduced as a sanity check.
     Just the share of classified frames carrying a Boar box.

  B. Per-frame N>=2: the same consecutive-count debounce applied directly
     to individual log frames (ignoring bursts and poll pacing entirely),
     reported as a share of frames so it is directly comparable in shape
     to Metric A. This answers "how much does requiring two-in-a-row
     buy, at the finest grain the log can express" - it is NOT what
     production does (production polls, it does not evaluate every raw
     frame), but it isolates the debounce's effect from the burst-OR
     question below.

  C. Production-faithful: what _watch_for_vision actually does. A poll is
     FRAME_COUNT (3) consecutive log frames, OR'd together (positive if
     ANY of the 3 has a Boar box - this is _vision_check's real
     semantics, not an approximation of it). Polls are sampled every
     ~POLL_INTERVAL_S (1.0s) of log time, derived per chunk from that
     chunk's own real frames-per-second (duration / frame count) rather
     than an assumed constant, since FPS is not guaranteed uniform across
     chunks. VISION_SPECIES_CONSECUTIVE_POLLS["Boar"] = 2 consecutive
     positive polls are then required, same run-length logic as Metric B
     but applied to polls instead of frames.

     Metric C's own "before" number (the poll-level baseline, before the
     N>=2 requirement) is reported too, because burst-OR can *amplify*
     the frame rate: if frame positives were independent, a 3-frame OR
     poll would be positive ~1-(1-0.3153)^3 ~= 68%, worse than the frame
     rate it started from. Real Boar false positives are spatially
     clustered on fixed background anchors (see the README's own
     analysis), so they are almost certainly correlated rather than
     independent and the true number should come in well under that -
     but this must be measured on the real log, not assumed, which is
     why both the pre- and post-debounce poll rates are reported
     side by side.

Also reported: the same three metrics for Elephant (expected 0% at every
stage - the no-op guard that this change costs Elephant nothing), and the
per-chunk spread for both baseline and production-faithful Boar rates
(the README documents per-chunk swings from 1.2% to 73.9% at the frame
level; this script shows whether that swing survives at the poll level
too).

FRAME_COUNT, POLL_INTERVAL_S and BOAR_REQUIRED_STREAK below are literal
copies of device/mpu/services/config.py's VISION_CHECK_FRAME_COUNT,
VISION_WATCH_POLL_INTERVAL_S and VISION_SPECIES_CONSECUTIVE_POLLS["Boar"]
- copied rather than imported so this script has zero dependencies and
runs standalone on the board with no PYTHONPATH setup. If those
constants change, update these three lines to match.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime

FRAME_COUNT = 3  # services/config.py VISION_CHECK_FRAME_COUNT
POLL_INTERVAL_S = 1.0  # services/config.py VISION_WATCH_POLL_INTERVAL_S
BOAR_REQUIRED_STREAK = 2  # services/config.py VISION_SPECIES_CONSECUTIVE_POLLS["Boar"]

CHUNK_START_RE = re.compile(r"^=== CHUNK (\d+) START (\S+) ===")
CHUNK_END_RE = re.compile(r"^=== CHUNK (\d+) END (\S+) ===")
BOXES_RE = re.compile(r"^boundingBoxes\s+\d+ms\.\s+(\[.*\])\s*$")


@dataclass
class ChunkFrames:
    """One runner-restart chunk's frames, in log order.

    boar[i]/elephant[i] are whether frame i's boundingBoxes array carried
    that label - the runner has already applied its own min_score
    threshold before a box is emitted, so presence in the array is
    exactly the production-equivalent per-frame positive/negative call.
    """

    chunk_id: int
    start_iso: str
    end_iso: str = ""
    boar: list[bool] = field(default_factory=list)
    elephant: list[bool] = field(default_factory=list)

    def duration_s(self) -> float:
        start = datetime.fromisoformat(self.start_iso)
        end = datetime.fromisoformat(self.end_iso)
        return (end - start).total_seconds()


def parse_log(path: str) -> list[ChunkFrames]:
    chunks: list[ChunkFrames] = []
    current: ChunkFrames | None = None
    with open(path, "r", errors="replace") as f:
        for line in f:
            m = CHUNK_START_RE.match(line)
            if m:
                current = ChunkFrames(chunk_id=int(m.group(1)), start_iso=m.group(2))
                continue
            m = CHUNK_END_RE.match(line)
            if m and current is not None:
                current.end_iso = m.group(2)
                chunks.append(current)
                current = None
                continue
            m = BOXES_RE.match(line)
            if m and current is not None:
                boxes = json.loads(m.group(1))
                labels = {b["label"] for b in boxes}
                current.boar.append("Boar" in labels)
                current.elephant.append("Elephant" in labels)
    if current is not None:
        # A chunk with a START but no END (log truncated mid-run). Keep its
        # frames but flag it rather than silently dropping or mis-timing it.
        print(
            f"warning: chunk {current.chunk_id} has no END marker - "
            f"{len(current.boar)} frames kept, excluded from duration/FPS math",
            file=sys.stderr,
        )
    return chunks


def _admitted_run_share(flags: list[bool], required: int) -> tuple[int, int]:
    """Share of `flags` belonging to a run of >=`required` consecutive True.

    Same run-length logic _watch_for_vision's streak counters express
    (a label is admitted once its consecutive-positive streak reaches
    `required`), applied here to a flat sequence rather than one watch
    window, and reported per-element so it is directly comparable in
    shape to a flat positive rate. Returns (admitted_count, total_count).
    """
    n = len(flags)
    admitted = 0
    i = 0
    while i < n:
        if flags[i]:
            j = i
            while j < n and flags[j]:
                j += 1
            if (j - i) >= required:
                admitted += j - i
            i = j
        else:
            i += 1
    return admitted, n


def _poll_positives(flags: list[bool], stride: int, majority: bool = False) -> list[bool]:
    """Polls of FRAME_COUNT consecutive frames, sampled every `stride`.

    majority=False reproduces _vision_check's real semantics: OR across the
    burst (any qualifying box in any of the 3 frames). majority=True is the
    plan's named alternative if OR turns out to be the problem, not the
    debounce - requires at least a majority (2 of 3) of the burst's frames
    to be positive, not production behaviour today.
    """
    n = len(flags)
    polls = []
    i = 0
    while i < n:
        burst = flags[i : i + FRAME_COUNT]
        if majority:
            polls.append(sum(burst) * 2 > len(burst))
        else:
            polls.append(any(burst))
        i += stride
    return polls


def _rate(numerator: int, denominator: int) -> float:
    return (numerator / denominator * 100.0) if denominator else 0.0


def _chunk_stride(chunk: ChunkFrames) -> int:
    n = len(chunk.boar)
    if n < 2 or not chunk.end_iso:
        return max(1, round(POLL_INTERVAL_S * 5.52))  # README's measured average FPS, fallback
    duration_s = chunk.duration_s()
    if duration_s <= 0:
        return max(1, round(POLL_INTERVAL_S * 5.52))
    fps = n / duration_s
    return max(1, round(POLL_INTERVAL_S * fps))


def summarize(chunks: list[ChunkFrames]) -> None:
    all_boar: list[bool] = []
    all_elephant: list[bool] = []
    all_boar_polls: list[bool] = []
    all_elephant_polls: list[bool] = []

    print(f"{'chunk':>5}  {'frames':>7}  {'stride':>6}  "
          f"{'baseline%':>10}  {'frame N>=2%':>12}  "
          f"{'poll baseline%':>15}  {'poll N>=2%':>11}")

    all_boar_polls_majority: list[bool] = []

    for c in chunks:
        stride = _chunk_stride(c)
        boar_polls = _poll_positives(c.boar, stride)
        elephant_polls = _poll_positives(c.elephant, stride)
        boar_polls_majority = _poll_positives(c.boar, stride, majority=True)

        all_boar.extend(c.boar)
        all_elephant.extend(c.elephant)
        all_boar_polls.extend(boar_polls)
        all_elephant_polls.extend(elephant_polls)
        all_boar_polls_majority.extend(boar_polls_majority)

        base_pct = _rate(sum(c.boar), len(c.boar))
        frame_admitted, frame_n = _admitted_run_share(c.boar, BOAR_REQUIRED_STREAK)
        frame_n2_pct = _rate(frame_admitted, frame_n)
        poll_base_pct = _rate(sum(boar_polls), len(boar_polls))
        poll_admitted, poll_n = _admitted_run_share(boar_polls, BOAR_REQUIRED_STREAK)
        poll_n2_pct = _rate(poll_admitted, poll_n)

        print(
            f"{c.chunk_id:>5}  {len(c.boar):>7}  {stride:>6}  "
            f"{base_pct:>9.2f}%  {frame_n2_pct:>11.2f}%  "
            f"{poll_base_pct:>14.2f}%  {poll_n2_pct:>10.2f}%"
        )

    print()
    print("=== Overall (all 13 chunks, %d frames) ===" % len(all_boar))

    base_admitted, base_n = sum(all_boar), len(all_boar)
    print(f"A. Frame baseline (any Boar box):            "
          f"{base_admitted}/{base_n} = {_rate(base_admitted, base_n):.2f}%")

    fa, fn = _admitted_run_share(all_boar, BOAR_REQUIRED_STREAK)
    print(f"B. Per-frame N>=2 (share of frames in a run "
          f">= {BOAR_REQUIRED_STREAK}): {fa}/{fn} = {_rate(fa, fn):.2f}%")

    pb, pn = sum(all_boar_polls), len(all_boar_polls)
    print(f"C0. Production-faithful poll baseline "
          f"(burst-OR, pre-debounce):    {pb}/{pn} = {_rate(pb, pn):.2f}%")

    pa, pn2 = _admitted_run_share(all_boar_polls, BOAR_REQUIRED_STREAK)
    print(f"C.  Production-faithful N>=2 (poll streak "
          f">= {BOAR_REQUIRED_STREAK}):     {pa}/{pn2} = {_rate(pa, pn2):.2f}%")

    print()
    print("=== Named alternative: within-burst majority (2-of-3), not production today ===")
    mb, mn = sum(all_boar_polls_majority), len(all_boar_polls_majority)
    print(f"D0. Majority-burst poll baseline (pre-debounce):  "
          f"{mb}/{mn} = {_rate(mb, mn):.2f}%")
    ma, man = _admitted_run_share(all_boar_polls_majority, BOAR_REQUIRED_STREAK)
    print(f"D.  Majority-burst + N>=2 poll debounce:          "
          f"{ma}/{man} = {_rate(ma, man):.2f}%")

    print()
    print("=== Elephant no-op guard (expect 0% at every stage) ===")
    eb, en = sum(all_elephant), len(all_elephant)
    print(f"A. Frame baseline:              {eb}/{en} = {_rate(eb, en):.2f}%")
    efa, efn = _admitted_run_share(all_elephant, 1)  # Elephant's required streak is 1
    print(f"B. Per-frame N>=1 (no-op check): {efa}/{efn} = {_rate(efa, efn):.2f}%")
    epb, epn = sum(all_elephant_polls), len(all_elephant_polls)
    print(f"C0. Poll baseline:               {epb}/{epn} = {_rate(epb, epn):.2f}%")
    epa, epn2 = _admitted_run_share(all_elephant_polls, 1)
    print(f"C.  Production-faithful N>=1:    {epa}/{epn2} = {_rate(epa, epn2):.2f}%")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "log_path",
        nargs="?",
        default="/home/arduino/monitor_2h_20260830.log",
        help="Path to the continuous monitoring log (default: the 30 Aug board log path)",
    )
    args = parser.parse_args()

    chunks = parse_log(args.log_path)
    if not chunks:
        print(f"no complete CHUNK ... START/END pairs found in {args.log_path}", file=sys.stderr)
        return 1

    summarize(chunks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
