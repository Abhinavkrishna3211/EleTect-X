"""Invariant checks for services/config.py, not restatements of its values.

Each test asserts a relationship that has to hold for the constant's own
documented rationale to still be true - not just that the constant exists
or equals a hardcoded literal, which would only re-encode the value and
never catch drift.
"""

import re
from pathlib import Path

from services import config

MCU_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent.parent / "mcu" / "src" / "config.h"
)
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "bridge" / "schema.md"


def _read_mcu_define(name: str) -> float:
    """Pull a #define's numeric value out of device/mcu/src/config.h."""
    text = MCU_CONFIG_PATH.read_text(encoding="utf-8")
    match = re.search(rf"#define\s+{name}\s+([0-9.]+)", text)
    assert match, f"Could not find #define {name} in {MCU_CONFIG_PATH}"
    return float(match.group(1))


def test_schema_version_matches_schema_md():
    """SCHEMA_VERSION must equal the version schema.md's own header declares."""
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    match = re.search(r"schema_version:\s*uint8\s*=\s*(\d+)", text)
    assert match, "schema.md's header no longer states schema_version's value explicitly."
    assert config.SCHEMA_VERSION == int(match.group(1))


def test_bridge_call_timeout_exceeds_longest_actuator_burst():
    """Assert the timeout still exceeds the longest possible actuator burst.

    BRIDGE_CALL_TIMEOUT_S's own rationale is that it exceeds the longest
    burst any actuator can be commanded to run (LED_BURST_MAX_MS) plus
    transport overhead - if config.h's cap ever grows past that, this
    constant's derivation silently stops holding.
    """
    led_burst_max_s = _read_mcu_define("LED_BURST_MAX_MS") / 1000.0
    assert config.BRIDGE_CALL_TIMEOUT_S > led_burst_max_s, (
        f"BRIDGE_CALL_TIMEOUT_S ({config.BRIDGE_CALL_TIMEOUT_S}s) no longer "
        f"exceeds LED_BURST_MAX_MS ({led_burst_max_s}s) - a legitimate full "
        "burst would now read as a timed-out call."
    )


def test_actuator_calls_are_never_retried():
    """Assert actuator calls are never retried on timeout.

    drive_horn/drive_led/pulse_ir are non-idempotent - retrying a timed-out
    call risks doubling a physical burst. This must stay 0 regardless of how
    BRIDGE_STATE_CALL_RETRIES is tuned.
    """
    assert config.BRIDGE_ACTUATOR_CALL_RETRIES == 0


def test_data_paths_resolve_under_device_mpu():
    """Assert data paths resolve inside device/mpu, not somewhere transient.

    DATA_DIR/MODELS_DIR must stay inside device/mpu, not /tmp or a
    dev-laptop-only path, since the board's filesystem has no /tmp
    equivalent guaranteed to persist across a suspend cycle.
    """
    mpu_root = Path(__file__).resolve().parent.parent
    assert mpu_root in config.DATA_DIR.parents
    assert mpu_root in config.MODELS_DIR.parents
    assert config.EXPERIENCE_DB_PATH.parent == config.DATA_DIR


def test_camera_device_is_a_v4l2_path():
    """CAMERA_DEVICE must look like a V4L2 device node, not a Windows/OS-default path.

    perception/camera.py's own backend choice (cv2.CAP_V4L2, forced
    explicitly) only makes sense against a /dev/video* path - this catches
    a future edit accidentally pointing it somewhere else. Deliberately not
    "/dev/video" - a bare /dev/videoN index is exactly the failure mode
    docs/KNOWN_GAPS.md ruled out (it reshuffles across reboots/hub
    reconnects, and on this board even landed on the wrong device class
    once); CAMERA_DEVICE is a /dev/v4l/by-id/ symlink instead.
    """
    assert config.CAMERA_DEVICE.startswith("/dev/video") or config.CAMERA_DEVICE.startswith(
        "/dev/v4l/by-id/"
    )


def test_camera_pixel_format_is_a_valid_fourcc_length():
    """CAMERA_PIXEL_FORMAT must be exactly 4 characters - what FourCC requires.

    perception.camera.fourcc_to_int raises ValueError on anything else, so
    a malformed constant here would fail at Camera.open() time on real
    hardware instead of at import/lint time.
    """
    assert len(config.CAMERA_PIXEL_FORMAT) == 4


def test_camera_warmup_frames_is_non_negative():
    """CAMERA_WARMUP_FRAMES feeds a range() in Camera.open() - must be >= 0."""
    assert config.CAMERA_WARMUP_FRAMES >= 0


def test_camera_burst_frames_is_at_least_one():
    """CAMERA_BURST_FRAMES is capture_burst()'s default count, which rejects < 1."""
    assert config.CAMERA_BURST_FRAMES >= 1


def test_camera_burst_interval_is_non_negative():
    """CAMERA_BURST_INTERVAL_S is capture_burst()'s default interval, which rejects < 0."""
    assert config.CAMERA_BURST_INTERVAL_S >= 0
