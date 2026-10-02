"""Integrity audit of the frozen acoustic split, run before anything is trained on it.

Every check here exists because something like it went wrong at least once. The
three leaks ADR 0025 documents were all invisible to per-file inspection and all
found only by asking whether two files were secretly the same recording, so the
expensive check - hashing every payload and looking for content duplicates that
straddle the train/test boundary - is the one that actually matters and is not
optional.

Checks, in rough order of how badly a failure would invalidate a result:

  1. CONTENT DUPLICATES ACROSS THE SPLIT. Identical audio in train and test is a
     leak no grouping rule caught. Fatal.
  2. GROUP STRADDLE. A recording group with files on both sides. Fatal - it means
     the split file was not drawn on groups, or was edited afterwards.
  3. MISSING FILES. A split that references audio the disk lacks silently shrinks
     the test set.
  4. FORMAT DRIFT. The locked impulse is 8 kHz mono 16-bit 10 s. A clip at another
     rate or length trains on a different front end than it deploys with.
  5. DEGENERATE AUDIO. All-zero, DC-offset, or clipped payloads are real - a
     recorder that dropped out produces them - and they teach nothing.
  6. LABEL/FILENAME DISAGREEMENT. The cache prefixes every file with its label, so
     a record whose label contradicts its own filename means the index mis-parsed.
  7. CLASS AND SOURCE BALANCE, reported not enforced, since what counts as
     balanced is a judgement call.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import sys
import wave

import numpy as np

SR = 8000
DUR_S = 10.0
WIDTH = 2
CHANNELS = 1


def probe(path: str) -> dict:
    """Hash the payload and measure the waveform in one pass."""
    with wave.open(path, "rb") as w:
        sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(n)
    out = {"sr": sr, "frames": n, "ch": ch, "width": sw,
           "sha256": hashlib.sha256(raw).hexdigest()}
    if sw == 2:
        a = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        if ch > 1:
            a = a.reshape(-1, ch).mean(axis=1)
        if a.size:
            peak = float(np.abs(a).max())
            out["peak"] = peak / 32768.0
            out["rms"] = float(np.sqrt(np.mean(a ** 2))) / 32768.0
            out["dc"] = float(a.mean()) / 32768.0
            out["clip_frac"] = float(np.mean(np.abs(a) >= 32700))
        else:
            out.update(peak=0.0, rms=0.0, dc=0.0, clip_frac=0.0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default=os.path.join("ml", "acoustic", "harness", "split.json"))
    ap.add_argument("--full", action="store_true",
                    help="hash and probe every file (slow, and the only way checks 1/4/5 run)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    with open(args.split, encoding="utf-8") as fh:
        spec = json.load(fh)
    recs = spec["records"]
    fatal: list[str] = []
    warn: list[str] = []

    print(f"=== {args.split} ===")
    print(f"{len(recs)} files, {len({r['group'] for r in recs})} recordings\n")

    # --- 2. group straddle -------------------------------------------------
    side = collections.defaultdict(set)
    for r in recs:
        side[r["group"]].add(r["split"])
    straddle = sorted(g for g, s in side.items() if len(s) > 1)
    if straddle:
        fatal.append(f"{len(straddle)} recording group(s) on BOTH sides of the split: {straddle[:5]}")
    else:
        print("[ok]   no recording group straddles the split")

    # --- 6. label vs filename ---------------------------------------------
    bad_label = [r for r in recs if not r["file"].startswith(r["label"])]
    if bad_label:
        fatal.append(f"{len(bad_label)} file(s) whose label contradicts the filename, "
                     f"e.g. {[(b['file'][:48], b['label']) for b in bad_label[:3]]}")
    else:
        print("[ok]   every filename agrees with its label")

    # --- 3. missing files --------------------------------------------------
    missing = [r["path"] for r in recs if not os.path.exists(r["path"])]
    if missing:
        fatal.append(f"{len(missing)} file(s) referenced by the split are absent from disk, "
                     f"e.g. {missing[:3]}")
    else:
        print(f"[ok]   all {len(recs)} referenced files present on disk")

    # --- class / source balance -------------------------------------------
    print("\nclass balance (files | recordings)")
    for label in sorted({r["label"] for r in recs}):
        sub = [r for r in recs if r["label"] == label]
        tr = [r for r in sub if r["split"] == "train"]
        te = [r for r in sub if r["split"] == "test"]
        print(f"  {label:<15} train {len(tr):>5} | {len({r['group'] for r in tr}):>4}"
              f"    test {len(te):>4} | {len({r['group'] for r in te}):>4}")
    print("\nsource mix")
    for src, n in collections.Counter(r["source"] for r in recs).most_common():
        g = len({r["group"] for r in recs if r["source"] == src})
        print(f"  {src:<20} {n:>5} files  {g:>5} recordings")

    if not args.full:
        print("\n(--full not given: content-duplicate, format and degenerate-audio "
              "checks were SKIPPED - those are the ones that catch real leaks)")
    else:
        print(f"\nprobing {len(recs)} files ...")
        seen: dict[str, list[dict]] = collections.defaultdict(list)
        fmt_bad, degen = [], []
        probes = {}
        for i, r in enumerate(recs, 1):
            if not os.path.exists(r["path"]):
                continue
            try:
                p = probe(r["path"])
            except Exception as e:                      # noqa: BLE001 - report, never abort the audit
                fmt_bad.append((r["file"], f"unreadable: {e}"))
                continue
            probes[r["file"]] = p
            seen[p["sha256"]].append(r)
            if p["sr"] != SR or p["ch"] != CHANNELS or p["width"] != WIDTH:
                fmt_bad.append((r["file"], f"{p['sr']}Hz {p['ch']}ch {p['width'] * 8}bit"))
            elif abs(p["frames"] / p["sr"] - DUR_S) > 0.05:
                fmt_bad.append((r["file"], f"{p['frames'] / p['sr']:.2f}s"))
            if p.get("peak", 1) < 1e-4:
                degen.append((r["file"], "silent"))
            elif abs(p.get("dc", 0)) > 0.05:
                degen.append((r["file"], f"DC offset {p['dc']:+.3f}"))
            elif p.get("clip_frac", 0) > 0.02:
                degen.append((r["file"], f"clipped {p['clip_frac']:.1%}"))
            if i % 1000 == 0:
                print(f"  {i}/{len(recs)}")

        # --- 1. content duplicates ----------------------------------------
        dup_groups = {h: rs for h, rs in seen.items() if len(rs) > 1}
        cross = {h: rs for h, rs in dup_groups.items()
                 if len({r["split"] for r in rs}) > 1}
        same = {h: rs for h, rs in dup_groups.items() if h not in cross}
        if cross:
            ex = [[r["file"][:44] + ":" + r["split"] for r in rs] for rs in list(cross.values())[:3]]
            fatal.append(f"{len(cross)} byte-identical audio payload(s) appear on BOTH sides "
                         f"of the split - this is a leak: {ex}")
        else:
            print("[ok]   no identical payload spans train and test")
        if same:
            n = sum(len(v) - 1 for v in same.values())
            warn.append(f"{len(same)} payload(s) duplicated {n} time(s) within one side of the "
                        f"split - harmless for held-out honesty, wasteful for training")
        if fmt_bad:
            fatal.append(f"{len(fmt_bad)} file(s) not {SR}Hz/{CHANNELS}ch/{WIDTH * 8}bit/{DUR_S}s, "
                         f"e.g. {fmt_bad[:3]}")
        else:
            print(f"[ok]   all files {SR}Hz mono {WIDTH * 8}-bit {DUR_S}s")
        if degen:
            warn.append(f"{len(degen)} degenerate payload(s), e.g. {degen[:4]}")
        else:
            print("[ok]   no silent, DC-offset or clipped payloads")

        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump({"probes": probes,
                           "cross_split_duplicates": {h: [r["file"] for r in rs]
                                                      for h, rs in cross.items()}}, fh, indent=1)
            print(f"\nwrote {args.json_out}")

    print()
    for w in warn:
        print(f"[warn] {w}")
    for f in fatal:
        print(f"[FATAL] {f}")
    if fatal:
        print(f"\n{len(fatal)} fatal issue(s) - do not train on this split until they are resolved")
        return 1
    print("\nno fatal issues" + (f", {len(warn)} warning(s)" if warn else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
