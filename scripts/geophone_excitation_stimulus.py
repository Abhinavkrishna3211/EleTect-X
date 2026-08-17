#!/usr/bin/env python3
"""Bench-only geophone excitation stimulus player.

Plays a fixed sequence (quiet baseline, discrete tones, a linear sweep, an
impulse/thump train) through the desk-coupled laptop speaker and logs the
real wall-clock start/stop of every event to a JSONL file, so a separate
capture of the board's [seismic] console stream can be correlated against it
after the fact.

Desk-speaker excitation is NOT a substitute for a real human stomp test -
different waveform shape, amplitude, and frequency content than an elephant
footfall coupling through soil. This only checks that the SM-24 -> INA333 ->
ADS1115 -> STA/LTA chain is alive, repeatable, and roughly the right
frequency-response shape. See docs/KNOWN_GAPS.md's geophone section.

Requires the laptop's own audio enhancements (Nahimic/Spatial Sound/bass
boost) to be OFF - they distort frequency content in ways that would corrupt
the correlation. Requires the geophone rig to be on the same rigid desk
surface as the laptop, not on top of it.

Usage:
    python geophone_excitation_stimulus.py --out bench-logs/stimulus_<ts>.jsonl
"""
import argparse
import datetime
import json
import sys
import time

import numpy as np

try:
    import sounddevice as sd
    HAVE_SOUNDDEVICE = True
except ImportError:
    HAVE_SOUNDDEVICE = False
    import winsound

SAMPLE_RATE = 48000
GAIN = 0.25 * 0.9  # matches scripts/geophone_bench_excitation.html's default 25% slider * 0.9 headroom cap
FADE_S = 0.015     # short raised-cosine fade in/out to avoid clicks between segments

TONE_FREQS_HZ = [10.0, 20.0, 24.0, 50.0]
# Supplementary points, not in the original spec's required set - added to bracket
# the SM-24's ~10 Hz mechanical resonance more finely after the first pass showed a
# strong, real STA/LTA response there, and to see the rolloff shape further out.
EXTRA_TONE_FREQS_HZ = [5.0, 8.0, 15.0, 30.0, 100.0]
TONE_DUR_S = 5.0
GAP_DUR_S = 3.0
BASELINE_DUR_S = 10.0
SWEEP_START_HZ = 2.0
SWEEP_END_HZ = 60.0
SWEEP_DUR_S = 20.0
IMPULSE_BURST_MS = 80
IMPULSE_BPM = 60
IMPULSE_TRAIN_DUR_S = 15.0
IMPULSE_TONE_HZ = 24.0  # burst carrier frequency, matches the html tool's default


def fade(samples: np.ndarray) -> np.ndarray:
    n = len(samples)
    fade_n = min(int(FADE_S * SAMPLE_RATE), n // 2)
    if fade_n <= 0:
        return samples
    window = np.ones(n)
    ramp = 0.5 * (1 - np.cos(np.linspace(0, np.pi, fade_n)))
    window[:fade_n] = ramp
    window[-fade_n:] = ramp[::-1]
    return samples * window


def make_tone(freq_hz: float, dur_s: float) -> np.ndarray:
    t = np.linspace(0, dur_s, int(SAMPLE_RATE * dur_s), endpoint=False)
    return fade(GAIN * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def make_sweep(f0: float, f1: float, dur_s: float) -> np.ndarray:
    t = np.linspace(0, dur_s, int(SAMPLE_RATE * dur_s), endpoint=False)
    # Linear chirp: instantaneous frequency f(t) = f0 + (f1-f0)*t/dur_s
    k = (f1 - f0) / dur_s
    phase = 2 * np.pi * (f0 * t + 0.5 * k * t ** 2)
    return fade(GAIN * np.sin(phase)).astype(np.float32)


def make_burst(freq_hz: float, dur_ms: float) -> np.ndarray:
    dur_s = dur_ms / 1000.0
    t = np.linspace(0, dur_s, int(SAMPLE_RATE * dur_s), endpoint=False)
    tone = np.sin(2 * np.pi * freq_hz * t)
    attack_n = int(0.008 * SAMPLE_RATE)
    release_n = int(0.010 * SAMPLE_RATE)
    env = np.ones(len(t))
    if attack_n > 0:
        env[:attack_n] = np.linspace(0, 1, attack_n)
    if release_n > 0:
        env[-release_n:] = np.linspace(1, 0, release_n)
    return (GAIN * tone * env).astype(np.float32)


def make_impulse_train(bpm: float, burst_ms: float, total_dur_s: float, freq_hz: float) -> np.ndarray:
    interval_s = 60.0 / bpm
    n_total = int(SAMPLE_RATE * total_dur_s)
    out = np.zeros(n_total, dtype=np.float32)
    burst = make_burst(freq_hz, burst_ms)
    t = 0.0
    while t < total_dur_s:
        start = int(t * SAMPLE_RATE)
        end = min(start + len(burst), n_total)
        out[start:end] += burst[: end - start]
        t += interval_s
    return out


def play_blocking(samples: np.ndarray) -> None:
    sd.play(samples, SAMPLE_RATE, blocking=False)
    sd.wait()


def beep_fallback(freq_hz: float, dur_ms: int) -> None:
    winsound.Beep(max(37, min(int(round(freq_hz)), 32767)), dur_ms)


def run(out_path: str) -> None:
    events = []

    def log_event(label: str, freq_hz, start_ts: float, end_ts: float, note: str = "") -> None:
        events.append({
            "label": label,
            "freq_hz": freq_hz,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_iso": datetime.datetime.fromtimestamp(start_ts).isoformat(),
            "end_iso": datetime.datetime.fromtimestamp(end_ts).isoformat(),
            "note": note,
        })
        print(f"[{label}] {end_ts - start_ts:5.2f}s  "
              f"{(f'{freq_hz:.1f} Hz' if freq_hz is not None else ''):>10}  {note}")

    print("=== geophone excitation stimulus: starting ===")
    print("Confirm: capture (ssh ... nc 127.0.0.1 7500) is already running before continuing.")
    print(f"Method: {'sounddevice sine synthesis' if HAVE_SOUNDDEVICE else 'winsound.Beep (SQUARE WAVE, not sine)'}")

    # 1. Quiet baseline
    t0 = time.time()
    time.sleep(BASELINE_DUR_S)
    t1 = time.time()
    log_event("baseline_quiet", None, t0, t1)

    # 2. Discrete tones with quiet gaps
    for freq in TONE_FREQS_HZ:
        t0 = time.time()
        if HAVE_SOUNDDEVICE:
            play_blocking(make_tone(freq, TONE_DUR_S))
        else:
            beep_fallback(freq, int(TONE_DUR_S * 1000))
        t1 = time.time()
        log_event(f"tone_{freq:g}hz", freq, t0, t1)

        t0 = time.time()
        time.sleep(GAP_DUR_S)
        t1 = time.time()
        log_event(f"quiet_gap_after_{freq:g}hz", None, t0, t1)

    # 3. Linear sweep
    t0 = time.time()
    if HAVE_SOUNDDEVICE:
        play_blocking(make_sweep(SWEEP_START_HZ, SWEEP_END_HZ, SWEEP_DUR_S))
    else:
        # Coarse fallback: step through the sweep range in 1 Hz beeps.
        n_steps = int(SWEEP_DUR_S)
        step_ms = int(SWEEP_DUR_S * 1000 / n_steps)
        for i in range(n_steps):
            f = SWEEP_START_HZ + (SWEEP_END_HZ - SWEEP_START_HZ) * i / n_steps
            beep_fallback(f, step_ms)
    t1 = time.time()
    log_event("sweep_2to60hz", None, t0, t1, note=f"{SWEEP_START_HZ}->{SWEEP_END_HZ} Hz linear")

    t0 = time.time()
    time.sleep(GAP_DUR_S)
    t1 = time.time()
    log_event("quiet_gap_after_sweep", None, t0, t1)

    # 4. Impulse/thump train
    t0 = time.time()
    if HAVE_SOUNDDEVICE:
        play_blocking(make_impulse_train(IMPULSE_BPM, IMPULSE_BURST_MS, IMPULSE_TRAIN_DUR_S, IMPULSE_TONE_HZ))
    else:
        n_beats = int(IMPULSE_TRAIN_DUR_S * IMPULSE_BPM / 60.0)
        interval_s = 60.0 / IMPULSE_BPM
        for _ in range(n_beats):
            beep_fallback(IMPULSE_TONE_HZ, IMPULSE_BURST_MS)
            time.sleep(max(0.0, interval_s - IMPULSE_BURST_MS / 1000.0))
    t1 = time.time()
    log_event("impulse_train", IMPULSE_TONE_HZ, t0, t1,
               note=f"{IMPULSE_BPM} BPM, {IMPULSE_BURST_MS}ms bursts")

    t0 = time.time()
    time.sleep(GAP_DUR_S)
    t1 = time.time()
    log_event("quiet_gap_after_impulse", None, t0, t1)

    # 5. Supplementary tones (not in the original required spec set - see
    # EXTRA_TONE_FREQS_HZ's comment above).
    for freq in EXTRA_TONE_FREQS_HZ:
        t0 = time.time()
        if HAVE_SOUNDDEVICE:
            play_blocking(make_tone(freq, TONE_DUR_S))
        else:
            beep_fallback(freq, int(TONE_DUR_S * 1000))
        t1 = time.time()
        log_event(f"extra_tone_{freq:g}hz", freq, t0, t1, note="supplementary, not in original spec set")

        t0 = time.time()
        time.sleep(GAP_DUR_S)
        t1 = time.time()
        log_event(f"quiet_gap_after_extra_{freq:g}hz", None, t0, t1)

    with open(out_path, "w") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")
    print(f"=== done. {len(events)} events logged to {out_path} ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="path to write the JSONL timestamp log")
    args = parser.parse_args()
    run(args.out)
