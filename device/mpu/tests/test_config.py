"""Invariant checks for services/config.py, not restatements of its values.

Each test asserts a relationship that has to hold for the constant's own
documented rationale to still be true - not just that the constant exists
or equals a hardcoded literal, which would only re-encode the value and
never catch drift.
"""

import re
from pathlib import Path

from services import config, reflex_loop

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


def test_actuator_call_timeouts_each_exceed_their_mcu_cap():
    """Each per-actuator Bridge.call timeout must exceed that actuator's cap.

    drive_horn/drive_led/pulse_ir do not ack until the commanded burst
    finishes, and the deterrence ladder commands the uint16 protocol max on
    every tier (cognition/config.py TIER_DURATION_MS), which the MCU clamps
    to the cap below. If a timeout here ever drops to or below its actuator's
    cap, a legitimate full-length burst reads as a hung call and the reflex
    loop raises TimeoutError on every tier fire. Caps are owned by
    device/mcu/src/config.h.
    """
    for timeout_s, define in (
        (config.BRIDGE_HORN_CALL_TIMEOUT_S, "HORN_BURST_MAX_MS"),
        (config.BRIDGE_LED_CALL_TIMEOUT_S, "LED_BURST_MAX_MS"),
        (config.BRIDGE_IR_CALL_TIMEOUT_S, "IR_PULSE_MAX_MS"),
    ):
        cap_s = _read_mcu_define(define) / 1000.0
        assert timeout_s > cap_s, (
            f"Bridge.call timeout ({timeout_s}s) no longer exceeds {define} "
            f"({cap_s}s) - a legitimate full burst would read as a timed-out "
            "call and every tier fire would raise TimeoutError."
        )


def test_generic_bridge_call_timeout_still_covers_longest_burst():
    """BRIDGE_CALL_TIMEOUT_S (non-actuator calls) must still clear the LED cap.

    bridge/rpc.py's docstrings still route get_system_state and the retry
    policy through this historical name; it stays equal to the longest
    per-actuator timeout so those references keep resolving to a value that
    exceeds the longest burst plus transport overhead.
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


# ---------------------------------------------------------------------------
# Trigger-gated event video (ADR 0020)
# ---------------------------------------------------------------------------


def test_event_video_ships_disabled():
    """EVENT_VIDEO_ENABLED must default False until the pipeline runs on the board.

    Not a style preference: perception/video.py's GStreamer element chain
    has never been executed on this hardware (its module docstring says so
    under an explicit UNVERIFIED heading), and the camera itself has never
    been proven to enumerate under VIN power, which is the field topology
    (docs/KNOWN_GAPS.md). Flipping this on is a deliberate act with a human
    present, not something a merge should be able to do quietly.
    """
    assert config.EVENT_VIDEO_ENABLED is False


def test_confirm_window_covers_every_bounded_stage_before_the_decision():
    """The keep/discard decision's bounded stages must fit inside the window.

    ADR 0020 B3 wants the decision within ~15-20s of wake, and
    EVENT_VIDEO_CONFIRM_WINDOW_S records that budget. Nothing enforces it
    at runtime - the reflex loop is synchronous and has no watchdog - so
    this test is the enforcement. Worst case is every camera-open retry
    burning its full backoff, the vision-check burst at its configured
    spacing, then one detect_vision() call timing out. fuse() and decide()
    are pure and contribute nothing measurable.
    """
    worst_case_s = (
        config.CAMERA_OPEN_RETRIES * config.CAMERA_OPEN_RETRY_BACKOFF_S
        + config.VISION_CHECK_FRAME_COUNT * config.CAMERA_BURST_INTERVAL_S
        + config.VISION_INFERENCE_TIMEOUT_S
    )
    assert worst_case_s <= config.EVENT_VIDEO_CONFIRM_WINDOW_S, (
        f"Worst-case time to the keep/discard decision is now {worst_case_s}s, "
        f"past the {config.EVENT_VIDEO_CONFIRM_WINDOW_S}s window ADR 0020 B3 "
        "budgets. Either the window moves and the ADR is revisited, or the "
        "stage that grew comes back down."
    )


def test_retreat_tail_is_longer_than_the_jpeg_post_fire_tail():
    """The video tail must exceed the burst tail it replaces, or it buys nothing.

    EVENT_VIDEO_RETREAT_TAIL_S replaces CAPTURE_POST_FIRE_TAIL_S rather
    than adding to it (services/reflex_loop.py). If it ever dropped to or
    below 2s, the recording would stop moments after the horn and show
    none of the retreat - which is the half of the encounter ADR 0020 B4
    exists to capture.
    """
    assert config.EVENT_VIDEO_RETREAT_TAIL_S > reflex_loop.CAPTURE_POST_FIRE_TAIL_S


def test_scratch_dir_is_a_real_subdirectory_of_the_capture_dir():
    """Scratch must sit under CAPTURE_DIR, and must not *be* it.

    Two separate hazards in one relationship. Under: commit_video() ends in
    os.replace(), which is only atomic within a single filesystem, and on
    the board CAPTURE_DIR's partition and the container's /tmp are
    different mounts. Not equal: clear_orphaned_scratch() deletes every
    file it finds in the scratch directory, so pointing it at CAPTURE_DIR
    would turn a startup cleanup into a wipe of confirmed captures - the
    exact thing ADR 0020 Decision C forbids.
    """
    assert config.EVENT_VIDEO_SCRATCH_DIR != config.CAPTURE_DIR
    assert config.CAPTURE_DIR in config.EVENT_VIDEO_SCRATCH_DIR.parents


def test_event_video_suffix_is_a_usable_extension():
    """The suffix is concatenated straight onto the committed filename stem.

    perception/storage.py builds `f"{_event_prefix(tag)}{suffix}"`, so a
    suffix missing its dot silently produces `..._alert1mkv` - a file no
    player will open by extension and no glob will match.
    """
    assert config.EVENT_VIDEO_SUFFIX.startswith(".")
    assert len(config.EVENT_VIDEO_SUFFIX) > 1


def test_event_video_dimensions_are_even():
    """H.264 4:2:0 (NV12) chroma is subsampled 2x in both axes - odd sizes fail.

    v4l2h264enc rejects or silently crops an odd width/height rather than
    telling the caller, and the failure would first appear as an empty
    scratch file in the field.
    """
    assert config.EVENT_VIDEO_WIDTH > 0 and config.EVENT_VIDEO_WIDTH % 2 == 0
    assert config.EVENT_VIDEO_HEIGHT > 0 and config.EVENT_VIDEO_HEIGHT % 2 == 0


def test_event_video_framerate_and_bitrate_are_positive():
    """Both go straight into the pipeline description as caps/controls values.

    A zero framerate produces `framerate=0/1`, which no source will
    negotiate; a zero bitrate asks the encoder for no output at all.
    """
    assert config.EVENT_VIDEO_FRAMERATE >= 1
    assert config.EVENT_VIDEO_BITRATE_BPS > 0


def test_frame_timeout_covers_at_least_one_frame_interval():
    """Frame pulls must wait longer than the pipeline takes to make a frame.

    EVENT_VIDEO_FRAME_TIMEOUT_S bounds each try-pull-sample. If it dropped
    below 1/framerate, every pull would time out on a perfectly healthy
    pipeline and the vision check would see no frames at all - degrading
    to "camera failed" on a camera that is working.
    """
    frame_interval_s = 1.0 / config.EVENT_VIDEO_FRAMERATE
    assert config.EVENT_VIDEO_FRAME_TIMEOUT_S > frame_interval_s


def test_stop_timeout_is_positive():
    """Bounds the EOS wait in perception/video.py; 0 would truncate every clip."""
    assert config.EVENT_VIDEO_STOP_TIMEOUT_S > 0


def test_worst_case_clip_stays_well_inside_the_low_disk_headroom():
    """One event's recording must not by itself threaten the disk headroom.

    Worst case is a clip that runs the full confirm window, the whole
    actuator sequence (bounded by the per-actuator Bridge.call timeouts)
    and then the entire retreat tail, all at the configured bitrate. If
    that ever approached CAPTURE_LOW_DISK_HEADROOM_BYTES, a single night's
    events could fill the partition between visits - and nothing deletes
    committed captures to make room (ADR 0020 Decision C).
    """
    worst_case_s = (
        config.EVENT_VIDEO_CONFIRM_WINDOW_S
        + config.BRIDGE_HORN_CALL_TIMEOUT_S
        + config.BRIDGE_LED_CALL_TIMEOUT_S
        + config.BRIDGE_IR_CALL_TIMEOUT_S
        + config.EVENT_VIDEO_RETREAT_TAIL_S
    )
    worst_case_bytes = worst_case_s * config.EVENT_VIDEO_BITRATE_BPS / 8
    assert worst_case_bytes < config.CAPTURE_LOW_DISK_HEADROOM_BYTES / 10, (
        f"A single worst-case clip is now ~{worst_case_bytes / 1e6:.0f} MB against a "
        f"{config.CAPTURE_LOW_DISK_HEADROOM_BYTES / 1e6:.0f} MB headroom - too close to "
        "let a busy night run unattended."
    )
