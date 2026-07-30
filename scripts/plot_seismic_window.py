"""Render [window] CSV dumps from a saved seismic bench console log into PNGs.

Standalone host script - stdlib plus matplotlib only, no dependency on
device/mcu or device/mpu's own packages. Mirrors device/mpu/bench/
camera_check/capture_check.py's pattern: run standalone, save output to
disk, no live-display assumption.

Reads a text console log saved from a bench session run with
SEISMIC_DEBUG_VERBOSE=1 (device/mcu/include/config.h), where
state_machine.cpp prints one [window] header line followed immediately by
one CSV line of raw volts on every existing [trigger] event, and renders
one PNG per dump - this is the Part C2 sensitivity/waveform-
characterization pass that flag exists for (device/mcu/README.md), not the
INA333 REF-bias check.

Expected input shape, one pair per trigger, interleaved with any other
console output (which is ignored):

    [window] t=<ms> n=<sample_count> rate_hz=<rate> unit=volts
    <v0>,<v1>,...,<vN-1>

Usage:
    python scripts/plot_seismic_window.py console.log --out-dir plots/
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_HEADER_RE = re.compile(
    r"^\[window\] t=(?P<t>\d+) n=(?P<n>\d+) rate_hz=(?P<rate_hz>\d+) unit=volts\s*$"
)


@dataclass(frozen=True)
class WindowDump:
    """One parsed [window] header + CSV sample line pair.

    Attributes:
        t_ms: millis() at the [trigger] event this dump was printed for.
        n: Sample count the header itself claims - not necessarily equal to
            len(samples) if the CSV line was truncated in the saved log.
        rate_hz: Sample rate the header claims, for the plot's x-axis.
        samples: Parsed raw volts, oldest-to-newest, as printed.
    """

    t_ms: int
    n: int
    rate_hz: int
    samples: tuple[float, ...]


def parse_window_dumps(log_text: str) -> list[WindowDump]:
    """Extract every [window] header + CSV sample line pair from a console log.

    Pure function - no file I/O, no plotting. Only reads the line
    immediately following a recognized [window] header; every other line
    (other [trigger]/[seismic]/[bias-check] lines, App Lab console noise,
    blank lines) is skipped without affecting parsing.

    Args:
        log_text: Full text of a saved console log.

    Returns:
        One WindowDump per [window] header found, in the order they appear.
        A header whose immediately-following line does not parse as a
        comma-separated list of floats is skipped (a warning goes to
        stderr) rather than raising - one truncated dump at the end of a
        log should not lose every dump before it.
    """
    lines = log_text.splitlines()
    dumps: list[WindowDump] = []
    i = 0
    while i < len(lines):
        match = _HEADER_RE.match(lines[i])
        if match is None:
            i += 1
            continue

        if i + 1 >= len(lines):
            print(
                f"warning: [window] header at line {i + 1} has no following "
                "CSV line, skipping",
                file=sys.stderr,
            )
            break

        csv_line = lines[i + 1].strip()
        try:
            samples = tuple(float(value) for value in csv_line.split(","))
        except ValueError:
            print(
                f"warning: [window] header at line {i + 1} followed by "
                "unparseable CSV, skipping",
                file=sys.stderr,
            )
            i += 2
            continue

        dumps.append(
            WindowDump(
                t_ms=int(match.group("t")),
                n=int(match.group("n")),
                rate_hz=int(match.group("rate_hz")),
                samples=samples,
            )
        )
        i += 2

    return dumps


def _plot_dump(dump: WindowDump, out_dir: Path) -> Path:
    """Render one WindowDump to a PNG, x-axis in seconds from window start."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    time_s = [i / dump.rate_hz for i in range(len(dump.samples))]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(time_s, dump.samples, linewidth=0.8)
    ax.set_xlabel("time (s)")
    ax.set_ylabel("volts")
    ax.set_title(f"seismic window @ t={dump.t_ms} ms (n={len(dump.samples)}, {dump.rate_hz} Hz)")
    fig.tight_layout()

    out_path = out_dir / f"window_t{dump.t_ms}.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def main() -> int:
    """Parse a console log and save one PNG per [window] dump. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", help="Path to a saved console log containing [window] dumps")
    parser.add_argument("--out-dir", default="plots", help="Directory to save PNGs into")
    args = parser.parse_args()

    log_path = Path(args.log_file)
    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    dumps = parse_window_dumps(log_text)
    if not dumps:
        print(f"No [window] dumps found in {log_path}")
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for dump in dumps:
        saved = _plot_dump(dump, out_dir)
        print(f"saved {saved} ({len(dump.samples)} samples)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
