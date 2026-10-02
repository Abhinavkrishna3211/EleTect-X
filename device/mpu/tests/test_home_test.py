"""Behavioral tests for services/home_test.py (HOME_TEST_MODE).

No hardware, no real threads: every test drives HomeTestSession's internal
methods directly (_rotate_ring, _run_one_poll, _advance_encounter,
_start_encounter, _close_encounter, _protect_frame) with a fake camera, a
scripted detect_vision, and an injectable spawn_deterrence, rather than
calling start()/stop() and racing real capture/inference daemon threads -
the same "test the loop body, not the loop" approach as
tests/test_reflex_loop.py's _fire() helper, which never spins up a real
Bridge either.

config.HOME_TEST_DIR/RING_DIR/ENCOUNTERS_DIR/DETECTIONS_PATH are monkeypatched
to a pytest tmp_path per test (the home_test_paths fixture) so nothing here
ever touches the real device/mpu/services/data/home_test/ directory a
developer's own local run might have populated.

Coverage matches the plan's stated list: ring rotation, protect-on-detection
(pre-roll and post-roll), departure timeout, the max-encounter cap, and a
below-threshold detection that is logged but never starts an encounter.
"""

import json
import threading
import time
from pathlib import Path

import pytest

from perception.camera import Frame
from perception.detector import Detection
from perception.night import frames_are_night
from services import config, home_test

np = pytest.importorskip("numpy")

ELEPHANT_HIGH = Detection(label="Elephant", confidence=0.95, x=0, y=0, width=10, height=10)
# Below HOME_TEST_FIRE_MIN_CONFIDENCE but ABOVE HOME_TEST_REVIEW_MIN_CONFIDENCE -
# the marginal band the review-still directory exists to capture.
ELEPHANT_LOW = Detection(label="Elephant", confidence=0.30, x=0, y=0, width=10, height=10)
# Below the review floor too. Derived from the constant rather than hardcoded:
# the floor has already moved once (0.45 -> 0.25 on 23 Sept) and silently
# carried a fixture that was no longer below it.
ELEPHANT_BELOW_REVIEW = Detection(
    label="Elephant",
    confidence=round(config.HOME_TEST_REVIEW_MIN_CONFIDENCE / 2, 3),
    x=0,
    y=0,
    width=10,
    height=10,
)
# A box spanning the whole 16x16 test frame - area fraction 1.0, well over
# HOME_TEST_MAX_BOX_AREA_FRACTION - standing in for the detector's degenerate
# frame-filling mode.
FULL_FRAME_ELEPHANT = Detection(label="Elephant", confidence=0.95, x=0, y=0, width=16, height=16)


def _gray_frame(value: int = 40):
    """A flat mid-grey BGR image - equal channels, so HSV saturation is 0. Reads as night."""
    return np.full((16, 16, 3), value, dtype=np.uint8)


def _colour_frame(bgr: tuple[int, int, int] = (20, 90, 200)):
    """A flat saturated BGR image - unequal channels, high HSV saturation. Reads as day."""
    frame = np.zeros((16, 16, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


class _ManualClock:
    """A monotonic clock a test can advance by hand, for ExposureAutoLock's rate limiting."""

    def __init__(self, start: float = 0.0) -> None:
        """Start the clock at `start`."""
        self.value = start

    def __call__(self) -> float:
        """Read the current value."""
        return self.value

    def advance(self, seconds: float) -> None:
        """Move the clock forward by `seconds`."""
        self.value += seconds


def _real_is_night(frames: list[Frame]) -> bool | None:
    """The same NightDecideFn shape main.py's _is_night() binds - unwraps .image itself.

    Used instead of a trivial fake wherever a test needs to prove
    ExposureAutoLock.maybe_update() is actually being called with Frame
    objects (not raw images) end to end through home_test.py's call site -
    see the Frame/raw-image contract fix in perception/night.py.
    """
    return frames_are_night([f.image for f in frames], config.NIGHT_SATURATION_THRESHOLD)


class _FakeCamera:
    """Minimal CameraProtocol stand-in - never opened by these tests.

    HomeTestSession's constructor calls camera_factory() but these tests
    never call start(), so open()/capture_frame()/close() are never
    actually invoked - only present so the constructor has something to
    call.

    lock_result/restore_result are configurable per instance, and every
    call is counted, so a test can script a failing lock or restore
    (previously untested anywhere) and assert on how many times each was
    actually called.
    """

    def __init__(self, lock_result: bool = True, restore_result: bool = True) -> None:
        """Create a fake camera whose lock/restore calls return the given results."""
        self.lock_result = lock_result
        self.restore_result = restore_result
        self.lock_calls = 0
        self.restore_calls = 0

    def open(self) -> None:
        pass

    def capture_frame(self):
        return None

    def lock_night_exposure(self) -> bool:
        self.lock_calls += 1
        return self.lock_result

    def restore_auto_exposure(self) -> bool:
        self.restore_calls += 1
        return self.restore_result

    def close(self) -> None:
        pass


def _frames(count: int) -> list[Frame]:
    """A burst of `count` Frame objects with distinct fake images."""
    return [Frame(image=f"frame-{i}", index=i, timestamp_s=float(i)) for i in range(count)]


def _np_frames(count: int, height: int = 1080, width: int = 1920) -> list[Frame]:
    """A burst of real ndarray-backed frames so the box-area filter can read a shape."""
    return [
        Frame(image=np.zeros((height, width, 3), dtype=np.uint8), index=i, timestamp_s=float(i))
        for i in range(count)
    ]


def _constant_detect_vision(detections: list[Detection]):
    """VisionDetectFn stand-in: every frame in the burst gets the same detections."""

    def _detect(images):
        return [list(detections) for _ in images]

    return _detect


def _is_night_unmeasurable(images):
    """A default is_night() fake: always unmeasurable, so exposure-lock tests opt in explicitly."""
    return None


def _make_session(
    *,
    detect_vision=None,
    footfall_kwargs=None,
    spawn_deterrence=None,
    clock=None,
    monotonic=None,
    camera=None,
):
    """A HomeTestSession wired to fakes throughout.

    footfall_kwargs is merged over a default `is_night` fake rather than
    replaced outright, so tests that only care about the ring/encounter
    machinery (most of this file) do not also have to supply one just to
    satisfy HomeTestSession.__init__'s ExposureAutoLock construction.
    camera defaults to a fresh _FakeCamera() instance; pass one in to
    script lock/restore results.
    """
    merged_footfall_kwargs = dict(footfall_kwargs) if footfall_kwargs is not None else {}
    merged_footfall_kwargs.setdefault("is_night", _is_night_unmeasurable)
    return home_test.HomeTestSession(
        detect_vision if detect_vision is not None else _constant_detect_vision([]),
        merged_footfall_kwargs,
        camera_factory=(lambda: camera) if camera is not None else _FakeCamera,
        clock=clock if clock is not None else time.time,
        monotonic=monotonic if monotonic is not None else time.monotonic,
        spawn_deterrence=spawn_deterrence if spawn_deterrence is not None else (lambda fn: None),
    )


@pytest.fixture
def home_test_paths(tmp_path, monkeypatch):
    """Redirect every HOME_TEST_* path constant into a throwaway tmp_path.

    Also pins DETERRENT_TARGET_LABELS to ("Elephant",) regardless of the
    real ELETECT_DETERRENCE_SCOPE in this environment - Elephant is not
    burst-majority-gated (services/reflex_loop.py's _vision_check()
    docstring), so a single qualifying detection in a fake burst is enough,
    keeping these tests independent of Boar's majority-gate behaviour
    (that gate has its own coverage in tests/test_reflex_loop.py).
    """
    base = tmp_path / "home_test"
    monkeypatch.setattr(config, "HOME_TEST_DIR", base)
    monkeypatch.setattr(config, "HOME_TEST_RING_DIR", base / "ring")
    monkeypatch.setattr(config, "HOME_TEST_ENCOUNTERS_DIR", base / "encounters")
    monkeypatch.setattr(config, "HOME_TEST_REVIEW_DIR", base / "review_frames")
    monkeypatch.setattr(config, "HOME_TEST_DETECTIONS_PATH", base / "detections.jsonl")
    monkeypatch.setattr(config, "HOME_TEST_EXPOSURE_LOG_PATH", base / "exposure_decisions.jsonl")
    monkeypatch.setattr(config, "HOME_TEST_CAMERA_COVERED_LOG_PATH", base / "camera_covered.jsonl")
    monkeypatch.setattr(config, "HOME_TEST_TELEMETRY_PATH", base / "telemetry.jsonl")
    monkeypatch.setattr(config, "HOME_TEST_MANUAL_FIRE_TRIGGER_PATH", base / "manual-fire-request")
    monkeypatch.setattr(config, "DETERRENT_TARGET_LABELS", ("Elephant",))
    return base


# ---------------------------------------------------------------------------
# deterrence worker
# ---------------------------------------------------------------------------


def test_default_spawn_deterrence_runs_every_call_on_one_persistent_thread(home_test_paths):
    """The real (non-test) spawn_deterrence must serialize every call onto a single thread.

    Every other test in this file passes spawn_deterrence=lambda fn: fn() (via
    _make_session's default), which never exercises the actual production
    implementation - _spawn_deterrence_thread and _deterrence_loop - at all.
    That gap is exactly how the previous per-encounter
    `threading.Thread(...).start()` design shipped a bug: it satisfied every
    existing test while breaking cognition/experience.py's ExperienceStore,
    which back then cached a single sqlite3.Connection on whichever thread
    first called it and refused every other one. CPython can reuse an exited
    thread's OS identifier for a later thread, so some record_trigger() calls
    landed back on the connection's original owning thread by luck and others
    raised sqlite3.ProgrammingError - intermittently, and silently swallowed
    by _fire_deterrence's own broad except. The store carries its own lock
    now, so that particular failure is fixed at its source; this test stands
    because the single USB camera and the single horn still need one
    encounter's deterrence to finish before the next one starts.
    This constructs a session with the constructor's real default
    (bypassing _make_session's no-op override), drives _deterrence_loop on
    a worker thread directly (never start()/stop()), and asserts every
    queued call actually lands on that same one thread.
    """
    session = home_test.HomeTestSession(
        _constant_detect_vision([]),
        {"is_night": _is_night_unmeasurable},
        camera_factory=_FakeCamera,
    )
    worker = threading.Thread(target=session._deterrence_loop, daemon=True)
    worker.start()
    try:
        thread_ids: list[int] = []
        all_ran = threading.Event()

        def _record() -> None:
            thread_ids.append(threading.get_ident())
            if len(thread_ids) == 3:
                all_ran.set()

        for _ in range(3):
            session._spawn_deterrence(_record)

        assert all_ran.wait(timeout=2.0), "queued deterrence calls never ran"
        assert thread_ids == [worker.ident] * 3, "every call must run on the one worker thread"
    finally:
        session._stop.set()
        worker.join(timeout=2.0)


def _alive_thread() -> threading.Thread:
    """A real, running thread standing in for one of the session's daemon loops.

    Blocks on its own Event forever (until the test process exits, since it
    is a daemon thread) - just needs to report is_alive() == True for
    is_healthy()'s thread-liveness half of the check.
    """
    thread = threading.Thread(target=threading.Event().wait, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# stall watchdog
# ---------------------------------------------------------------------------


def test_is_healthy_true_when_threads_alive_and_heartbeats_fresh(home_test_paths):
    """Alive threads plus recently-beaten heartbeats reads as healthy."""
    session = _make_session()
    session._capture_thread = _alive_thread()
    session._inference_thread = _alive_thread()
    session._deterrence_thread = _alive_thread()

    assert session.is_healthy() is True


def test_is_healthy_false_when_a_heartbeat_goes_stale(home_test_paths):
    """A single stale heartbeat fails health even though every thread is still alive.

    This is the case _run_guarded's own hard-exit-on-exception cannot catch:
    a thread wedged on a hung call never raises and never dies, so nothing
    about it looks wrong except that its heartbeat stopped advancing.
    """
    clock = _ManualClock(start=1_000_000.0)
    session = _make_session(monotonic=clock)
    session._capture_thread = _alive_thread()
    session._inference_thread = _alive_thread()
    session._deterrence_thread = _alive_thread()

    clock.advance(config.HOME_TEST_STALL_TIMEOUT_S + 1.0)

    assert session.is_healthy() is False, "a stale heartbeat must fail health despite alive threads"


def test_is_healthy_false_when_a_thread_has_died(home_test_paths):
    """A dead thread fails health regardless of how fresh the heartbeats are."""
    session = _make_session()
    dead = threading.Thread(target=lambda: None)
    dead.start()
    dead.join()
    session._capture_thread = dead
    session._inference_thread = _alive_thread()
    session._deterrence_thread = _alive_thread()

    assert session.is_healthy() is False


# ---------------------------------------------------------------------------
# telemetry
# ---------------------------------------------------------------------------


def test_maybe_log_telemetry_writes_one_line_per_interval(home_test_paths):
    """Telemetry is rate-limited like exposure decisions - once per configured interval."""
    clock = _ManualClock(start=1_000_000.0)
    session = _make_session(clock=clock)
    session._last_inference_latency_ms = 123.4

    session._maybe_log_telemetry()
    clock.advance(config.HOME_TEST_TELEMETRY_INTERVAL_S - 1.0)
    session._maybe_log_telemetry()

    lines = config.HOME_TEST_TELEMETRY_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1, "a call before the interval elapses must not write a second line"

    clock.advance(2.0)
    session._maybe_log_telemetry()

    lines = config.HOME_TEST_TELEMETRY_PATH.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2, "a call after the interval elapses must write a new line"
    record = json.loads(lines[0])
    assert record["inference_latency_ms"] == 123.4, (
        "the last measured inference latency must be recorded"
    )


# ---------------------------------------------------------------------------
# ring rotation
# ---------------------------------------------------------------------------


def test_rotate_ring_deletes_frames_older_than_preroll_keeps_newer(home_test_paths):
    """_rotate_ring() deletes only frames older than HOME_TEST_PREROLL_S."""
    session = _make_session()
    now = 1_000_000.0
    old_path = config.HOME_TEST_RING_DIR / f"{now - config.HOME_TEST_PREROLL_S - 5:018.6f}_1.jpg"
    new_path = config.HOME_TEST_RING_DIR / f"{now - 5:018.6f}_2.jpg"
    old_path.write_bytes(b"x")
    new_path.write_bytes(b"x")

    session._rotate_ring(now)

    assert not old_path.exists(), "a ring frame older than HOME_TEST_PREROLL_S must be deleted"
    assert new_path.exists(), "a ring frame within HOME_TEST_PREROLL_S must survive rotation"


def test_rotate_ring_ignores_files_it_cannot_parse_a_timestamp_from(home_test_paths):
    """A stray non-conforming .jpg in the ring dir must not crash rotation."""
    session = _make_session()
    junk = config.HOME_TEST_RING_DIR / "not-a-timestamp.jpg"
    junk.write_bytes(b"x")

    session._rotate_ring(1_000_000.0)

    assert junk.exists()


# ---------------------------------------------------------------------------
# detection logging - unconditional, independent of the fire gate
# ---------------------------------------------------------------------------


def test_run_one_poll_logs_every_detection_unconditionally(home_test_paths):
    """Every Detection in the burst gets one JSONL line, gate or no gate."""
    session = _make_session(detect_vision=_constant_detect_vision([ELEPHANT_LOW]))

    # Real ndarray frames: ELEPHANT_LOW sits above the review floor, so this
    # poll also writes a review still, and that path really encodes a JPEG.
    session._run_one_poll(_np_frames(2))

    lines = config.HOME_TEST_DETECTIONS_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2, "one logged line per frame in the burst, unconditionally"
    assert '"label": "Elephant"' in lines[0]


def test_run_one_poll_with_no_detections_writes_nothing(home_test_paths):
    """No boxes at all means nothing to log - an empty write is skipped."""
    session = _make_session(detect_vision=_constant_detect_vision([]))

    session._run_one_poll(_frames(2))

    assert not config.HOME_TEST_DETECTIONS_PATH.exists()


def test_run_one_poll_below_fire_threshold_is_logged_but_does_not_start_encounter(
    home_test_paths,
):
    """A weak-but-confirmed detection must log but never start an encounter.

    ELEPHANT_LOW is a real _vision_check() confirmation (Elephant needs no
    burst majority), but HOME_TEST_FIRE_MIN_CONFIDENCE holds the
    fire/protect decision back - detection logging must not care either way.
    """
    session = _make_session(detect_vision=_constant_detect_vision([ELEPHANT_LOW]))

    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS + 2):
        session._run_one_poll(_np_frames(1))

    assert session._encounter is None
    lines = config.HOME_TEST_DETECTIONS_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == config.HOME_TEST_FIRE_CONSECUTIVE_POLLS + 2


def test_meets_fire_bar_requires_home_test_fire_min_confidence(home_test_paths):
    """_meets_fire_bar() is a plain confidence-floor check over target labels."""
    session = _make_session()

    assert session._meets_fire_bar([[ELEPHANT_LOW]]) is False
    assert session._meets_fire_bar([[ELEPHANT_HIGH]]) is True
    assert session._meets_fire_bar([[]]) is False


# ---------------------------------------------------------------------------
# review stills - evidence for a detection that misses the fire gate
# ---------------------------------------------------------------------------

BOAR_REVIEW = Detection(label="Boar", confidence=0.55, x=10, y=10, width=200, height=150)
BOAR_REVIEW_STRONGER = Detection(label="Boar", confidence=0.58, x=10, y=10, width=200, height=150)


def test_log_detections_saves_a_review_still_for_a_sub_fire_bar_detection(home_test_paths):
    """A detection above HOME_TEST_REVIEW_MIN_CONFIDENCE but below the fire bar gets one still.

    This is the exact gap the night of 10-11 Sept 2026 exposed: a Boar
    cluster peaked at 0.631 confidence but never opened a formal encounter,
    and by morning its ring frames had long aged out - zero image evidence
    survived, only the detections.jsonl rows.
    """
    session = _make_session()

    session._log_detections(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert len(saved) == 1, "exactly one review still must be saved"
    assert "Boar" in saved[0].name
    assert "0.550" in saved[0].name


def test_maybe_save_review_still_skips_a_detection_below_the_review_floor(home_test_paths):
    """A detection under HOME_TEST_REVIEW_MIN_CONFIDENCE is pure noise - nothing is saved."""
    session = _make_session()

    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[ELEPHANT_BELOW_REVIEW]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert saved == [], "below-floor detections save nothing"


def test_maybe_save_review_still_throttles_repeat_saves_for_the_same_label(home_test_paths):
    """HOME_TEST_REVIEW_MIN_INTERVAL_S suppresses a second still too soon for the same label."""
    session = _make_session()

    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])
    session._maybe_save_review_still(
        1_000_000.0 + config.HOME_TEST_REVIEW_MIN_INTERVAL_S - 1.0,
        _np_frames(1),
        [[BOAR_REVIEW_STRONGER]],
    )

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert len(saved) == 1, "a second save inside the throttle interval must be dropped"


def test_maybe_save_review_still_saves_again_once_the_interval_elapses(home_test_paths):
    """Past HOME_TEST_REVIEW_MIN_INTERVAL_S, the same label may save a fresh still."""
    session = _make_session()

    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])
    session._maybe_save_review_still(
        1_000_000.0 + config.HOME_TEST_REVIEW_MIN_INTERVAL_S + 1.0,
        _np_frames(1),
        [[BOAR_REVIEW_STRONGER]],
    )

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert len(saved) == 2, "a save past the throttle interval must go through"


def test_maybe_save_review_still_is_skipped_while_an_encounter_is_active(home_test_paths):
    """An active encounter already protects its own ring frames continuously - no still needed."""
    session = _make_session()
    session._start_encounter(1_000_000.0)

    session._maybe_save_review_still(1_000_005.0, _np_frames(1), [[BOAR_REVIEW]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert saved == [], "no still while an encounter is open"


def test_maybe_save_review_still_stops_past_the_byte_cap(home_test_paths, monkeypatch):
    """Past HOME_TEST_REVIEW_MAX_TOTAL_BYTES, saving stops but nothing raises or is deleted."""
    session = _make_session()
    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])
    assert len(list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))) == 1
    monkeypatch.setattr(config, "HOME_TEST_REVIEW_MAX_TOTAL_BYTES", 1)
    session._review_bytes = 1

    session._maybe_save_review_still(
        1_000_000.0 + config.HOME_TEST_REVIEW_MIN_INTERVAL_S + 1.0,
        _np_frames(1),
        [[BOAR_REVIEW_STRONGER]],
    )

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert len(saved) == 1, "the cap must stop new saves without touching what is already there"


def test_maybe_save_review_still_swallows_an_encode_failure(home_test_paths, monkeypatch):
    """A cv2.imencode failure is logged and swallowed, never raised."""
    session = _make_session()
    monkeypatch.setattr(home_test.cv2, "imencode", lambda *args, **kwargs: (False, None))

    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert saved == [], "a failed encode must save nothing"


def test_maybe_save_review_still_swallows_a_write_failure(home_test_paths, monkeypatch):
    """An OSError writing the still is logged and swallowed, never raised."""
    session = _make_session()
    real_write_bytes = Path.write_bytes

    def _boom(self, data):
        if self.parent == config.HOME_TEST_REVIEW_DIR:
            raise OSError("disk full")
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", _boom)

    session._maybe_save_review_still(1_000_000.0, _np_frames(1), [[BOAR_REVIEW]])

    assert list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg")) == [], "a failed write must save nothing"


def test_maybe_save_review_still_skips_a_frame_filling_detection(home_test_paths):
    """A frame-filling box saves no still - it is the same artefact the fire gate drops.

    Added 11 Sept 2026 alongside the camera-covered streak alert: a covered
    lens was saving one near-identical blank-blob still every
    HOME_TEST_REVIEW_MIN_INTERVAL_S for ~40 minutes despite carrying no
    localisation information worth a human's review time.
    """
    session = _make_session()
    small_frames = _np_frames(1, height=16, width=16)

    session._maybe_save_review_still(1_000_000.0, small_frames, [[FULL_FRAME_ELEPHANT]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert saved == [], "a frame-filling detection must save nothing"


def test_maybe_save_review_still_still_saves_a_frame_filling_box_when_shape_is_unreadable(
    home_test_paths, monkeypatch
):
    """If the frame's shape cannot be read, the frame-filling skip must not run either.

    Mirrors _gate_results_without_degenerate_boxes' own degrade-safe rule:
    a shape-read failure must never manufacture a dropped detection, so a
    still is saved rather than silently losing evidence the caller
    cannot even confirm is degenerate. cv2.imencode is stubbed the same
    way test_maybe_save_review_still_swallows_an_encode_failure does,
    since a str-backed fake frame (no real .shape) cannot be encoded for
    real - only the shape-read fallback itself is under test here.
    """
    session = _make_session()
    monkeypatch.setattr(
        home_test.cv2, "imencode", lambda *args, **kwargs: (True, np.zeros(4, dtype=np.uint8))
    )

    session._maybe_save_review_still(1_000_000.0, _frames(1), [[FULL_FRAME_ELEPHANT]])

    saved = list(config.HOME_TEST_REVIEW_DIR.glob("*.jpg"))
    assert len(saved) == 1, "an unreadable shape must fall back to saving, not skipping"


# ---------------------------------------------------------------------------
# camera-possibly-covered detection (observational only - never touches the
# fire path: _encounter, _qualifying_window, or anything _advance_encounter
# reads)
# ---------------------------------------------------------------------------


def _covered_log_lines() -> list[dict]:
    """Parse every JSON line currently in HOME_TEST_CAMERA_COVERED_LOG_PATH, or [] if absent."""
    if not config.HOME_TEST_CAMERA_COVERED_LOG_PATH.exists():
        return []
    text = config.HOME_TEST_CAMERA_COVERED_LOG_PATH.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line]


def test_camera_covered_streak_logs_nothing_before_the_threshold(home_test_paths):
    """Fewer than HOME_TEST_CAMERA_COVERED_STREAK_POLLS drops in a row stays silent."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS - 1):
        session._update_camera_covered_state(True, False, 1_000_000.0)

    assert _covered_log_lines() == [], "no warning before the streak reaches the threshold"


def test_camera_covered_streak_logs_once_at_the_threshold_and_never_spams(home_test_paths):
    """The threshold poll logs exactly one 'covered' line, and staying covered logs no more."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS):
        session._update_camera_covered_state(True, False, 1_000_000.0)
    assert _covered_log_lines() == [
        {"wall_s": 1_000_000.0, "state": "covered", "reason": "frame_filling"}
    ]

    for _ in range(10):
        session._update_camera_covered_state(True, False, 1_000_050.0)
    assert _covered_log_lines() == [
        {"wall_s": 1_000_000.0, "state": "covered", "reason": "frame_filling"}
    ], "staying covered must not log a second time"


def test_camera_covered_streak_resets_silently_if_never_crossed_the_threshold(home_test_paths):
    """A short run of drops that never reaches the threshold clears with no log line at all."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS - 1):
        session._update_camera_covered_state(True, False, 1_000_000.0)
    session._update_camera_covered_state(False, False, 1_000_010.0)

    assert session._covered_streak == 0
    assert _covered_log_lines() == [], "a streak that never crossed the bar logs nothing on reset"


def test_camera_covered_logs_clear_once_the_streak_breaks_past_the_threshold(home_test_paths):
    """Once past the threshold, the first non-dropping poll logs one 'clear' line."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS):
        session._update_camera_covered_state(True, False, 1_000_000.0)
    session._update_camera_covered_state(False, False, 1_000_040.0)

    assert session._covered_streak == 0
    assert _covered_log_lines() == [
        {"wall_s": 1_000_000.0, "state": "covered", "reason": "frame_filling"},
        {"wall_s": 1_000_040.0, "state": "clear"},
    ]

    session._update_camera_covered_state(False, False, 1_000_041.0)
    assert len(_covered_log_lines()) == 2, "an already-clear camera must not log 'clear' again"


def test_update_camera_covered_state_never_touches_the_fire_path(home_test_paths):
    """Even a long covered streak leaves _encounter and _qualifying_window untouched."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS * 2):
        session._update_camera_covered_state(True, False, 1_000_000.0)

    assert session._encounter is None, "the covered-streak tracker must never open an encounter"
    assert list(session._qualifying_window) == [], "the covered-streak tracker must not touch it"


def test_run_one_poll_flags_camera_covered_after_a_sustained_frame_filling_run(home_test_paths):
    """A real covered-lens pattern - a frame-filling box every poll - trips the alert.

    Reproduces the 11 Sept incident: a frame-filling "Elephant" every poll
    for HOME_TEST_CAMERA_COVERED_STREAK_POLLS seconds, correctly excluded
    from the fire gate throughout, but now also surfaced as a probable
    obstruction instead of vanishing silently.
    """
    session = _make_session(detect_vision=_constant_detect_vision([FULL_FRAME_ELEPHANT]))
    small_frames = _np_frames(1, height=16, width=16)

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS):
        session._run_one_poll(small_frames)

    assert session._encounter is None, "a frame-filling box must still never open an encounter"
    lines = _covered_log_lines()
    assert len(lines) == 1
    assert lines[0]["state"] == "covered"


# ---------------------------------------------------------------------------
# low-texture (partial-covering) half of the camera-covered check
# ---------------------------------------------------------------------------


def _textured_frame():
    """A 16x16 BGR gradient - real pixel variance, standing in for a genuine scene."""
    ramp = np.linspace(0, 255, 16, dtype=np.uint8)
    gray = np.tile(ramp, (16, 1))
    return np.repeat(gray[:, :, None], 3, axis=2)


def test_burst_is_low_texture_true_when_every_frame_is_flat():
    """A burst of uniform frames reads as low-texture - the partial-covering shape."""
    frames = [Frame(image=_gray_frame(90), index=i, timestamp_s=float(i)) for i in range(3)]

    result = home_test._burst_is_low_texture(
        frames, config.HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD
    )

    assert result is True


def test_burst_is_low_texture_false_if_any_frame_has_real_texture():
    """One textured frame among flat ones must not count as low-texture."""
    frames = [
        Frame(image=_gray_frame(90), index=0, timestamp_s=0.0),
        Frame(image=_textured_frame(), index=1, timestamp_s=1.0),
        Frame(image=_gray_frame(90), index=2, timestamp_s=2.0),
    ]

    result = home_test._burst_is_low_texture(
        frames, config.HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD
    )

    assert result is False, "a single textured frame must save the whole burst from the flag"


def test_burst_is_low_texture_none_when_nothing_measurable():
    """A burst with no readable frame returns None, not a guess either way."""
    frames = [Frame(image=None, index=0, timestamp_s=0.0)]

    result = home_test._burst_is_low_texture(
        frames, config.HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD
    )

    assert result is None


def test_update_camera_covered_state_trips_on_low_texture_alone(home_test_paths):
    """A sustained flat-frame run, with no frame-filling box at all, still trips the alert."""
    session = _make_session()

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS):
        session._update_camera_covered_state(False, True, 1_000_000.0)

    lines = _covered_log_lines()
    assert len(lines) == 1
    assert lines[0] == {"wall_s": 1_000_000.0, "state": "covered", "reason": "low_texture"}


def test_run_one_poll_flags_camera_covered_from_a_partial_covering(home_test_paths):
    """Reproduces the 11 Sept partial-covering case: no frame-filling box, only flat frames.

    Small, varying, sub-threshold boxes (the shape a partial covering
    actually produces) never trip HOME_TEST_MAX_BOX_AREA_FRACTION's
    frame-filling check - the low-texture signal is what catches this one.
    """
    session = _make_session(detect_vision=_constant_detect_vision([ELEPHANT_LOW]))
    flat_frames = [Frame(image=_gray_frame(90), index=0, timestamp_s=0.0)]

    for _ in range(config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS):
        session._run_one_poll(flat_frames)

    assert session._encounter is None
    lines = _covered_log_lines()
    assert len(lines) == 1
    assert lines[0]["state"] == "covered"
    assert lines[0]["reason"] == "low_texture"


# ---------------------------------------------------------------------------
# frame-filling degenerate-box rejection (fire gate only, never logging)
# ---------------------------------------------------------------------------


def test_gate_filter_drops_a_box_that_fills_the_frame():
    """A box at HOME_TEST_MAX_BOX_AREA_FRACTION or more of the frame is removed before the gate."""
    frames = _np_frames(1)
    full = Detection(label="Elephant", confidence=1.0, x=0, y=0, width=1920, height=1080)

    gated = home_test._gate_results_without_degenerate_boxes(frames, [[full]])

    assert gated == [[]], "a frame-filling detection must not reach the fire gate"


def test_gate_filter_keeps_a_normally_sized_box():
    """A detection well under the area cap passes the filter untouched."""
    frames = _np_frames(1)
    small = Detection(label="Boar", confidence=0.9, x=10, y=10, width=200, height=150)

    gated = home_test._gate_results_without_degenerate_boxes(frames, [[small]])

    assert gated == [[small]], "a plausibly-sized detection must pass the filter unchanged"


def test_gate_filter_degrades_safe_when_frame_has_no_shape():
    """If a frame's pixel dimensions cannot be read, every detection on it is kept."""
    frames = _frames(1)  # image is a str - no .shape
    full = Detection(label="Elephant", confidence=1.0, x=0, y=0, width=1920, height=1080)

    gated = home_test._gate_results_without_degenerate_boxes(frames, [[full]])

    assert gated == [[full]], "a shape-read failure must never manufacture a dropped detection"


def test_run_one_poll_logs_a_frame_filling_box_but_never_starts_an_encounter(home_test_paths):
    """The degenerate-box artefact is logged in full yet cannot clear the fire gate."""
    full = Detection(label="Elephant", confidence=1.0, x=0, y=0, width=1920, height=1080)
    session = _make_session(detect_vision=_constant_detect_vision([full]))

    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS + 2):
        session._run_one_poll(_np_frames(1))

    assert session._encounter is None, "a frame-filling box must never open an encounter"
    lines = config.HOME_TEST_DETECTIONS_PATH.read_text(encoding="utf-8").splitlines()
    logged = config.HOME_TEST_FIRE_CONSECUTIVE_POLLS + 2
    assert len(lines) == logged, "every poll still logs the box"


# ---------------------------------------------------------------------------
# encounter state machine
# ---------------------------------------------------------------------------


def test_advance_encounter_starts_only_after_enough_qualifying_polls(home_test_paths):
    """HOME_TEST_FIRE_CONSECUTIVE_POLLS qualifying polls within the window start one."""
    spawned = []
    session = _make_session(spawn_deterrence=lambda fn: spawned.append(fn))
    now = 1_000_000.0

    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS - 1):
        session._advance_encounter(now, True, None)
    assert session._encounter is None, "one poll short of the count must not start an encounter"

    session._advance_encounter(now, True, None)
    assert session._encounter is not None, "the Nth qualifying poll must start one"
    assert len(spawned) == 1, "exactly one deterrence run must be spawned per encounter start"


def test_advance_encounter_tolerates_a_gap_within_the_window(home_test_paths):
    """Qualifying polls need not be back-to-back, only within the window - the 11 Sept fix.

    Mirrors the real 10-11 Sept Boar cluster: a qualifying poll, then
    nothing but non-qualifying polls filling the rest of the window, then
    the remaining qualifying polls needed - still opens an encounter. The
    old strict streak design zeroed on the very first gap and could never
    open on this pattern, which is exactly why last night's real animal
    (soil-digging ground-truth confirmed the next morning) never triggered
    one despite repeatedly clearing both the confirmation gate and the
    fire-confidence floor.
    """
    session = _make_session()
    now = 1_000_000.0
    gap = config.HOME_TEST_FIRE_WINDOW_POLLS - config.HOME_TEST_FIRE_CONSECUTIVE_POLLS

    session._advance_encounter(now, True, None)
    for _ in range(gap):
        session._advance_encounter(now, False, None)
    assert session._encounter is None, "only one qualifying poll so far - must not start yet"

    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS - 1):
        session._advance_encounter(now, True, None)
    assert session._encounter is not None, (
        "the window's qualifying-poll count must open once met, gap and all"
    )


def test_advance_encounter_a_qualifying_poll_ages_out_of_the_window(home_test_paths):
    """A stray hit no longer counts once it exits the window - the tolerance still has a bound.

    The window is a fix for spacing between genuine hits, not a license
    for one lucky poll to sit there indefinitely waiting for company.
    """
    session = _make_session()
    now = 1_000_000.0

    session._advance_encounter(now, True, None)
    for _ in range(config.HOME_TEST_FIRE_WINDOW_POLLS):
        session._advance_encounter(now, False, None)
    assert session._encounter is None, "the lone early hit must have aged out of the window by now"

    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS - 1):
        session._advance_encounter(now, True, None)
    assert session._encounter is None, (
        "one aged-out hit plus a too-short new run must still not be enough"
    )


def test_start_encounter_protects_buffered_preroll_frames(home_test_paths):
    """Only ring frames within HOME_TEST_PREROLL_S get copied into the encounter."""
    session = _make_session()
    now = 1_000_000.0
    within_preroll = config.HOME_TEST_RING_DIR / f"{now - 5:018.6f}_1.jpg"
    before_preroll = (
        config.HOME_TEST_RING_DIR / f"{now - config.HOME_TEST_PREROLL_S - 5:018.6f}_2.jpg"
    )
    within_preroll.write_bytes(b"frame-data")
    before_preroll.write_bytes(b"frame-data")

    session._start_encounter(now)

    dir_path = session._encounter.dir_path
    assert (dir_path / within_preroll.name).exists(), "pre-roll frame must be copied in"
    assert not (dir_path / before_preroll.name).exists(), "frame older than the pre-roll is not"


def test_advance_encounter_closes_after_departure_timeout_and_protects_postroll(
    home_test_paths,
):
    """Departure timeout + post-roll closes the encounter and sweeps in the tail."""
    session = _make_session()
    start = 1_000_000.0
    session._advance_encounter(start, True, None)
    session._advance_encounter(start, True, None)
    session._advance_encounter(start, True, None)
    assert session._encounter is not None
    encounter_dir = session._encounter.dir_path

    # A post-roll frame written by the (untested-here) capture thread while
    # the encounter was active - _close_encounter must sweep this in.
    postroll_wall_s = start + 1.0
    postroll_path = config.HOME_TEST_RING_DIR / f"{postroll_wall_s:018.6f}_9.jpg"
    postroll_path.write_bytes(b"frame-data")

    after_timeout = (
        start + config.HOME_TEST_DEPARTURE_TIMEOUT_S + config.HOME_TEST_POSTROLL_S + 1.0
    )
    session._advance_encounter(after_timeout, False, None)

    assert session._encounter is None, "the encounter must close once departure+postroll elapses"
    assert (encounter_dir / postroll_path.name).exists(), "the post-roll frame must be protected"


def test_advance_encounter_a_still_qualifying_encounter_does_not_close_early(home_test_paths):
    """A qualifying poll keeps last_qualifying_wall_s fresh, so the timeout never fires."""
    session = _make_session()
    start = 1_000_000.0
    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS):
        session._advance_encounter(start, True, None)
    assert session._encounter is not None

    # Well past HOME_TEST_DEPARTURE_TIMEOUT_S in wall-clock terms, but every
    # poll in between kept qualifying, so last_qualifying_wall_s tracks
    # `now` and the encounter must still be open.
    now = start + config.HOME_TEST_DEPARTURE_TIMEOUT_S + 5.0
    session._advance_encounter(now, True, None)

    assert session._encounter is not None


def test_advance_encounter_hits_max_encounter_cap_even_while_still_qualifying(home_test_paths):
    """A stuck false positive that never stops qualifying must not run all night."""
    session = _make_session()
    start = 1_000_000.0
    for _ in range(config.HOME_TEST_FIRE_CONSECUTIVE_POLLS):
        session._advance_encounter(start, True, None)
    assert session._encounter is not None

    now = start + config.HOME_TEST_MAX_ENCOUNTER_S + 1.0
    session._advance_encounter(now, True, None)

    assert session._encounter is None, "HOME_TEST_MAX_ENCOUNTER_S must close it regardless"


# ---------------------------------------------------------------------------
# manual fire trigger
# ---------------------------------------------------------------------------


def test_manual_fire_trigger_absent_does_nothing(home_test_paths):
    """No trigger file - no encounter, no deterrence call."""
    session = _make_session()
    session._check_manual_fire_trigger(1_000_000.0)
    assert session._encounter is None


def test_manual_fire_trigger_starts_a_new_encounter_and_consumes_the_file(home_test_paths):
    """Touching the trigger file starts an encounter and deletes the file immediately."""
    fired = []
    session = _make_session(spawn_deterrence=lambda fn: fired.append(fn))
    config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH.write_text("")

    session._check_manual_fire_trigger(1_000_000.0)

    assert session._encounter is not None, "a manual trigger must open an encounter"
    assert len(fired) == 1, "deterrence must be spawned exactly once"
    assert not config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH.exists(), "trigger file must be consumed"


def test_manual_fire_trigger_is_a_no_op_on_the_next_poll_once_consumed(home_test_paths):
    """A stale/already-consumed trigger must never cause a second, unintended fire."""
    fired = []
    session = _make_session(spawn_deterrence=lambda fn: fired.append(fn))
    config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH.write_text("")

    session._check_manual_fire_trigger(1_000_000.0)
    session._check_manual_fire_trigger(1_000_001.0)

    assert len(fired) == 1, "the second poll must not fire again"


def test_manual_fire_trigger_forces_a_refire_on_an_already_open_encounter(home_test_paths):
    """On an open encounter, a manual trigger re-fires immediately, ignoring the refire interval."""
    fired = []
    session = _make_session(spawn_deterrence=lambda fn: fired.append(fn))
    session._start_encounter(1_000_000.0)
    assert len(fired) == 1  # the start-encounter fire
    encounter = session._encounter
    fire_count_before = encounter.fire_count

    # Well inside HOME_TEST_REFIRE_INTERVAL_S - a real qualifying poll would
    # not re-fire yet, but the manual override must ignore that throttle.
    config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH.write_text("")
    session._check_manual_fire_trigger(1_000_000.5)

    assert session._encounter is encounter, "the same encounter stays open, not a new one"
    assert encounter.fire_count == fire_count_before + 1
    assert len(fired) == 2, "the manual trigger must spawn a second deterrence call"


def test_manual_fire_trigger_ignores_the_max_fires_per_encounter_cap(home_test_paths, monkeypatch):
    """The manual override must fire even when the encounter already hit its automatic cap."""
    monkeypatch.setattr(config, "HOME_TEST_MAX_FIRES_PER_ENCOUNTER", 1)
    fired = []
    session = _make_session(spawn_deterrence=lambda fn: fired.append(fn))
    session._start_encounter(1_000_000.0)
    encounter = session._encounter
    encounter.fire_count = config.HOME_TEST_MAX_FIRES_PER_ENCOUNTER  # already at the cap

    config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH.write_text("")
    session._check_manual_fire_trigger(1_000_000.5)

    assert encounter.fire_count == config.HOME_TEST_MAX_FIRES_PER_ENCOUNTER + 1
    assert len(fired) == 2, "manual override fires despite the cap (start-fire + manual fire)"


# ---------------------------------------------------------------------------
# byte cap on protected video
# ---------------------------------------------------------------------------


def test_protect_frame_stops_protecting_past_home_test_max_total_bytes(
    home_test_paths, monkeypatch
):
    """Past HOME_TEST_MAX_TOTAL_BYTES, protection stops but the encounter keeps running."""
    monkeypatch.setattr(config, "HOME_TEST_MAX_TOTAL_BYTES", 4)
    session = _make_session()
    now = 1_000_000.0
    frame_a = config.HOME_TEST_RING_DIR / f"{now - 1:018.6f}_1.jpg"
    frame_b = config.HOME_TEST_RING_DIR / f"{now:018.6f}_2.jpg"
    frame_a.write_bytes(b"12345")  # already over the 4-byte cap on its own
    frame_b.write_bytes(b"more-data")

    session._start_encounter(now)

    dir_path = session._encounter.dir_path
    assert (dir_path / frame_a.name).exists(), "first frame protects even past the cap"
    assert not (dir_path / frame_b.name).exists(), "cap reached - later frames are skipped"
    assert session._encounter.protecting is False


# ---------------------------------------------------------------------------
# SharedFrameCamera
# ---------------------------------------------------------------------------


def test_shared_frame_camera_reads_from_the_session_buffer(home_test_paths):
    """SharedFrameCamera serves frames from the session, never opens a device."""
    session = _make_session()
    frame = Frame(image="only-frame", index=0, timestamp_s=0.0)
    with session._frames_lock:
        session._frames.append(frame)
    camera = home_test.SharedFrameCamera(session)

    result = camera.capture_burst(count=1, interval_s=0.0)

    assert result == [frame]
    camera.open()  # no-op, must not raise
    camera.close()  # no-op, must not raise


def test_shared_frame_camera_lock_night_exposure_really_locks_now(home_test_paths):
    """SharedFrameCamera.lock_night_exposure() must not just echo stale controller state.

    Before this fix it returned the cached session.exposure_locked, which
    ExposureAutoLock's own recheck interval can leave stale for up to
    HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S. The vision watch's illumination
    block needs the lock applied right now, for this event - before its
    first lit poll, not a recheck interval later.
    """
    fake_camera = _FakeCamera(lock_result=True)
    session = _make_session(camera=fake_camera)
    assert session.exposure_locked is False  # nothing has locked yet
    shared_camera = home_test.SharedFrameCamera(session)

    applied = shared_camera.lock_night_exposure()

    assert applied is True
    assert fake_camera.lock_calls == 1
    assert session.exposure_locked is True


def test_shared_frame_camera_lock_night_exposure_reports_a_failed_lock(home_test_paths):
    """A rejected on-demand lock is reported honestly, not masked as success."""
    fake_camera = _FakeCamera(lock_result=False)
    session = _make_session(camera=fake_camera)
    shared_camera = home_test.SharedFrameCamera(session)

    applied = shared_camera.lock_night_exposure()

    assert applied is False
    assert session.exposure_locked is False


# ---------------------------------------------------------------------------
# periodic exposure lock - start() no longer locks unconditionally,
# _maybe_update_exposure() decides from real frames instead
# ---------------------------------------------------------------------------


def test_session_construction_does_not_lock_exposure_unconditionally(home_test_paths):
    """Constructing (and, by extension, start()-ing) a session must not lock by itself.

    This is the bug HOME_TEST_MODE actually had: a fixed dark-scene
    exposure locked the moment the camera opened, regardless of the real
    scene. Nothing in __init__ or start() calls lock_night_exposure() -
    only _maybe_update_exposure(), driven by real frames, decides that.
    """
    fake_camera = _FakeCamera()
    session = _make_session(camera=fake_camera)

    assert fake_camera.lock_calls == 0
    assert session.exposure_locked is False


def test_maybe_update_exposure_locks_on_confirmed_night_and_logs_median_saturation(
    home_test_paths,
):
    """A night-reading burst locks exposure and logs the median saturation that caused it.

    Uses _real_is_night(), the same NightDecideFn shape main.py binds -
    proving frames (not raw images) flow through home_test.py's call site
    and perception.night.ExposureAutoLock.maybe_update() end to end. Drives
    ExposureAutoLock's real HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE/RECHECK_INTERVAL_S
    defaults via a manual clock rather than monkeypatching config - those
    two are bound as constructor default args at night.py's import time, so
    a post-import monkeypatch would not reach them.
    """
    fake_camera = _FakeCamera(lock_result=True)
    clock = _ManualClock()
    session = _make_session(
        camera=fake_camera, footfall_kwargs={"is_night": _real_is_night}, monotonic=clock
    )
    night_frames = [Frame(image=_gray_frame(), index=i, timestamp_s=float(i)) for i in range(3)]

    for _ in range(config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE):
        session._maybe_update_exposure(night_frames)
        clock.advance(config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S)

    assert fake_camera.lock_calls == 1
    assert session.exposure_locked is True
    lines = config.HOME_TEST_EXPOSURE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    assert len(lines) == config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE
    record = json.loads(lines[-1])
    assert record["action"] == "lock"
    assert record["night"] is True
    assert record["applied"] is True
    assert record["median_saturation"] < config.NIGHT_SATURATION_THRESHOLD


def test_maybe_update_exposure_restores_on_confirmed_day_after_a_prior_lock(home_test_paths):
    """A day-reading burst restores auto exposure once the policy believes it is locked.

    Seeds the locked belief via note_external_lock() - the same path
    ensure_night_exposure_locked() uses - so this test does not depend on
    the separate night-locks-first test's own mechanics.
    """
    fake_camera = _FakeCamera(restore_result=True)
    clock = _ManualClock()
    session = _make_session(
        camera=fake_camera, footfall_kwargs={"is_night": _real_is_night}, monotonic=clock
    )
    session._exposure_lock.note_external_lock(True)
    clock.advance(config.HOME_TEST_EXPOSURE_MIN_DWELL_S)  # clear the post-lock cooldown
    day_frames = [Frame(image=_colour_frame(), index=i, timestamp_s=float(i)) for i in range(3)]

    for _ in range(config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE):
        session._maybe_update_exposure(day_frames)
        clock.advance(config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S)

    assert fake_camera.restore_calls == 1
    assert session.exposure_locked is False
    lines = config.HOME_TEST_EXPOSURE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["action"] == "restore"
    assert record["night"] is False


def test_maybe_update_exposure_records_a_failed_lock_and_capture_continues(home_test_paths):
    """A rejected lock write is logged honestly and never crashes the inference loop.

    The policy must not believe it locked when the camera's own write
    didn't verify, and a later poll must still run normally afterwards -
    perception failure never blocks capture.
    """
    fake_camera = _FakeCamera(lock_result=False)
    clock = _ManualClock()
    session = _make_session(
        camera=fake_camera, footfall_kwargs={"is_night": _real_is_night}, monotonic=clock
    )
    night_frames = [Frame(image=_gray_frame(), index=i, timestamp_s=float(i)) for i in range(3)]

    for _ in range(config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE):
        session._maybe_update_exposure(night_frames)  # must not raise
        clock.advance(config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S)

    assert fake_camera.lock_calls == 1
    assert session.exposure_locked is False, "a failed lock must not be believed"
    lines = config.HOME_TEST_EXPOSURE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["action"] == "lock"
    assert record["applied"] is False

    session._run_one_poll(night_frames)  # capture/inference keeps running afterwards


def test_maybe_update_exposure_releases_the_lock_on_a_bright_mono_dawn_burst(home_test_paths):
    """A zero-saturation but daylit-bright burst restores auto exposure - the dawn case.

    _gray_frame(200) reads as night by saturation (equal channels) yet its
    mean luma is well above NIGHT_BRIGHTNESS_DAY_THRESHOLD, exactly the
    IR-camera-at-sunrise shape that held the lock through dawn in the field.
    """
    fake_camera = _FakeCamera(restore_result=True)
    clock = _ManualClock()
    session = _make_session(
        camera=fake_camera, footfall_kwargs={"is_night": _real_is_night}, monotonic=clock
    )
    session._exposure_lock.note_external_lock(True)
    clock.advance(config.HOME_TEST_EXPOSURE_MIN_DWELL_S)  # clear the post-lock cooldown
    bright_frames = [
        Frame(image=_gray_frame(200), index=i, timestamp_s=float(i)) for i in range(3)
    ]

    for _ in range(config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE):
        session._maybe_update_exposure(bright_frames)
        clock.advance(config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S)

    assert fake_camera.restore_calls == 1
    assert fake_camera.lock_calls == 0
    assert session.exposure_locked is False
    lines = config.HOME_TEST_EXPOSURE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[-1])
    assert record["action"] == "restore"
    assert record["night"] is False
    assert record["brightness_override"] is True
    assert record["median_brightness"] >= config.NIGHT_BRIGHTNESS_DAY_THRESHOLD


def test_maybe_update_exposure_kill_switch_forces_auto_regardless_of_frame_content(
    home_test_paths, monkeypatch
):
    """NIGHT_EXPOSURE_LOCK_ENABLED=False forces auto even on an unambiguous night burst."""
    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", False)
    fake_camera = _FakeCamera(restore_result=True)
    session = _make_session(camera=fake_camera, footfall_kwargs={"is_night": _real_is_night})
    night_frames = [Frame(image=_gray_frame(), index=i, timestamp_s=float(i)) for i in range(3)]

    session._maybe_update_exposure(night_frames)

    assert fake_camera.restore_calls == 1
    assert fake_camera.lock_calls == 0
    assert session.exposure_locked is False
    lines = config.HOME_TEST_EXPOSURE_LOG_PATH.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    assert record["action"] == "restore"
    assert record["night"] is None
