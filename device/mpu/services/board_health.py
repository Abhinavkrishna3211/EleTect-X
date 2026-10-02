"""Best-effort board/process telemetry - stdlib only, never raises.

Read by HOME_TEST_MODE's own performance log (services/home_test.py) as the
overnight run's evidence of model speed and on-device resource headroom -
not wired into any fire/decision path, so a bad reading here must never be
able to affect capture or deterrence. Every reader function returns None on
any failure instead of raising.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

_THERMAL_ZONE_GLOB = "/sys/class/thermal/thermal_zone*/temp"


def read_cpu_temp_c() -> float | None:
    """Highest reading across every thermal zone, in Celsius.

    The QRB2210 exposes several zones (CPU, GPU, etc.) - the highest one is
    the one that would actually throttle the board, which is what a
    performance log needs to know about.
    """
    readings: list[float] = []
    for path in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            milli_c = int(path.read_text(encoding="utf-8").strip())
            readings.append(milli_c / 1000.0)
        except (OSError, ValueError):
            continue
    return max(readings) if readings else None


def read_mem_available_mb() -> float | None:
    """MemAvailable from /proc/meminfo, in MB - what's actually free for use."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def read_load_average() -> tuple[float, float, float] | None:
    """1/5/15-minute load average, as os.getloadavg() reports it.

    os.getloadavg is POSIX-only - AttributeError is caught alongside OSError
    so this stays a clean None on a Windows dev machine instead of raising.
    """
    try:
        return os.getloadavg()
    except (OSError, AttributeError):
        return None


def read_disk_free_mb(path: Path) -> float | None:
    """Free space at path's filesystem, in MB."""
    try:
        return shutil.disk_usage(path).free / (1024 * 1024)
    except OSError:
        return None


def snapshot(disk_path: Path) -> dict[str, Any]:
    """One combined reading of every metric above, for a single telemetry line."""
    return {
        "cpu_temp_c": read_cpu_temp_c(),
        "mem_available_mb": read_mem_available_mb(),
        "load_avg": read_load_average(),
        "disk_free_mb": read_disk_free_mb(disk_path),
    }
