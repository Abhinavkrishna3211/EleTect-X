"""Invariant checks for services/config.py, not restatements of its values.

Each test asserts a relationship that has to hold for the constant's own
documented rationale to still be true - not just that the constant exists
or equals a hardcoded literal, which would only re-encode the value and
never catch drift.
"""

import importlib
import os
import re
import subprocess
import sys
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


def test_the_watch_pulse_fits_inside_the_mcu_duty_budget():
    """The two illumination constants must stay inside the caps the MCU enforces.

    IR_WATCH_PULSE_MS and IR_WATCH_MIN_INTERVAL_S mirror IR_PULSE_MAX_MS and
    IR_MIN_INTERVAL_MS in device/mcu/src/config.h. The MCU stays
    authoritative - it clamps a long pulse and refuses an early one
    regardless of what is asked here - so neither of these can make the
    hardware unsafe. What they can do is make the MPU ask for things it will
    not get, once per poll for up to 45s per event, which turns a normal
    night into a log full of refusals and spends a Bridge round-trip each
    time to learn nothing.

    Read out of config.h rather than duplicated, because a mirrored constant
    with nothing comparing it to its original is how these drift.
    """
    pulse_cap_ms = _read_mcu_define("IR_PULSE_MAX_MS")
    min_interval_ms = _read_mcu_define("IR_MIN_INTERVAL_MS")

    assert config.IR_WATCH_PULSE_MS <= pulse_cap_ms, (
        f"IR_WATCH_PULSE_MS ({config.IR_WATCH_PULSE_MS}) exceeds the MCU's "
        f"IR_PULSE_MAX_MS ({pulse_cap_ms}) - every pulse would be silently "
        "clamped, so the frames would be lit for less time than the exposure "
        "was locked for."
    )
    assert config.IR_WATCH_MIN_INTERVAL_S * 1000.0 >= min_interval_ms, (
        f"IR_WATCH_MIN_INTERVAL_S ({config.IR_WATCH_MIN_INTERVAL_S}s) is "
        f"shorter than the MCU's IR_MIN_INTERVAL_MS ({min_interval_ms}ms) - "
        "the watch would ask faster than the duty gate admits and most polls "
        "would be refused."
    )


def test_the_watch_can_actually_illuminate_more_than_once():
    """A pacing interval longer than the window would make this whole path dead code.

    Not a hardware constraint - a design one. The extended watch is the
    window a night event actually runs in (ADR 0022 / the cold-trigger
    path), and if only one pulse fits in it the illuminator cannot cover an
    animal that walks into frame late, which is the case it exists for.
    """
    assert config.IR_WATCH_MIN_INTERVAL_S < config.VISION_WATCH_EXTENDED_S / 2.0


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


# --- deterrence_scope_labels() / NODE_DETERRENCE_SCOPE ----------------------


def test_deterrence_scope_ships_elephant_only_by_default():
    """The committed default must be the field trial's actual configuration.

    Nothing in this pass may enable boar_only or both live - that is a
    commissioning decision, not a code default.
    """
    assert config.NODE_DETERRENCE_SCOPE == "elephant_only"
    assert config.DETERRENT_TARGET_LABELS == ("Elephant",)
    assert config.EVENT_VIDEO_TARGET_LABELS == ("Elephant",)


def test_elephant_only_resolves_to_todays_byte_for_byte_value():
    """Deriving these two constants must not have changed what they resolve to."""
    assert config.deterrence_scope_labels("elephant_only") == (("Elephant",), ("Elephant",))


def test_boar_only_deters_and_films_only_boar():
    """Elephant must not appear in either list under boar_only."""
    assert config.deterrence_scope_labels("boar_only") == (("Boar",), ("Boar",))


def test_both_deters_and_films_both_species():
    """Both labels appear in both lists under the symmetric "both" state."""
    assert config.deterrence_scope_labels("both") == (
        ("Elephant", "Boar"),
        ("Elephant", "Boar"),
    )


def test_an_unrecognized_scope_falls_back_to_elephant_only_instead_of_raising():
    """A typo in a per-node environment variable must not crash the reflex loop."""
    assert config.deterrence_scope_labels("bogus") == (("Elephant",), ("Elephant",))
    assert config.deterrence_scope_labels("") == (("Elephant",), ("Elephant",))


def test_a_scope_names_any_combination_of_the_registry():
    """The point of the change: a combination the old three states could not express.

    Elephant-and-fox-but-not-boar is not an exotic case - it is a node at
    a site with no boar pressure - and under the three-state switch there
    was no string that said it.
    """
    assert config.parse_scope_labels("Elephant,Fox") == ("Elephant", "Fox")
    assert config.parse_scope_labels("Boar,Fox") == ("Boar", "Fox")
    assert config.parse_scope_labels("Elephant,Boar,Fox") == ("Elephant", "Boar", "Fox")


def test_order_and_case_and_spacing_cannot_split_one_scope_into_two():
    """Equivalent spellings must be one scope, because this value keys the DB.

    If " fox , ELEPHANT " and "Elephant,Fox" resolved differently they
    would open two experience databases, and a node would silently lose
    its learned policy to a whitespace edit in a compose file.
    """
    canonical = config.parse_scope_labels("Elephant,Fox")
    assert config.parse_scope_labels("Fox,Elephant") == canonical
    assert config.parse_scope_labels(" fox , ELEPHANT ") == canonical
    assert config.parse_scope_labels("Elephant,Fox,Elephant") == canonical


def test_the_resolved_order_follows_the_registry_not_the_operator():
    """Registry order, so the tuple is canonical rather than as-typed."""
    assert config.parse_scope_labels("Fox,Boar,Elephant") == config.DETERRABLE_LABELS


def test_all_tracks_the_registry_rather_than_a_hand_written_list():
    """The alias that must not need editing when a species is added.

    Asserted against DETERRABLE_LABELS rather than a literal: a hardcoded
    ("Elephant", "Boar", "Fox") here would pass forever while silently
    becoming wrong the next time the registry grows.
    """
    assert config.parse_scope_labels("all") == config.DETERRABLE_LABELS
    assert "Fox" in config.parse_scope_labels("all")


def test_an_unknown_species_is_dropped_without_taking_the_rest_with_it():
    """Dropping one bad label beats discarding the operator's whole intent.

    Deliberately asserted on a scope with no Elephant in it. "Elephant,
    Tiger" would be the obvious case to write and it proves nothing: its
    expected value is ("Elephant",), which is also what the
    everything-was-dropped fallback returns, so the test would pass just
    as happily against an implementation that threw the whole list away.
    """
    assert config.parse_scope_labels("Boar,Tiger,Fox") == ("Boar", "Fox")
    # Nothing usable left, so this one really is the fallback.
    assert config.parse_scope_labels("Tiger,Leopard") == ("Elephant",)


def test_every_legacy_alias_still_resolves_byte_for_byte():
    """No deployed node may be repointed by scopes having become free-form."""
    assert config.parse_scope_labels("elephant_only") == ("Elephant",)
    assert config.parse_scope_labels("boar_only") == ("Boar",)
    assert config.parse_scope_labels("both") == ("Elephant", "Boar")
    assert config.parse_scope_labels("none") == ()


def test_fox_is_an_ordinary_scope_choice_and_not_a_mode(monkeypatch):
    """Fox is deterred because a node was commissioned for it, nothing else.

    It was previously appended to both target lists by an operating-mode
    flag, after the scope had already resolved - so the node deterred a
    species its own configuration did not name, and no scope string could
    turn it off. Scope is the only thing that decides this now.
    """
    assert "Fox" not in config.parse_scope_labels("both")
    assert "Fox" in config.parse_scope_labels("Elephant,Boar,Fox")

    monkeypatch.setenv("ELETECT_DETERRENCE_SCOPE", "Elephant,Fox")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.DETERRENT_TARGET_LABELS == ("Elephant", "Fox")
        assert reloaded.EVENT_VIDEO_TARGET_LABELS == ("Elephant", "Fox")
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_a_label_list_scope_survives_a_cold_import():
    """The import-order trap: this fails as NameError at startup, not as a wrong value.

    EXPERIENCE_DB_PATH is evaluated at import time, and a label-list
    scope reaches parse_scope_labels() through experience_db_filename().
    Define the parser below that line - beside deterrence_scope_labels(),
    which is the natural place for it - and a field node configured with
    exactly the scope the parser exists to support dies on import.

    Run in a subprocess, which is the only thing that reproduces it.
    Calling parse_scope_labels() directly cannot: by then the module has
    finished importing. Nor can importlib.reload(), which re-executes the
    body into the *existing* module namespace, so the previous import's
    binding is still there to satisfy the premature call - a reload-based
    version of this test passes against the broken order. Only a cold
    interpreter has the empty namespace a field node boots with.
    """
    env = dict(os.environ, ELETECT_DETERRENCE_SCOPE="Elephant,Boar,Fox")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from services import config\n"
            "print(config.DETERRENT_TARGET_LABELS)\n"
            "print(config.EXPERIENCE_DB_PATH.name)\n",
        ],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"importing config with a label-list scope failed:\n{result.stderr}"
    )
    labels, db_name = result.stdout.splitlines()[:2]
    assert labels == "('Elephant', 'Boar', 'Fox')"
    assert db_name == "experience-elephant-boar-fox.sqlite3"


def test_filming_can_be_widened_without_widening_deterrence(monkeypatch):
    """The asymmetric case, and the reason it is a second scope not a fourth state.

    Collect the footage that shows whether deterring a species is worth
    doing, before any horn fires at one.
    """
    monkeypatch.setenv("ELETECT_DETERRENCE_SCOPE", "Elephant")
    monkeypatch.setenv("ELETECT_EVENT_VIDEO_SCOPE", "Elephant,Boar,Fox")
    reloaded = importlib.reload(config)
    try:
        assert reloaded.DETERRENT_TARGET_LABELS == ("Elephant",)
        assert reloaded.EVENT_VIDEO_TARGET_LABELS == ("Elephant", "Boar", "Fox")
    finally:
        monkeypatch.undo()
        importlib.reload(config)


# --- EXPERIENCE_DB_PATH derivation -------------------------------------------


def test_experience_db_path_derivation_for_all_three_scopes():
    """Reverting NODE_DETERRENCE_SCOPE to elephant_only must restore the trial's own DB.

    That is the whole safety property this derivation buys: there is no
    separate archive-or-reset step whose omission could silently ship a
    boar-shaped policy into the field trial.
    """
    for scope, expected_name in (
        ("elephant_only", "experience.sqlite3"),
        ("boar_only", "experience-boar_only.sqlite3"),
        ("both", "experience-both.sqlite3"),
    ):
        assert config.experience_db_filename(scope) == expected_name


def test_a_label_list_keys_its_database_off_the_resolved_labels():
    """Equivalent spellings must open one database, not several.

    The raw string cannot be the key here the way it is for an alias:
    "Fox,Elephant" and " elephant , fox " are the same scope, and keying
    on the text would hand each of them its own empty policy.
    """
    expected = "experience-elephant-fox.sqlite3"
    assert config.experience_db_filename("Elephant,Fox") == expected
    assert config.experience_db_filename("Fox,Elephant") == expected
    assert config.experience_db_filename(" fox , ELEPHANT ") == expected


def test_widening_a_scope_opens_a_different_database():
    """Not a bug - but it is a cost, and it should be visible in a test.

    A node moved from "both" to "Elephant,Boar,Fox" starts the bandit
    cold. Its old policy stays on disk and comes back if the scope is
    restored, which is the property worth having; what it does not do is
    carry over.
    """
    assert config.experience_db_filename("both") == "experience-both.sqlite3"
    assert (
        config.experience_db_filename("Elephant,Boar,Fox")
        == "experience-elephant-boar-fox.sqlite3"
    )


def test_elephant_only_experience_db_path_is_todays_unqualified_filename():
    """The shipped default must resolve to exactly today's DB, unqualified."""
    assert config.EXPERIENCE_DB_PATH == config.DATA_DIR / "experience.sqlite3"
