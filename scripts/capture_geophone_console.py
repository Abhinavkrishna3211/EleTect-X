#!/usr/bin/env python3
"""Bench-only capture wrapper around the board's socat/nc console bridge.

Connects to the board over `ssh <host> "nc 127.0.0.1 7500"` (same method
used for tonight's cadence-gate check - the socat daemon on the board
bridges /dev/ttyGS0 to tcp:127.0.0.1:7500, since arduino-app-cli monitor
cannot read this board's live serial console, see docs/KNOWN_GAPS.md).

Each line is timestamped with the HOST's wall-clock arrival time, not the
board's own millis()-based `t=` field printed inside [seismic]/[trigger]
lines - those are two different clocks with no cheap way to align them
after the fact, whereas host-arrival time can be directly compared against
the stimulus script's own wall-clock event log (also produced on this same
host). Network/serial latency here is small (local Wi-Fi + USB gadget
serial) relative to the multi-second stimulus windows being correlated
against.

Usage:
    python capture_geophone_console.py --host arduino@eletect-x.local \
        --duration 100 --out bench-logs/geophone_excitation_<date>.log
"""
import argparse
import subprocess
import sys
import time


def run(host: str, duration_s: float, out_path: str) -> None:
    cmd = ["ssh", host, "nc 127.0.0.1 7500"]
    print(f"=== capture: connecting via: {' '.join(cmd)} ===")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, bufsize=1)
    deadline = time.time() + duration_s
    n_lines = 0
    try:
        with open(out_path, "w") as f:
            while time.time() < deadline:
                remaining = deadline - time.time()
                # readline() blocks; if the stream goes idle near the deadline
                # this can overrun slightly, which is fine for a bench capture.
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        print("=== capture: ssh/nc process exited early ===", file=sys.stderr)
                        break
                    continue
                recv_ts = time.time()
                f.write(f"{recv_ts:.6f}\t{line.rstrip(chr(10))}\n")
                f.flush()
                n_lines += 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print(f"=== capture: done, {n_lines} lines written to {out_path} ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="arduino@eletect-x.local")
    parser.add_argument("--duration", type=float, required=True, help="capture duration in seconds")
    parser.add_argument("--out", required=True, help="path to write the timestamped raw console log")
    args = parser.parse_args()
    run(args.host, args.duration, args.out)
