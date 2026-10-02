"""Cut training clips from the Stefanakis/Astaras long-range chainsaw corpus.

Why this source. The 2026-09-23 recording-level evaluation put `chainsaw` at
77.9% recall against 94-95% for the other three classes, and three independent
checks said the shortfall is in the data, not the model: an 81M-parameter
AudioSet-pretrained backbone and a 2-conv net from scratch score it identically,
+254 AudioSet chainsaw recordings moved it -1.1 points, and no decision
threshold reaches 85% recall without precision collapsing. The confusion matrix
says where it actually goes - 11.5% of chainsaw is called `ambient` and 10.6%
`gunshot`. The `ambient` half is quiet, distant cutting, and every chainsaw
recording the corpus holds today is a close-mic Freesound or ESC-50 clip of a
saw running in the foreground. The model has never heard a chainsaw at range.

This corpus is that missing distribution, and it matches the deployment almost
exactly:

    * recorded on Cornell SWIFT autonomous recording units left in forest -
      the same modality as an EleTect-X node, not a handheld or a studio mic
    * 8 kHz native, which is the locked impulse's sample rate, so nothing is
      resampled into or out of the training set
    * the paper it accompanies is explicitly about *long-range* detection
      (Stefanakis, Psaroulakis, Simou, Astaras, "An open-access system for
      long-range chainsaw sound detection", EUSIPCO 2022)
    * events are marked in TextGrid files by human listeners, so the label is a
      timestamp on real audio rather than an uploader's tag - which is the
      failure mode caveat 4 records for Freesound

The non-event stretches matter as much as the events. They are hours of real
forest ambience captured by the same recorder in the same place, so they attack
the chainsaw/ambient confusion from both sides instead of only adding positives.

Licensing. CC-BY-4.0 (Zenodo record 5824433) - redistributable with attribution,
unlike the AudioSet segments (YouTube terms) and the HiruDewmi elephant corpus
(no stated license). This is the first chainsaw source in the project that
carries no licensing caveat at all.

Deduplication. `RP3_0h30_to1h20` and `RP6_0h30_to1h20` are byte-identical in
size (48,239,128) with identically sized TextGrids, and the record gives no
indication they are meant to be distinct. Recordings are keyed by content hash
and a repeat is dropped rather than admitted under a second name: the whole
reason this ingest exists is a split that leaked, and two names for one
recording is exactly how that happened the first time.

Grouping. Every window cut from one source recording carries that recording's
name, so `build_index.py` assigns them a single `zen:<recording>` group and
`freeze_split.py` moves them as one unit. A window is not a recording.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import wave

import numpy as np

SRC = os.path.join("ml", "datasets", "acoustic", "raw", "_zenodo_chainsaw")
OUT = os.path.join("ml", "datasets", "acoustic", "raw")
WINDOW_S = 10.0
SR = 8000

# How much marked saw a 10 s window needs before it counts as `chainsaw`.
#
# This is deliberately NOT a high fraction of the window. The human annotations
# mark individual audible bursts, and at range those are short and clustered -
# the first recording averages 2.0 s per event across 89 events in 35 minutes.
# Requiring a window to be mostly saw would reject nearly all of them and throw
# away the exact distribution this ingest exists to add. A node records in 10 s
# windows; a window carrying a second of clearly audible saw over forest floor
# is a chainsaw-present window, and it is the hard, distant case the model gets
# wrong today. Below ~1 s the burst is short enough that a 10 s clip is mostly
# forest and the label starts teaching the wrong thing.
MIN_EVENT_S = 1.0
# Events this close together are one bout of cutting, not separate activity, so
# windows are slid across the merged bout rather than each individual burst.
MERGE_GAP_S = 8.0
# Guard band around every event before audio counts as ambient. Chainsaw carries
# far at low level - that is the entire premise of this corpus - so audio just
# outside a human-marked event is not reliably clean.
AMBIENT_GUARD_S = 30.0
CHAINSAW_HOP_S = 5.0
AMBIENT_HOP_S = 20.0
# Both caps exist to keep this corpus internally balanced, which matters more
# than its balance against the rest of the cache.
#
# The first attempt took 436 chainsaw against 163 ambient windows from eight
# recordings, and it cost 17.5 points of chainsaw precision and 40 points of
# field-ambient recall: these are SWIFT units in one forest, so they share a
# distinctive noise floor, and within that noise floor chainsaw outnumbered
# ambient 2.7:1. The model learned the recorder rather than the saw and began
# calling real field ambience `chainsaw`. Same failure as the DC offset above,
# and as the earlier `xiao_esp32s3` artifact - a per-source constant that
# correlates with a label.
#
# So every recording contributes at most as much chainsaw as ambient, and the
# ambient hop is tight enough that the long recordings can actually meet it.
MAX_AMBIENT_PER_REC = 240
MAX_CHAINSAW_PER_REC = 60


def parse_textgrid(path: str) -> list[tuple[float, float, str]]:
    """Return (xmin, xmax, text) for every non-empty interval in every tier.

    Praat writes two dialects of this format - the long one with `xmin = 1.5`
    key/value lines and a short one that is bare values in a fixed order. Only
    the long form appears in this record, but both are cheap to accept, so the
    parser keys off `intervals [n]:` blocks and reads whatever numbers follow.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        txt = fh.read()
    out: list[tuple[float, float, str]] = []
    # Long form: xmin/xmax/text triples inside an intervals block.
    for m in re.finditer(
        r"intervals\s*\[\d+\]:\s*xmin\s*=\s*([\d.eE+-]+)\s*xmax\s*=\s*([\d.eE+-]+)\s*text\s*=\s*\"([^\"]*)\"",
        txt,
    ):
        lo, hi, text = float(m.group(1)), float(m.group(2)), m.group(3).strip()
        if text:
            out.append((lo, hi, text))
    return out


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        if w.getsampwidth() != 2:
            raise SystemExit(f"{path}: expected 16-bit PCM, got {w.getsampwidth() * 8}-bit")
        sr, n, ch = w.getframerate(), w.getnframes(), w.getnchannels()
        a = np.frombuffer(w.readframes(n), dtype=np.int16).astype(np.float32)
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a / 32768.0, sr


def write_norm(path: str, x: np.ndarray) -> None:
    """Remove DC, peak-normalise, and write 8 kHz mono 16-bit per the cache convention.

    The DC removal is not cosmetic. These recordings sit at -0.007 to -0.016 DC,
    which is harmless at source level, but the windows are quiet forest - rms
    around 0.003 against a peak near 0.03 - so peak-normalising multiplies
    everything by ~30x and carries the offset up with it, to a median 0.32 and a
    worst case of 0.60. Two things break at once. The offset consumes the
    headroom the signal was supposed to get, and, far worse, it becomes a
    per-source constant: every other corpus in the cache measures 0.000 DC, so a
    model could separate this corpus from the rest on the offset alone and never
    listen to the audio. The offset was also larger on the chainsaw windows
    (0.36) than the ambient ones (0.20), which is precisely the shape of a
    shortcut that would have shown up as a chainsaw improvement.
    """
    x = x - float(x.mean())
    peak = float(np.abs(x).max())
    if peak > 0:
        x = x * (0.95 / peak)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(np.clip(x * 32767, -32768, 32767).astype(np.int16).tobytes())


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=SRC)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--manifest", default=os.path.join("ml", "acoustic", "zenodo_chainsaw_manifest.json"))
    args = ap.parse_args()

    wavs = sorted(f for f in os.listdir(args.src) if f.endswith(".wav"))
    if not wavs:
        raise SystemExit(f"no .wav under {args.src} - run the download first")

    seen: dict[str, str] = {}
    manifest: list[dict] = []
    tot_cs = tot_amb = 0
    win = int(WINDOW_S * SR)

    for fn in wavs:
        rec = fn[:-4]
        wpath = os.path.join(args.src, fn)
        tg = os.path.join(args.src, rec + ".TextGrid")
        if not os.path.exists(tg):
            print(f"  {rec}: no TextGrid, skipped")
            continue

        h = hashlib.sha256()
        with open(wpath, "rb") as fh:
            for blk in iter(lambda: fh.read(1 << 20), b""):
                h.update(blk)
        digest = h.hexdigest()
        if digest in seen:
            print(f"  {rec}: DUPLICATE of {seen[digest]} (sha256 match) - dropped")
            continue
        seen[digest] = rec

        x, sr = read_wav(wpath)
        if sr != SR:
            print(f"  {rec}: {sr} Hz, expected {SR} - skipped")
            continue
        dur = len(x) / sr
        ev = [(lo, hi) for lo, hi, _ in parse_textgrid(tg)]
        ev.sort()
        ev_s = sum(hi - lo for lo, hi in ev)

        # Merge bursts into bouts of cutting before windowing.
        bouts: list[list[float]] = []
        for lo, hi in ev:
            if bouts and lo - bouts[-1][1] <= MERGE_GAP_S:
                bouts[-1][1] = max(bouts[-1][1], hi)
            else:
                bouts.append([lo, hi])

        n_cs = n_amb = 0
        # Chainsaw windows: slide across each bout, keeping only windows that
        # carry enough marked saw to be honestly labelled.
        taken: set[int] = set()
        for lo, hi in bouts:
            t = max(0.0, lo - WINDOW_S * 0.5)
            while t + WINDOW_S <= min(dur, hi + WINDOW_S * 0.5):
                k = int(t * sr)
                if k not in taken:
                    ev_in = sum(overlap(t, t + WINDOW_S, a, b) for a, b in ev)
                    if ev_in >= MIN_EVENT_S and n_cs < MAX_CHAINSAW_PER_REC:
                        seg = x[k: k + win]
                        if len(seg) == win:
                            name = f"chainsaw_zen_{rec}_w{n_cs:04d}.10s.norm.wav"
                            if not args.dry_run:
                                write_norm(os.path.join(args.out, name), seg)
                            taken.add(k)
                            n_cs += 1
                t += CHAINSAW_HOP_S

        # Ambient windows: only where no event comes within the guard band.
        t = 0.0
        while t + WINDOW_S <= dur and n_amb < MAX_AMBIENT_PER_REC:
            near = any(
                overlap(t - AMBIENT_GUARD_S, t + WINDOW_S + AMBIENT_GUARD_S, a, b) > 0
                for a, b in ev
            )
            if not near:
                seg = x[int(t * sr): int(t * sr) + win]
                if len(seg) == win:
                    name = f"ambient_zen_{rec}_w{n_amb:04d}.10s.norm.wav"
                    if not args.dry_run:
                        write_norm(os.path.join(args.out, name), seg)
                    n_amb += 1
            t += AMBIENT_HOP_S

        print(f"  {rec:<26} {dur / 60:6.1f} min  {len(ev):4d} events ({ev_s / 60:5.1f} min)"
              f"  -> {n_cs:4d} chainsaw, {n_amb:3d} ambient")
        manifest.append({
            "recording": rec, "sha256": digest, "duration_s": round(dur, 1),
            "events": len(ev), "event_s": round(ev_s, 1),
            "chainsaw_windows": n_cs, "ambient_windows": n_amb,
            "source": "zenodo:5824433", "license": "CC-BY-4.0",
        })
        tot_cs += n_cs
        tot_amb += n_amb

    print(f"\n{len(manifest)} recordings kept, {len(wavs) - len(manifest)} dropped")
    print(f"TOTAL {tot_cs} chainsaw + {tot_amb} ambient windows")
    if not args.dry_run:
        with open(args.manifest, "w", encoding="utf-8") as fh:
            json.dump({"source": "https://zenodo.org/records/5824433",
                       "license": "CC-BY-4.0",
                       "citation": "N. Stefanakis, K. Psaroulakis, N. Simou, C. Astaras, "
                                   "'An open-access system for long-range chainsaw sound "
                                   "detection', EUSIPCO 2022",
                       "recordings": manifest}, fh, indent=1)
        print(f"wrote {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
