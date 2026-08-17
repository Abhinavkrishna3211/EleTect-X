"""Live two-panel plot of the seismic geophone signal, for pitch/demo use only.

Standalone host script - stdlib plus pyserial and matplotlib only, no
dependency on device/mcu or device/mpu's own packages. Mirrors
plot_seismic_window.py's pattern of parsing firmware console lines with pure
functions kept separate from I/O, but reads a live, continuously-updating
stream instead of a saved log, and never touches disk.

Requires two device/mcu/src/config.h debug flags set to 1 together:

    SEISMIC_DEBUG_STREAM_RAW   feeds the top (raw volts) panel - one bare
                                float per line, 6 decimals, no prefix
    SEISMIC_DEBUG_VERBOSE      feeds the bottom (STA/LTA ratio) panel via the
                                existing "[seismic] t=... sta=... lta=...
                                ratio=..." line state_machine.cpp already
                                prints

Both flags must be reset to 0 and the board re-synced before any field
deployment - see device/mcu/README.md and config.h's own bench-only-flags
section.

Console source. The bench console has only been confirmed reachable via App
Lab's own browser Serial Monitor - arduino-app-cli monitor does not deliver
serial data on this board (ADR 0010's 2026-07-30 addendum), so a Windows COM
port is not confirmed to exist. To cover whichever transport turns out to
work at the bench, this script accepts any of:

    --port COM5              a serial port, via pyserial (imported lazily -
                              only needed for this source)
    --file console.log       tail a growing file (e.g. one App Lab's monitor
                              is being copy-pasted into, or that a bridge
                              process is appending to)
    - (or no source at all)  read stdin, e.g.
                              ssh host 'cat /dev/ttyGS0' | python live_seismic_plot.py -

Known gap: the plotted x-axis is host arrival time (time.monotonic() since
this script started), not the device's own millis() - the two clocks cannot
be reconciled without an offset estimate this script does not attempt, and
arrival time degrades gracefully on a dropped or reordered line, which a
device timestamp parsed out of order would not.

Known gap: the [seismic] line only prints while the state machine is in its
kSensing state (state_machine.cpp). After a trigger, the reflex loop spends
EVENT_MAX_MS + COOLDOWN_MS (config.h) in kEvent/kCooldown before returning to
kSensing - about 35 s at today's values - during which the bottom panel does
not advance. This is not a bug in this script; time a recording around it
(trigger, hold the spike a couple of seconds, cut) rather than expecting a
continuous ratio trace across a trigger event.

Usage:
    python scripts/live_seismic_plot.py --port COM5
    python scripts/live_seismic_plot.py --file console.log
    ssh eletect-x.local "cat /dev/ttyGS0" | python scripts/live_seismic_plot.py -
"""

from __future__ import annotations

import argparse
import math
import re
import sys
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

# Mirrors device/mcu/src/config.h's STA_LTA_TRIGGER_RATIO - keep in sync if
# that constant ever changes. A standalone host script cannot #include a C
# header, so this is restated rather than shared. Currently the SEISMIC_DEMO_MODE
# value (2.0), not the field value (4.0) - update this alongside config.h
# when demo mode is reverted.
STA_LTA_TRIGGER_RATIO = 2.0

# Mirrors device/mcu/src/config.h's ADS1115_CFG_PGA_2048MV full-scale range.
# Raw volts readings cannot physically arrive outside +/-ADS1115_PGA_VOLTS -
# the ADC saturates there - so this bounds --volts-limit's sane range.
ADS1115_PGA_VOLTS = 2.048

_RATIO_RE = re.compile(
    r"^\[seismic\] t=(?P<t>\d+) sta=(?P<sta>-?[\d.]+) lta=(?P<lta>-?[\d.]+) "
    r"ratio=(?P<ratio>-?[\d.]+)\s*$"
)


@dataclass(frozen=True)
class RatioSample:
    """One parsed "[seismic] t=... sta=... lta=... ratio=..." line.

    Attributes:
        t_ms: millis() on the device when this line was printed.
        sta: Short-term average magnitude.
        lta: Long-term average magnitude.
        ratio: sta / lta - compared against STA_LTA_TRIGGER_RATIO.
    """

    t_ms: int
    sta: float
    lta: float
    ratio: float


def parse_raw_volts_line(line: str) -> float | None:
    """Parse one SEISMIC_DEBUG_STREAM_RAW line: a bare volts float, nothing else.

    Args:
        line: One line of console text, not yet stripped.

    Returns:
        The parsed value, or None if the line is not a bare float (the
        normal case for every other line type in an interleaved console
        stream - not warned about). A line that does parse as a float but is
        not finite (a corrupted line like a stray run of digits overflowing
        to inf) is also treated as unusable, but is warned about on stderr
        since a plausible-looking numeric line silently vanishing would
        otherwise be confusing to debug.
    """
    stripped = line.strip()
    try:
        value = float(stripped)
    except ValueError:
        return None

    if not math.isfinite(value):
        print(f"warning: raw volts line parsed but is not finite: {line!r}", file=sys.stderr)
        return None

    return value


def parse_ratio_line(line: str) -> RatioSample | None:
    """Parse one "[seismic] t=... sta=... lta=... ratio=..." line.

    Args:
        line: One line of console text, not yet stripped.

    Returns:
        A RatioSample, or None if the line does not start with the
        "[seismic] " tag at all (the normal case for every other line type -
        not warned about). A line that does start with the tag but does not
        match the full expected shape (a truncated or garbled field) is also
        None, but is warned about on stderr - unlike an unrelated line, this
        one was clearly meant to be a ratio line and silently dropping it
        could hide a real parsing problem.
    """
    stripped = line.strip()
    if not stripped.startswith("[seismic] "):
        return None

    match = _RATIO_RE.match(stripped)
    if match is None:
        print(f"warning: [seismic] line did not match expected format: {line!r}", file=sys.stderr)
        return None

    return RatioSample(
        t_ms=int(match.group("t")),
        sta=float(match.group("sta")),
        lta=float(match.group("lta")),
        ratio=float(match.group("ratio")),
    )


def _iter_serial_lines(port: str, baud: int) -> Iterator[str]:
    """Yield decoded lines from a pyserial connection, blocking as needed."""
    try:
        import serial
    except ImportError as exc:
        raise SystemExit(
            "pyserial is required for --port. Install it with: pip install pyserial"
        ) from exc

    # timeout=0.05, not 1: a single blocking read with nothing waiting
    # returns after the timeout instead of stalling the animation callback
    # (and the whole Tkinter mainloop) for up to a full second per quiet
    # call, the same GUI-freeze class _iter_file_tail_lines's own 0.05 s
    # poll was fixed to avoid.
    #
    # Deliberately not connection.readline(): pyserial's readline() applies
    # this same timeout to *finding the next newline*, not just to "is
    # anything waiting" - if a multi-part Serial.print() (state_machine.cpp's
    # [seismic] line is 8 separate print() calls) straddles a 50 ms gap for
    # any reason (this script's own matplotlib animation loop competing for
    # the same thread, a USB-CDC chunk boundary, ...), readline() returns the
    # partial line with no trailing "\n" and the rest is lost - confirmed
    # on-hardware as a steady stream of "did not match expected format"
    # warnings once this ran inside the live plot's animation loop, not
    # reproducible in a standalone tight-loop reader. Buffering raw bytes
    # ourselves and only yielding on an actual "\n" makes a slow line block
    # across as many quiet reads as it needs instead of ever being truncated.
    with serial.Serial(port, baud, timeout=0.05) as connection:
        buffer = bytearray()
        while True:
            chunk = connection.read(max(1, connection.in_waiting))
            if not chunk:
                yield ""
                continue
            buffer.extend(chunk)
            while b"\n" in buffer:
                line, _, rest = buffer.partition(b"\n")
                buffer = bytearray(rest)
                yield (bytes(line) + b"\n").decode("utf-8", errors="replace")


def _iter_file_tail_lines(path: str) -> Iterator[str]:
    """Yield lines appended to a growing file, polling for new content.

    Yields "" rather than looping internally when nothing new is ready, so a
    single next() call is bounded to one ~0.05 s poll instead of blocking for
    the full length of a quiet stretch in the source (e.g. the ~35 s
    kEvent/kCooldown gap noted in the module docstring) - that unbounded
    block, not the drain loop below, is what actually froze the GUI thread.
    """
    with open(path, encoding="utf-8", errors="replace") as handle:
        handle.seek(0, 2)  # start at end-of-file - only new lines matter live
        while True:
            line = handle.readline()
            if not line:
                time.sleep(0.05)
                yield ""
                continue
            yield line


def _iter_stdin_lines() -> Iterator[str]:
    """Yield lines from stdin as they arrive."""
    yield from sys.stdin


def _make_line_source(args: argparse.Namespace) -> Iterator[str]:
    """Pick the line source implied by the parsed CLI args."""
    if args.port is not None:
        return _iter_serial_lines(args.port, args.baud)
    if args.file is not None:
        return _iter_file_tail_lines(args.file)
    return _iter_stdin_lines()


def _run_live_plot(
    line_source: Iterator[str], window_s: float, volts_limit: float, ratio_limit: float
) -> None:
    """Drive the two-panel FuncAnimation plot until the window is closed."""
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    plt.rcParams.update(
        {
            "font.size": 13,
            "axes.titlesize": 18,
            "axes.labelsize": 15,
            "xtick.labelsize": 13,
            "ytick.labelsize": 13,
        }
    )

    start_s = time.monotonic()
    volts_t: deque[float] = deque()
    volts_v: deque[float] = deque()
    ratio_t: deque[float] = deque()
    ratio_v: deque[float] = deque()

    fig, (ax_volts, ax_ratio) = plt.subplots(2, 1, sharex=True, figsize=(12, 8))
    fig.suptitle("EleTect X - live seismic geophone signal", fontsize=20)

    (volts_line,) = ax_volts.plot([], [], linewidth=0.8, color="tab:blue")
    ax_volts.set_ylabel("raw volts")
    ax_volts.set_ylim(-volts_limit, volts_limit)
    ax_volts.set_title("geophone output")

    (ratio_line,) = ax_ratio.plot([], [], linewidth=1.2, color="tab:orange")
    ax_ratio.axhline(
        STA_LTA_TRIGGER_RATIO,
        color="red",
        linestyle="--",
        linewidth=1.5,
        label=f"trigger {STA_LTA_TRIGGER_RATIO:.1f}",
    )
    ax_ratio.set_ylabel("STA/LTA ratio")
    ax_ratio.set_xlabel("time (s)")
    ax_ratio.set_ylim(0, ratio_limit)
    ax_ratio.set_title("footfall trigger ratio")
    ax_ratio.legend(loc="upper right")

    def _trim(times: deque[float], values: deque[float], now_s: float) -> None:
        cutoff = now_s - window_s
        while times and times[0] < cutoff:
            times.popleft()
            values.popleft()

    def _update(_frame: int):
        now_s = time.monotonic() - start_s

        # Bounded by wall-clock time, not line count: a count cap (the original
        # design) assumes lines arrive fast enough that draining N of them is
        # cheap. At a real sample rate well under the line source's per-call
        # blocking latency (confirmed on-hardware: SEISMIC_SAMPLE_RATE_HZ 250
        # in config.h vs an observed ~8 lines/sec relayed through Bridge.notify()),
        # a 500-line cap can block this callback - and therefore the whole
        # Tkinter mainloop - for the better part of a minute, which Windows
        # reports as "(Not Responding)". A time cap instead guarantees this
        # callback returns control to the animation loop well within one frame
        # interval regardless of arrival rate.
        drain_deadline = time.monotonic() + 0.03
        for _ in range(2000):  # hard safety cap against a pathological fast burst
            if time.monotonic() >= drain_deadline:
                break
            try:
                line = next(line_source)
            except StopIteration:
                break

            raw_volts = parse_raw_volts_line(line)
            if raw_volts is not None:
                volts_t.append(now_s)
                volts_v.append(raw_volts)
                continue

            ratio_sample = parse_ratio_line(line)
            if ratio_sample is not None:
                ratio_t.append(now_s)
                ratio_v.append(ratio_sample.ratio)

        _trim(volts_t, volts_v, now_s)
        _trim(ratio_t, ratio_v, now_s)

        volts_line.set_data(volts_t, volts_v)
        ratio_line.set_data(ratio_t, ratio_v)

        left = max(0.0, now_s - window_s)
        ax_volts.set_xlim(left, max(now_s, window_s))

        return volts_line, ratio_line

    # cache_frame_data=False: this animation runs indefinitely and blit=False
    # already disables the caching FuncAnimation would otherwise warn about.
    _animation = FuncAnimation(fig, _update, interval=50, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()


def main() -> int:
    """Parse CLI args and run the live plot until the window is closed."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--port", help="Serial port to read from, e.g. COM5 (requires pyserial)")
    source.add_argument("--file", help="Path to a growing console log to tail")
    parser.add_argument(
        "stdin_marker",
        nargs="?",
        choices=["-"],
        help="Pass '-' to read stdin explicitly (default if neither --port nor --file is given)",
    )
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate for --port (default 115200)")
    parser.add_argument(
        "--window", type=float, default=5.0, help="Seconds of scrolling history to show (default 5)"
    )
    parser.add_argument(
        "--volts-limit",
        type=float,
        default=0.25,
        help=(
            "Raw-volts panel y-axis is +/- this many volts (default 0.25). "
            f"Hard bound is +/-{ADS1115_PGA_VOLTS} V (the ADS1115's PGA full-scale range) - "
            "counts saturate outside that, so nothing wider is meaningful. Use "
            f"--volts-limit {ADS1115_PGA_VOLTS} for a single-ended bias-check session."
        ),
    )
    parser.add_argument(
        "--ratio-limit",
        type=float,
        default=8.0,
        help="STA/LTA ratio panel y-axis is 0 to this value (default 8.0)",
    )
    args = parser.parse_args()

    if args.volts_limit <= 0 or args.ratio_limit <= 0 or args.window <= 0:
        print("error: --volts-limit, --ratio-limit, and --window must all be positive", file=sys.stderr)
        return 1

    line_source = _make_line_source(args)
    _run_live_plot(line_source, args.window, args.volts_limit, args.ratio_limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
