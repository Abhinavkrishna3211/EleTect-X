"""HOME_TEST_MODE session: always-on capture, decoupled from inference.

Second operating mode, behind services.config.HOME_TEST_MODE, for a
supervised one-night backyard wild-boar test with mains power and no duty-
cycle constraint. Field mode's design (seismic-gated wake, event-only
camera, ADR 0020) is untouched - this module is not a replacement for it,
it is what main.py runs instead of the plain module-scope Camera when the
flag is set.

Four threads, one camera, no second reader of the USB device:

- Capture (this module's run loop, owns the only Camera): grabs frames as
  fast as the device sustains, writes each one to the rolling ring as a
  JPEG, and pushes it onto a bounded deque. Never waits on inference -
  capture rate and inference rate are independent by construction. An
  inference thread that only saved the frames it happened to look at would
  produce a stuttery slideshow regardless of container or codec; decoupling
  capture from inference is what avoids that, not a format choice.
- Inference: polls the deque, not the camera, at
  HOME_TEST_INFERENCE_INTERVAL_S. Every detection is logged unconditionally
  to HOME_TEST_DETECTIONS_PATH - false positives are useful labels for a
  night whose whole point is a labelled dataset - and reuses
  services.reflex_loop._vision_check() verbatim (wrapped as
  `lambda images: results`, since detection has already run) to apply the
  identical burst-majority gate the field path uses, so a Boar detection is
  judged by exactly the same rule here as it would be in the field.
- Deterrence: one persistent worker thread, started once in start() and
  processing every encounter's deterrence call serially off a queue - not a
  fresh thread per encounter (that was tried first and reverted: see
  _start_deterrence_worker's docstring for why). Each call runs the
  unmodified reflex_loop.handle_footfall_event() with seismic_available=False
  (the one new kwarg reflex_loop.py gained for this) and a SharedFrameCamera
  reading from this module's own frame buffer instead of opening a second
  capture handle. Everything downstream of that call - fuse, decide, the
  bandit, the rule gate, drive_horn/drive_led/pulse_ir - is exactly the
  field's deterrence path, unforked.

Every loop above stamps a per-thread heartbeat on each iteration
(HomeTestSession._beat); is_healthy() fails - and main.py's own watchdog
loop then exits the process for the container's restart policy to recover -
if a thread has either died or gone quiet past HOME_TEST_STALL_TIMEOUT_S,
so a hung-but-technically-alive thread is treated the same as a crash for
an unattended overnight run. A separate, best-effort performance log
(HOME_TEST_TELEMETRY_PATH, services/board_health.py) records model latency
and on-device resource headroom every HOME_TEST_TELEMETRY_INTERVAL_S -
evidence for later, not an input to any decision here.

Status: written 6 Sept 2026 for that night's test, hardened 9 Sept 2026 for an
unattended overnight run (stall watchdog, performance telemetry).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import random
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2

from cognition import config as cognition_config
from cognition.bandit import Tier
from perception.camera import Camera, Frame
from perception.detector import Detection
from perception.night import ExposureAutoLock
from services import board_health, config
from services.reflex_loop import (
    VisionCheck,
    _one_event_at_a_time,
    _vision_check,
    handle_footfall_event,
)

logger = logging.getLogger(__name__)


def _gate_results_without_degenerate_boxes(
    frames: list[Frame], results: list[list[Detection]]
) -> list[list[Detection]]:
    """Copy of `results` with frame-filling detector artefacts removed.

    A box covering at least config.HOME_TEST_MAX_BOX_AREA_FRACTION of its
    frame is dropped before the fire/protect gate sees it - see that
    constant's comment for the failure mode it targets. Detection logging
    upstream runs on the raw results and is never affected by this.

    Degrades safe: if a frame's pixel dimensions cannot be read, every
    detection on that frame is kept, so a shape-read failure can never
    manufacture a missed animal.
    """
    max_frac = config.HOME_TEST_MAX_BOX_AREA_FRACTION
    gated: list[list[Detection]] = []
    dropped = 0
    for frame, detections in zip(frames, results, strict=True):
        try:
            height, width = frame.image.shape[:2]
            frame_area = float(height) * float(width)
        except (AttributeError, ValueError, TypeError):
            gated.append(list(detections))
            continue
        if frame_area <= 0.0:
            gated.append(list(detections))
            continue
        kept = [
            det
            for det in detections
            if (det.width * det.height) / frame_area < max_frac
        ]
        dropped += len(detections) - len(kept)
        gated.append(kept)
    if dropped:
        logger.info(
            "home_test: dropped %d frame-filling detection(s) from the fire gate "
            "(>= %.0f%% of frame area)",
            dropped,
            max_frac * 100.0,
        )
    return gated


def _burst_is_low_texture(frames: list[Frame], std_threshold: float) -> bool | None:
    """Whether every frame in this poll's burst reads as near-uniform (flat).

    See config.HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD for why this exists
    alongside _gate_results_without_degenerate_boxes: a partial lens
    covering does not produce one frame-filling box, it produces varying
    sub-threshold noise, so this reads the frame's own pixel statistics
    instead of trusting detection-box geometry. Requires every frame in
    the burst below std_threshold, not just one, so a single frame with
    real texture (a genuine animal, or a covering that only reached part
    of the burst) cannot contribute to the covered streak.

    Degrades safe, same as frames_are_night(): an unmeasurable frame is
    dropped, not treated as flat, and None means nothing in the burst
    could be measured at all.
    """
    stds: list[float] = []
    for frame in frames:
        image = frame.image
        if image is None:
            continue
        try:
            shape = getattr(image, "shape", None)
            if not shape or len(shape) not in (2, 3):
                continue
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(shape) == 3 else image
            stds.append(float(gray.std()))
        except Exception:  # noqa: BLE001 - a bad frame must never propagate
            continue
    if not stds:
        return None
    return all(s < std_threshold for s in stds)


class SharedFrameCamera:
    """CameraProtocol adapter serving frames from the capture thread's buffer.

    open()/close() are no-ops: the real Camera is owned and kept open for
    the whole session by the capture thread in this module, never by
    handle_footfall_event. This is what lets the deterrence thread call the
    unmodified reflex_loop.handle_footfall_event() without a second reader
    ever touching /dev/video0.
    """

    def __init__(self, session: HomeTestSession) -> None:
        """Bind to the session whose capture thread owns the real camera."""
        self._session = session

    def open(self) -> None:
        """No-op - the session's capture thread already holds the device open."""

    def capture_burst(self, count: int, interval_s: float) -> list[Frame]:
        """Return up to `count` of the most recently captured frames.

        `interval_s` is accepted for CameraProtocol compatibility and
        ignored: these frames were already captured at whatever rate the
        capture thread sustains, not paced to order here. A caller asking
        for frames spaced `interval_s` apart is asking a live camera to
        slow down for it; this adapter can only hand back what already
        exists.
        """
        return self._session.recent_frames(count)

    def lock_night_exposure(self) -> bool:
        """Lock exposure now, on demand - never just re-report stale controller state.

        The capture thread's ExposureAutoLock only re-evaluates every
        HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S, so a caller on this
        protocol (reflex_loop.py's vision-watch illumination block, right
        before the first lit poll) cannot wait out that interval - it needs
        the lock now, for this event. Delegates to the session rather than
        reading self._session.exposure_locked directly, since that field
        can be stale by up to the recheck interval.
        """
        return self._session.ensure_night_exposure_locked()

    def close(self) -> None:
        """No-op - see open()."""


@dataclass
class _Encounter:
    """Mutable state for one in-progress encounter.

    Attributes:
        started_wall_s: When the qualifying streak first completed.
        last_qualifying_wall_s: Most recent qualifying detection - compared
            against HOME_TEST_DEPARTURE_TIMEOUT_S to decide when the
            encounter is over.
        dir_path: Where this encounter's protected frames are being written.
        protecting: False once HOME_TEST_MAX_TOTAL_BYTES has been reached
            for the session - the encounter keeps running (still logged,
            still eligible to fire) but stops copying frames into dir_path.
        last_fire_wall_s: When deterrence was last fired for this
            encounter - advances only on an actual (re-)fire attempt (7
            Sept field-test addition), compared against
            HOME_TEST_REFIRE_INTERVAL_S to decide when the next one is due.
        fire_count: How many times deterrence has been fired for this
            encounter (start + every re-fire). Capped at
            HOME_TEST_MAX_FIRES_PER_ENCOUNTER - see that constant (10 Sept
            field-trial run #1 hardening).
    """

    started_wall_s: float
    last_qualifying_wall_s: float
    dir_path: Path
    protecting: bool = True
    last_fire_wall_s: float = 0.0
    fire_count: int = 0


class HomeTestSession:
    """Owns the camera and the three HOME_TEST_MODE threads for one run.

    Args:
        detect_vision: Same VisionDetectFn main.py binds to the real
            HttpVisionDetector - called directly from the inference thread,
            not through reflex_loop's own vision-check path (that path is
            only reached via handle_footfall_event, once per encounter).
        footfall_kwargs: Every keyword handle_footfall_event needs *except*
            camera and seismic_available, which this class supplies itself
            (drive_horn, drive_led, pulse_ir, is_night, save_frames,
            experience, and optionally safe_mode/event_video overrides for
            tests). Kept as one dict rather than individual parameters so
            main.py can build it identically to _on_footfall_event's own
            call and pass it straight through.
        camera_factory: Returns a fresh CameraProtocol-shaped Camera.
            Overridable for tests - the default constructs the real
            perception.camera.Camera.
        clock: time.time, injectable for tests.
        monotonic: time.monotonic, injectable for tests.
        sleep: time.sleep, injectable for tests so the capture/inference
            loops can be driven without a real camera or real waits.
        spawn_deterrence: How to hand off Thread C's target once an
            encounter starts. Defaults to enqueuing onto the session's one
            persistent deterrence worker thread (started in start()). Tests
            override this with a synchronous call (`lambda fn: fn()`) so an
            encounter's deterrence call is deterministic and finishes before
            the test's next assertion, instead of racing a background
            thread.
    """

    def __init__(
        self,
        detect_vision: Callable[[list[Any]], list[list[Detection]]],
        footfall_kwargs: dict[str, Any],
        *,
        camera_factory: Callable[[], Any] = Camera,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        spawn_deterrence: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """Construct the session; does no I/O until start() is called."""
        self._camera = camera_factory()
        self._detect_vision = detect_vision
        self._footfall_kwargs = footfall_kwargs
        self._clock = clock
        self._monotonic = monotonic
        self._sleep = sleep
        self._spawn_deterrence = spawn_deterrence or self._spawn_deterrence_thread

        self._frames: deque[Frame] = deque(maxlen=config.HOME_TEST_FRAME_BUFFER_FRAMES)
        self._frames_lock = threading.Lock()
        self._stop = threading.Event()
        self._capture_thread: threading.Thread | None = None
        self._inference_thread: threading.Thread | None = None
        self._deterrence_thread: threading.Thread | None = None
        self._deterrence_queue: queue.Queue[Callable[[], None]] = queue.Queue()

        self.exposure_locked = False
        self._exposure_lock = ExposureAutoLock(
            is_night=footfall_kwargs["is_night"],
            lock=self._camera.lock_night_exposure,
            restore=self._camera.restore_auto_exposure,
            monotonic=monotonic,
            clock=clock,
        )
        self._encounter: _Encounter | None = None
        self._qualifying_window: deque[bool] = deque(maxlen=config.HOME_TEST_FIRE_WINDOW_POLLS)
        self._covered_streak = 0
        self._session_started_wall_s: float | None = None
        self._protected_bytes = 0
        self._ring_frame_index = 0
        self._review_bytes = 0
        self._last_review_save_wall_s: dict[str, float] = {}

        # Stall watchdog: each loop stamps its own key on every iteration,
        # *before* any blocking call in that iteration - see is_healthy()
        # and services.config.HOME_TEST_STALL_TIMEOUT_S for why.
        self._heartbeats_lock = threading.Lock()
        now_monotonic = monotonic()
        self._heartbeats: dict[str, float] = {
            "capture": now_monotonic,
            "inference": now_monotonic,
            "deterrence": now_monotonic,
        }
        self._last_inference_latency_ms: float | None = None
        self._last_telemetry_wall_s = 0.0

        # Camera-blindness guard + auto-recovery (10 Sept field-trial run #1
        # hardening - see services.config's HOME_TEST_CAMERA_* block). All
        # stamped/read on the capture and inference threads only.
        self._had_any_frame = False
        self._last_good_frame_monotonic = now_monotonic
        self._camera_down_since_monotonic: float | None = None
        self._last_reopen_monotonic = 0.0
        self._reboot_requested = False

        config.HOME_TEST_DIR.mkdir(parents=True, exist_ok=True)
        config.HOME_TEST_RING_DIR.mkdir(parents=True, exist_ok=True)
        config.HOME_TEST_ENCOUNTERS_DIR.mkdir(parents=True, exist_ok=True)
        config.HOME_TEST_REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        """Open the camera and start the capture and inference threads.

        Blocking calls only happen inside the two threads this spawns -
        this method itself returns as soon as they are started.
        """
        self._camera.open()
        # No lock here, on purpose: Camera.open() already leaves the device on
        # auto-exposure (_assert_auto_exposure), and self._exposure_lock starts
        # in the matching state (locked=False). Locking unconditionally at
        # open() is the exact bug this class used to have - a session that
        # starts under room lighting stayed pinned at NIGHT_LOCKED_EXPOSURE for
        # its whole run. _inference_loop's periodic maybe_update() call is what
        # decides, from live frames, whether and when to lock.
        self._session_started_wall_s = self._clock()

        self._capture_thread = threading.Thread(
            target=self._run_guarded,
            args=(self._capture_loop, "capture"),
            name="home_test_capture",
            daemon=True,
        )
        self._inference_thread = threading.Thread(
            target=self._run_guarded,
            args=(self._inference_loop, "inference"),
            name="home_test_inference",
            daemon=True,
        )
        self._deterrence_thread = threading.Thread(
            target=self._run_guarded,
            args=(self._deterrence_loop, "deterrence"),
            name="home_test_deterrence",
            daemon=True,
        )
        self._capture_thread.start()
        self._inference_thread.start()
        self._deterrence_thread.start()
        logger.info(
            "home_test: session started, ring=%s detections=%s encounters=%s",
            config.HOME_TEST_RING_DIR,
            config.HOME_TEST_DETECTIONS_PATH,
            config.HOME_TEST_ENCOUNTERS_DIR,
        )

    def stop(self) -> None:
        """Signal both threads to stop, join them, and close the camera.

        Does not close out an in-progress encounter's directory rename -
        an encounter still open at shutdown keeps whatever frames it has
        already protected; nothing is lost, the postroll simply never runs.
        """
        self._stop.set()
        for thread in (self._capture_thread, self._inference_thread, self._deterrence_thread):
            if thread is not None:
                thread.join(timeout=5.0)
        self._camera.close()
        logger.info("home_test: session stopped")

    def _run_guarded(self, fn: Callable[[], None], name: str) -> None:
        """Run a daemon thread's loop; on any exception, kill the process.

        capture_frame() and the rest of this module's own code are written
        to never raise, so an exception here means something genuinely
        unexpected. A daemon thread dying from an uncaught exception would
        otherwise leave the process running with one loop silently gone
        (the other thread and the main `while True: sleep(1)` in main.py
        keep going) - a zombie container Docker's restart policy can never
        see because the process itself never exits. Exiting hard instead
        turns that into the same loud, restart-triggering crash main.py's
        own module docstring already treats as correct for a startup
        failure, so an unattended overnight run recovers instead of going
        dark while still reporting healthy.
        """
        try:
            fn()
        except Exception:
            logger.exception(
                "home_test: %s thread crashed - exiting process for the "
                "container restart policy to recover",
                name,
            )
            os._exit(1)

    def is_healthy(self) -> bool:
        """Return whether every daemon thread is both alive and making progress.

        Only meaningful after start(). Exists for main.py to poll as a
        belt-and-suspenders check alongside _run_guarded's own hard exit -
        harmless if _run_guarded already covers every case, but cheap
        insurance against a future change to either loop that swallows an
        exception instead of letting it surface here.

        Alive-but-stuck is a distinct failure from crashed: a thread wedged
        on a hung call never dies, so restart-policy recovery from
        _run_guarded never triggers, and an unattended overnight run would
        just silently stop advancing. _beat() stamps a per-loop heartbeat on
        every iteration before that iteration's own blocking call; a
        heartbeat older than HOME_TEST_STALL_TIMEOUT_S means that iteration
        has been running (or the loop has stopped ticking) far longer than
        any real one should, and this method fails so main.py's watchdog
        loop turns it into the same hard exit a crash would cause.
        """
        threads_alive = (
            self._capture_thread is not None
            and self._capture_thread.is_alive()
            and self._inference_thread is not None
            and self._inference_thread.is_alive()
            and self._deterrence_thread is not None
            and self._deterrence_thread.is_alive()
        )
        if not threads_alive:
            return False

        now = self._monotonic()
        with self._heartbeats_lock:
            ages = {name: now - stamp for name, stamp in self._heartbeats.items()}
        timeout_s = config.HOME_TEST_STALL_TIMEOUT_S
        stalled = {name: age for name, age in ages.items() if age > timeout_s}
        if stalled:
            logger.error("home_test: stall detected, ages_s=%s", stalled)
            return False
        return True

    def _beat(self, name: str) -> None:
        """Stamp `name`'s heartbeat with the current monotonic time."""
        with self._heartbeats_lock:
            self._heartbeats[name] = self._monotonic()

    # -- shared state, read by SharedFrameCamera and tests --------------

    def recent_frames(self, count: int) -> list[Frame]:
        """Return up to the `count` most recently captured frames, oldest first."""
        with self._frames_lock:
            return list(self._frames)[-count:]

    def ensure_night_exposure_locked(self) -> bool:
        """Lock exposure right now, bypassing the periodic re-evaluation's own interval.

        Called from SharedFrameCamera.lock_night_exposure() - i.e. from the
        deterrence thread, right before an IR-lit evidence burst, which
        cannot wait out HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S for the
        capture thread's own re-evaluation to catch up. Updates
        self._exposure_lock's belief about device state to match (see
        ExposureAutoLock.note_external_lock), so the next periodic check
        does not act on stale state.
        """
        applied = self._camera.lock_night_exposure()
        self._exposure_lock.note_external_lock(applied)
        self.exposure_locked = self._exposure_lock.locked
        return applied

    # -- capture thread ---------------------------------------------------

    def _capture_loop(self) -> None:
        """Grab frames as fast as the camera sustains; ring-rotate; push to the deque.

        No pacing, no wait on inference - the ring reflects the camera's
        real throughput, whatever fps bench/camera_check/fps_probe.py
        measured it to be. A failed grab (capture_frame() returning None)
        is skipped, not retried in a tight spin, so a transient USB hiccup
        does not busy-loop this thread. A run of failed grabs escalates
        through _handle_failed_grab() - reopen the device, then, as a last
        resort, request a board reboot (10 Sept run #1 hardening).
        """
        while not self._stop.is_set():
            self._beat("capture")
            frame = self._camera.capture_frame()
            if frame is None:
                self._handle_failed_grab()
                continue
            self._note_good_grab()

            self._ring_frame_index += 1
            wall_s = self._clock()
            name = f"{wall_s:018.6f}_{self._ring_frame_index:08d}.jpg"
            path = config.HOME_TEST_RING_DIR / name
            ok = cv2.imwrite(
                str(path), frame.image, [cv2.IMWRITE_JPEG_QUALITY, config.HOME_TEST_JPEG_QUALITY]
            )
            if not ok:
                logger.warning("home_test: failed to write ring frame %s", path)
                continue

            with self._frames_lock:
                self._frames.append(frame)

            self._rotate_ring(wall_s)

    def _rotate_ring(self, now_wall_s: float) -> None:
        """Delete ring frames older than HOME_TEST_PREROLL_S.

        Frames belonging to the current encounter are never in this
        directory in the first place - _protect_frame() copies them into
        the encounter directory rather than moving them, so rotation here
        never has to know whether an encounter is active.
        """
        cutoff = now_wall_s - config.HOME_TEST_PREROLL_S
        for path in config.HOME_TEST_RING_DIR.glob("*.jpg"):
            try:
                frame_wall_s = float(path.name.split("_", 1)[0])
            except ValueError:
                continue
            if frame_wall_s < cutoff:
                path.unlink(missing_ok=True)

    # -- camera health: blindness guard + auto-recovery ------------------

    def _note_good_grab(self) -> None:
        """Record that the camera just delivered a frame; clear any down state."""
        now = self._monotonic()
        if self._camera_down_since_monotonic is not None:
            logger.warning(
                "home_test: camera recovered, delivering frames again after %.1fs down",
                now - self._camera_down_since_monotonic,
            )
        self._had_any_frame = True
        self._last_good_frame_monotonic = now
        self._camera_down_since_monotonic = None
        self._reboot_requested = False

    def _handle_failed_grab(self) -> None:
        """One failed capture_frame(): track downtime, escalate reopen -> reboot request.

        Called from the capture loop on every None grab. Escalation is
        time-based off the first failure, not a raw fail count, so it
        behaves the same whether the device returns None fast or blocks
        briefly first:

        - after HOME_TEST_CAMERA_REOPEN_AFTER_S with no good frame, attempt
          an in-place Camera.reopen(), rate-limited to one per
          HOME_TEST_CAMERA_REOPEN_MIN_INTERVAL_S;
        - after HOME_TEST_CAMERA_REBOOT_AFTER_S still down, drop a
          reboot-request sentinel for the host watchdog (once, until the
          camera recovers or the min-interval passes).

        A short sleep after handling keeps a hard-down device (immediate
        None every call) from spinning this thread while still ticking the
        heartbeat often enough for is_healthy().
        """
        now = self._monotonic()
        if self._camera_down_since_monotonic is None:
            self._camera_down_since_monotonic = now
            logger.warning("home_test: camera stopped delivering frames")

        down_for = now - self._camera_down_since_monotonic
        since_good = now - self._last_good_frame_monotonic

        if (
            since_good >= config.HOME_TEST_CAMERA_REOPEN_AFTER_S
            and now - self._last_reopen_monotonic >= config.HOME_TEST_CAMERA_REOPEN_MIN_INTERVAL_S
        ):
            self._last_reopen_monotonic = now
            logger.warning("home_test: camera down %.1fs - attempting in-place reopen", down_for)
            try:
                recovered = bool(self._camera.reopen())
            except Exception:  # noqa: BLE001 - recovery must never kill the capture thread
                logger.exception("home_test: camera reopen raised")
                recovered = False
            logger.warning(
                "home_test: camera reopen %s", "succeeded" if recovered else "failed"
            )

        if down_for >= config.HOME_TEST_CAMERA_REBOOT_AFTER_S and not self._reboot_requested:
            self._request_board_reboot(down_for)

        self._sleep(0.2)

    def _request_board_reboot(self, down_for_s: float) -> None:
        """Drop a sentinel asking the host watchdog cron to reboot the board.

        Last-resort camera recovery. The app runs in an unprivileged
        container and cannot reboot the host itself; eletect-x-watchdog.sh
        (host crontab, every 5 min) picks this file up and runs the reboot.
        Rate-limited via HOME_TEST_CAMERA_REBOOT_MARKER_PATH, persisted on a
        bind mount so a reboot it triggers cannot immediately trigger
        another. Never raises.
        """
        now_wall = self._clock()
        marker = config.HOME_TEST_CAMERA_REBOOT_MARKER_PATH
        try:
            if marker.exists():
                last = float(json.loads(marker.read_text()).get("wall_s", 0.0))
                if now_wall - last < config.HOME_TEST_CAMERA_REBOOT_MIN_INTERVAL_S:
                    logger.error(
                        "home_test: camera dead %.0fs but a reboot was requested %.0fs ago "
                        "(< %.0fs floor) - not requesting again",
                        down_for_s,
                        now_wall - last,
                        config.HOME_TEST_CAMERA_REBOOT_MIN_INTERVAL_S,
                    )
                    self._reboot_requested = True
                    return
        except (OSError, ValueError, TypeError):
            logger.warning("home_test: could not read reboot marker, proceeding", exc_info=True)

        payload = json.dumps({"wall_s": now_wall, "down_for_s": round(down_for_s, 1)})
        try:
            config.HOME_TEST_CAMERA_REBOOT_MARKER_PATH.write_text(payload)
            config.HOME_TEST_CAMERA_REBOOT_REQUEST_PATH.write_text(payload)
        except OSError:
            logger.exception("home_test: failed to write reboot-request sentinel")
            return
        self._reboot_requested = True
        logger.critical(
            "home_test: camera dead %.0fs despite reopen attempts - reboot-request sentinel "
            "written for the host watchdog to act on",
            down_for_s,
        )

    def _camera_is_blind(self) -> bool:
        """Whether the frame buffer is too stale to fire on.

        True when there are no frames at all, or the most recent good grab
        is older than HOME_TEST_CAMERA_STALE_S. Compared against the
        capture loop's own last-good-grab stamp (same monotonic clock the
        session was constructed with), not against Frame.timestamp_s, so
        the check stays consistent under an injected clock in tests.

        When this is true the deque is serving pre-failure frames and any
        detection on them is an illusion: the encounter machine must not
        qualify, fire, or re-fire, and an open encounter is closed.

        Returns False until the camera has delivered at least one frame -
        "not started yet" is not "blind", and the inference loop does not
        run a poll on an empty buffer anyway.
        """
        if not self._had_any_frame:
            return False
        with self._frames_lock:
            have_frames = bool(self._frames)
        if not have_frames:
            return True
        age = self._monotonic() - self._last_good_frame_monotonic
        return age >= config.HOME_TEST_CAMERA_STALE_S

    # -- inference thread -------------------------------------------------

    def _inference_loop(self) -> None:
        """Poll the frame buffer, log every detection, drive the encounter machine."""
        while not self._stop.is_set():
            self._beat("inference")
            poll_started = self._monotonic()
            self._check_manual_fire_trigger(self._clock())
            frames = self.recent_frames(config.HOME_TEST_INFERENCE_FRAME_COUNT)
            if frames:
                self._maybe_update_exposure(frames)
                self._run_one_poll(frames)
            self._maybe_log_telemetry()

            elapsed = self._monotonic() - poll_started
            remaining = config.HOME_TEST_INFERENCE_INTERVAL_S - elapsed
            if remaining > 0:
                self._sleep(remaining)

    def _maybe_update_exposure(self, frames: list[Frame]) -> None:
        """Re-evaluate day/night from `frames` and lock/restore exposure accordingly.

        Reuses the same frames this poll already pulled from the capture
        thread's buffer - no second read, no extra camera access.
        ExposureAutoLock.maybe_update() rate-limits itself internally
        (HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S), so this is cheap to call
        every poll and returns None on most calls. Every real evaluation -
        including a "hold" - is appended to HOME_TEST_EXPOSURE_LOG_PATH so
        a morning review can match the classifier's decisions against
        what the scene was actually doing.
        """
        decision = self._exposure_lock.maybe_update(frames)
        if decision is None:
            return
        self.exposure_locked = self._exposure_lock.locked
        if decision.action != "hold":
            logger.info(
                "home_test: exposure %s (median_saturation=%s, median_brightness=%s, "
                "brightness_override=%s, night=%s, applied=%s)",
                decision.action,
                decision.median_saturation,
                decision.median_brightness,
                decision.brightness_override,
                decision.night,
                decision.applied,
            )
        with open(config.HOME_TEST_EXPOSURE_LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "wall_s": decision.wall_s,
                        "median_saturation": decision.median_saturation,
                        "median_brightness": decision.median_brightness,
                        "brightness_override": decision.brightness_override,
                        "night": decision.night,
                        "action": decision.action,
                        "applied": decision.applied,
                    }
                )
                + "\n"
            )

    def _check_manual_fire_trigger(self, now_wall_s: float) -> None:
        """One-shot manual override: force an immediate fire+record, bypassing the vision gate.

        Consumed by touching config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH on
        the board - see that constant's comment for the exact command and
        why this exists. Checked at the top of every inference poll (before
        the frames/detection work below), so the delay between touching the
        file and the actuators firing is at most HOME_TEST_INFERENCE_INTERVAL_S,
        regardless of whether this poll's own frame grab succeeds. The
        trigger file is deleted the instant it is seen, so a stale touch can
        never cause a second, unintended fire later.

        Reuses the same encounter machinery a real qualifying detection
        would: if no encounter is open, starts one - protects the buffered
        pre-roll and closes itself out on the normal departure timeout once
        nothing keeps qualifying it, exactly like a real animal that wanders
        off. If one is already open, forces an immediate re-fire on it,
        ignoring HOME_TEST_REFIRE_INTERVAL_S and HOME_TEST_MAX_FIRES_PER_ENCOUNTER
        - an explicit human override outranks both automatic throttles.

        The actual deterrence call is the one thing NOT reused from a real
        detection: both branches below route to _manual_fire_actuators, not
        _fire_deterrence. A first attempt at this routed through the
        ordinary _fire_deterrence -> handle_footfall_event() call same as a
        real detection, and on 23 Sept a live trigger opened its encounter
        and recorded correctly but never fired the horn or LED -
        handle_footfall_event() ran its own internal vision-confirm watch
        and fuse/decide pass on this synthetic, signal-less call and
        returned alert=False (fused_P=0.184), since a single manual trigger
        has none of the repeated vision corroboration a real, lingering
        animal accumulates. An explicit human override must not be subject
        to a fusion score computed for an autonomous decision, so
        _manual_fire_actuators fires unconditionally instead.
        """
        trigger_path = config.HOME_TEST_MANUAL_FIRE_TRIGGER_PATH
        try:
            triggered = trigger_path.exists()
        except OSError:
            return
        if not triggered:
            return
        try:
            trigger_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "home_test: manual fire trigger seen but could not be removed - "
                "not firing again for it",
                exc_info=True,
            )
            return

        logger.warning("home_test: manual fire trigger consumed - forcing an immediate fire+record")
        if self._encounter is None:
            self._start_encounter(now_wall_s, manual=True)
            return

        encounter = self._encounter
        encounter.last_fire_wall_s = now_wall_s
        encounter.fire_count += 1
        logger.info(
            "home_test: manual fire on already-open encounter at %s (fire %d, cap bypassed)",
            encounter.dir_path,
            encounter.fire_count,
        )
        self._spawn_deterrence(lambda: self._manual_fire_actuators(encounter))

    def _maybe_log_telemetry(self) -> None:
        """Append one performance-log line every HOME_TEST_TELEMETRY_INTERVAL_S.

        Rate-limited the same way _maybe_update_exposure is - cheap to call
        every poll, does real work only occasionally. This is the overnight
        run's own record of model speed and on-device resource headroom,
        for later evidence and for spotting degradation (rising latency,
        falling memory, climbing temperature) after the fact; nothing here
        feeds a fire/decision path, and a failure to read any one metric
        (board_health's readers all return None on error) never blocks it.
        """
        now_wall_s = self._clock()
        if now_wall_s - self._last_telemetry_wall_s < config.HOME_TEST_TELEMETRY_INTERVAL_S:
            return
        self._last_telemetry_wall_s = now_wall_s

        record = {
            "wall_s": now_wall_s,
            "inference_latency_ms": self._last_inference_latency_ms,
            "encounter_active": self._encounter is not None,
            "exposure_locked": self.exposure_locked,
            **board_health.snapshot(config.HOME_TEST_DIR),
        }
        try:
            with open(config.HOME_TEST_TELEMETRY_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError:
            logger.warning("home_test: failed to write telemetry line", exc_info=True)

    def _run_one_poll(self, frames: list[Frame]) -> None:
        """One inference pass: log unconditionally, then run the encounter gate."""
        detect_started = self._monotonic()
        try:
            results = self._detect_vision([f.image for f in frames])
        except Exception:  # noqa: BLE001 - a detector outage must not stop capture
            logger.exception("home_test: detect_vision failed, skipping this poll")
            return
        finally:
            self._last_inference_latency_ms = (self._monotonic() - detect_started) * 1000.0

        now_wall_s = self._clock()
        self._log_detections(now_wall_s, frames, results)

        gate_results = _gate_results_without_degenerate_boxes(frames, results)
        dropped_this_poll = sum(len(d) for d in results) > sum(len(d) for d in gate_results)
        low_texture = _burst_is_low_texture(
            frames, config.HOME_TEST_CAMERA_COVERED_LOW_TEXTURE_STD
        )
        self._update_camera_covered_state(dropped_this_poll, low_texture, now_wall_s)
        check = _vision_check(
            lambda _images, _results=gate_results: _results,
            frames,
            target_labels=config.DETERRENT_TARGET_LABELS,
        )
        qualifies = check.confirmed and self._meets_fire_bar(gate_results)
        if qualifies and self._camera_is_blind():
            logger.error(
                "home_test: detection qualified but the frame buffer is stale (> %.1fs) - "
                "camera is blind, not firing on it",
                config.HOME_TEST_CAMERA_STALE_S,
            )
            qualifies = False
        self._advance_encounter(now_wall_s, qualifies, check)

    def _meets_fire_bar(self, results: list[list[Detection]]) -> bool:
        """Whether this poll clears HOME_TEST_FIRE_MIN_CONFIDENCE.

        Separate from _vision_check()'s own confirmation, which uses
        the field's target-label/majority gate but no confidence floor of
        its own - this mode raises the bar for the fire/protect decision
        specifically (services/config.py's HOME_TEST_FIRE_MIN_CONFIDENCE
        comment has the full rationale), not for detection logging, which
        stays ungated.
        """
        best = 0.0
        for detections in results:
            for detection in detections:
                if detection.label in config.DETERRENT_TARGET_LABELS:
                    best = max(best, detection.confidence)
        return best >= config.HOME_TEST_FIRE_MIN_CONFIDENCE

    def _update_camera_covered_state(
        self, dropped_this_poll: bool, low_texture: bool | None, now_wall_s: float
    ) -> None:
        """Track a sustained run of covered-lens signals as a possible obstruction.

        Purely observational - see HOME_TEST_CAMERA_COVERED_STREAK_POLLS in
        config.py for why this exists and why it is safe. Reads only its
        own streak counter and never touches _encounter, _qualifying_window,
        or any other fire-path state, so it cannot delay, suppress, or bias
        a real detection or encounter either way - it only changes what
        gets logged.

        Two independent signals feed the same streak: dropped_this_poll (a
        frame-filling box, the full-obstruction case) and low_texture (a
        near-uniform frame, added 11 Sept 2026 for the partial-covering
        case that never produces a frame-filling box). Either alone is
        enough to count a poll toward the streak.
        """
        possibly_covered = dropped_this_poll or bool(low_texture)
        if not possibly_covered:
            was_covered = self._covered_streak >= config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS
            self._covered_streak = 0
            if was_covered:
                logger.warning("home_test: camera clear again after a sustained covered-lens run")
                self._log_camera_covered_event(now_wall_s, "clear")
            return

        self._covered_streak += 1
        if self._covered_streak == config.HOME_TEST_CAMERA_COVERED_STREAK_POLLS:
            reason = (
                "frame_filling+low_texture"
                if dropped_this_poll and low_texture
                else "frame_filling"
                if dropped_this_poll
                else "low_texture"
            )
            logger.warning(
                "home_test: camera possibly obstructed - %d consecutive polls flagged (%s)",
                self._covered_streak,
                reason,
            )
            self._log_camera_covered_event(now_wall_s, "covered", reason)

    def _log_camera_covered_event(
        self, wall_s: float, state: str, reason: str | None = None
    ) -> None:
        """Append one line to HOME_TEST_CAMERA_COVERED_LOG_PATH for a covered/clear transition."""
        record: dict[str, Any] = {"wall_s": wall_s, "state": state}
        if reason is not None:
            record["reason"] = reason
        try:
            with open(config.HOME_TEST_CAMERA_COVERED_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        except OSError:
            logger.warning("home_test: failed to write camera-covered log line", exc_info=True)

    def _log_detections(
        self, wall_s: float, frames: list[Frame], results: list[list[Detection]]
    ) -> None:
        """Append every detection from this poll to HOME_TEST_DETECTIONS_PATH.

        One line per Detection, unconditional - see this module's own
        docstring for why logging is never gated the way firing is.
        """
        if not any(results):
            return
        with open(config.HOME_TEST_DETECTIONS_PATH, "a", encoding="utf-8") as fh:
            for frame, detections in zip(frames, results, strict=True):
                for detection in detections:
                    fh.write(
                        json.dumps(
                            {
                                "wall_s": wall_s,
                                "frame_timestamp_s": frame.timestamp_s,
                                "label": detection.label,
                                "confidence": detection.confidence,
                                "x": detection.x,
                                "y": detection.y,
                                "width": detection.width,
                                "height": detection.height,
                            }
                        )
                        + "\n"
                    )
        self._maybe_save_review_still(wall_s, frames, results)

    def _maybe_save_review_still(
        self, wall_s: float, frames: list[Frame], results: list[list[Detection]]
    ) -> None:
        """Save one representative still for a detection that misses the fire gate.

        Purely an evidence trail for the human review the morning after - see
        HOME_TEST_REVIEW_DIR's comment in config.py for the gap this closes.
        Never reads or writes anything the encounter/fire state machine
        touches, so it cannot affect a firing decision either way. Skipped
        entirely while an encounter is active: that case is already fully
        covered by the encounter's own continuous ring-protection.

        A frame-filling detection (see HOME_TEST_MAX_BOX_AREA_FRACTION) is
        also skipped here - added 11 Sept 2026 after a covered lens spent
        ~40 minutes saving one near-identical blank-blob still every
        HOME_TEST_REVIEW_MIN_INTERVAL_S. Those boxes carry no localisation
        information (that is the whole reason the fire gate drops them
        too), so there is nothing in the frame worth a human's review time
        or the disk space - see _update_camera_covered_state() for the
        actual obstruction alert this condition now raises instead.
        """
        if self._encounter is not None:
            return
        if self._review_bytes >= config.HOME_TEST_REVIEW_MAX_TOTAL_BYTES:
            return
        for frame, detections in zip(frames, results, strict=True):
            try:
                height, width = frame.image.shape[:2]
                frame_area = float(height) * float(width)
            except (AttributeError, ValueError, TypeError):
                frame_area = 0.0
            best: Detection | None = None
            for detection in detections:
                if detection.confidence < config.HOME_TEST_REVIEW_MIN_CONFIDENCE:
                    continue
                if frame_area > 0.0:
                    box_fraction = (detection.width * detection.height) / frame_area
                    if box_fraction >= config.HOME_TEST_MAX_BOX_AREA_FRACTION:
                        continue
                if best is None or detection.confidence > best.confidence:
                    best = detection
            if best is None:
                continue
            last_saved = self._last_review_save_wall_s.get(best.label, 0.0)
            if wall_s - last_saved < config.HOME_TEST_REVIEW_MIN_INTERVAL_S:
                continue
            name = f"{wall_s:018.6f}_{best.label}_{best.confidence:.3f}.jpg"
            path = config.HOME_TEST_REVIEW_DIR / name
            ok, encoded = cv2.imencode(
                ".jpg", frame.image, [cv2.IMWRITE_JPEG_QUALITY, config.HOME_TEST_JPEG_QUALITY]
            )
            if not ok:
                logger.warning("home_test: failed to encode review still for %s", best.label)
                continue
            try:
                path.write_bytes(encoded.tobytes())
            except OSError:
                logger.warning("home_test: failed to write review still %s", path)
                continue
            self._review_bytes += path.stat().st_size
            self._last_review_save_wall_s[best.label] = wall_s
            logger.info(
                "home_test: saved review still %s (confidence=%.3f, below fire bar)",
                name,
                best.confidence,
            )

    # -- encounter state machine ------------------------------------------

    def _advance_encounter(self, now_wall_s: float, qualifies: bool, check: VisionCheck) -> None:
        """Idle -> active -> postroll-and-close, per this poll's result.

        Called once per inference poll (HOME_TEST_INFERENCE_INTERVAL_S
        apart), never from the capture thread - the encounter machine only
        needs to run as often as new detections can arrive.

        7 Sept field-test addition: an encounter used to fire deterrence
        exactly once, on _start_encounter(), then run silent for however
        long the animal stayed. While the encounter remains active and
        still qualifying, this now re-fires every HOME_TEST_REFIRE_INTERVAL_S
        - a real animal that isn't deterred by the first roar needs a
        second and third, not silence until it wanders off on its own.

        7 Sept field-test addition #2: an encounter used to have its ring
        frames protected only twice - once at _start_encounter() (pre-roll)
        and once at _close_encounter() (post-roll) - with nothing copied in
        between. _rotate_ring() deletes anything older than
        HOME_TEST_PREROLL_S every capture-loop iteration regardless of
        whether an encounter is active, so any encounter running longer
        than about one pre-roll window opened a dead gap in the middle of
        its own footage: confirmed on the first real encounter of that run, which
        had a single 116s stretch with zero protected frames sandwiched
        between two dense ~13fps clusters at its edges - a slideshow with
        the whole approach-fire-depart arc missing from its middle, not a
        capture-rate problem (the capture thread sustains ~10-13fps the
        whole time; this is confirmed live, not assumed). This now sweeps
        new ring frames into the encounter directory every poll for as long
        as the encounter stays open, so the full duration gets protected at
        native capture rate, not just its two edges.

        11 Sept field-test finding: a real animal at the far edge of the
        camera's night range does not read as a clean run of qualifying
        polls - it reads as a cluster of near-misses with occasional hits
        scattered through it. The night of 10-11 Sept's Boar cluster
        (22:41:55-22:43:33Z) put frames at 0.52-0.63 against a 0.60 fire
        floor, clearing it at :23/:28/:33 - 5s apart, i.e. 4 non-qualifying
        polls between each hit at this module's 1.0s inference interval -
        and never twice back to back. A strict "N in a row, one miss wipes
        it" streak (the previous design here) can never open on that
        pattern regardless of how tight the animal's actual dwell time is.
        Requiring HOME_TEST_FIRE_CONSECUTIVE_POLLS qualifying polls within
        the last HOME_TEST_FIRE_WINDOW_POLLS (a bounded deque, not a
        streak) tolerates exactly that gap while changing nothing else:
        every poll counted here has already separately cleared both the
        Boar burst-majority gate and HOME_TEST_FIRE_MIN_CONFIDENCE, so this
        does not loosen either of the two levers that measurably control
        Boar's false-positive rate (services/config.py's
        VISION_SPECIES_BURST_MAJORITY_LABELS and
        HOME_TEST_FIRE_MIN_CONFIDENCE comments). It also does not repeat
        the 10 Sept dawn storm, which came from
        HOME_TEST_FIRE_CONSECUTIVE_POLLS itself being cut to 1 (a single
        qualifying poll firing alone) - that count requirement is
        unchanged here, only the "must be consecutive" part is relaxed.
        """
        self._qualifying_window.append(qualifies)

        if self._encounter is not None and self._camera_is_blind():
            logger.error(
                "home_test: camera blind mid-encounter at %s - closing it now, no further fires",
                self._encounter.dir_path,
            )
            self._close_encounter(self._encounter)
            self._encounter = None
            self._qualifying_window.clear()
            return

        if self._encounter is None:
            if sum(self._qualifying_window) >= config.HOME_TEST_FIRE_CONSECUTIVE_POLLS:
                self._start_encounter(now_wall_s)
            return

        encounter = self._encounter
        if qualifies:
            encounter.last_qualifying_wall_s = now_wall_s
        self._protect_ring_since(encounter, encounter.started_wall_s)

        since_last = now_wall_s - encounter.last_qualifying_wall_s
        duration = now_wall_s - encounter.started_wall_s
        if since_last >= config.HOME_TEST_DEPARTURE_TIMEOUT_S + config.HOME_TEST_POSTROLL_S:
            self._close_encounter(encounter)
            self._encounter = None
            self._qualifying_window.clear()
        elif duration >= config.HOME_TEST_MAX_ENCOUNTER_S:
            logger.warning(
                "home_test: encounter at %s hit HOME_TEST_MAX_ENCOUNTER_S, closing",
                encounter.dir_path,
            )
            self._close_encounter(encounter)
            self._encounter = None
            self._qualifying_window.clear()
        elif (
            qualifies
            and now_wall_s - encounter.last_fire_wall_s >= config.HOME_TEST_REFIRE_INTERVAL_S
        ):
            if encounter.fire_count >= config.HOME_TEST_MAX_FIRES_PER_ENCOUNTER:
                encounter.last_fire_wall_s = now_wall_s
                logger.warning(
                    "home_test: encounter at %s still qualifying but hit "
                    "HOME_TEST_MAX_FIRES_PER_ENCOUNTER (%d) - still recording, not re-firing",
                    encounter.dir_path,
                    config.HOME_TEST_MAX_FIRES_PER_ENCOUNTER,
                )
            else:
                encounter.last_fire_wall_s = now_wall_s
                encounter.fire_count += 1
                logger.info(
                    "home_test: encounter at %s still qualifying, re-firing (fire %d/%d)",
                    encounter.dir_path,
                    encounter.fire_count,
                    config.HOME_TEST_MAX_FIRES_PER_ENCOUNTER,
                )
                self._spawn_deterrence(lambda: self._fire_deterrence(encounter))

    def _start_encounter(self, now_wall_s: float, *, manual: bool = False) -> None:
        """Open a new encounter directory, protect the buffered pre-roll, spawn Thread C.

        The pre-roll is already sitting in HOME_TEST_RING_DIR when this
        runs - _protect_frame() below copies every ring frame not yet
        older than HOME_TEST_PREROLL_S, which is exactly the approach
        footage a detection alone cannot capture retroactively any other
        way.

        manual=True is the only thing that changes which deterrence call
        gets queued - see _manual_fire_actuators's docstring for why a
        human-triggered fire cannot go through the same call as a real
        detection.
        """
        dir_name = time.strftime("%Y%m%dT%H%M%S", time.localtime(now_wall_s))
        dir_path = config.HOME_TEST_ENCOUNTERS_DIR / dir_name
        dir_path.mkdir(parents=True, exist_ok=True)

        encounter = _Encounter(
            started_wall_s=now_wall_s,
            last_qualifying_wall_s=now_wall_s,
            dir_path=dir_path,
            last_fire_wall_s=now_wall_s,
            fire_count=1,
        )
        self._encounter = encounter
        self._protect_ring_since(encounter, now_wall_s - config.HOME_TEST_PREROLL_S)

        logger.info("home_test: encounter started at %s (pre-roll protected)", dir_path)
        if manual:
            self._spawn_deterrence(lambda: self._manual_fire_actuators(encounter))
        else:
            self._spawn_deterrence(lambda: self._fire_deterrence(encounter))

    def _spawn_deterrence_thread(self, run: Callable[[], None]) -> None:
        """Default spawn_deterrence: enqueue onto the one persistent deterrence worker.

        Tests substitute a synchronous ``lambda fn: fn()`` via the
        constructor's spawn_deterrence parameter so deterrence firing is
        deterministic and doesn't race assertions.
        """
        self._deterrence_queue.put(run)

    def _deterrence_loop(self) -> None:
        """Thread C: run every queued encounter's deterrence call, serially, forever.

        One thread rather than one per encounter, because an encounter's
        deterrence opens the single USB camera and drives the single horn:
        two of them at once is not a slow night, it is two readers on one
        /dev/video node and two overlapping horn bursts. Serialising here
        means the second encounter waits for the first instead.

        This also used to be the only thing keeping
        cognition/experience.py's ExperienceStore alive, back when that
        class cached one sqlite3.Connection on whichever thread opened it
        and refused every other. The previous design spawned a fresh
        threading.Thread per encounter and broke exactly that - CPython can
        reuse an exited thread's OS identifier for a later one, so some
        record_trigger() calls landed back on the connection's original
        owning thread purely by luck while others raised
        sqlite3.ProgrammingError, intermittently and silently swallowed by
        _fire_deterrence's own broad except. The store is thread-safe in
        its own right now and no longer depends on this thread for it, but
        the camera and the actuators still do, so the queue stays.
        """
        while not self._stop.is_set():
            self._beat("deterrence")
            try:
                run = self._deterrence_queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                run()
            finally:
                # Re-stamped on completion, not just at the top of the loop -
                # a run() that never returns (despite handle_footfall_event's
                # own sub-15s Bridge-call timeouts) leaves this heartbeat
                # aging from the moment it started, which is exactly what
                # should trip the stall check if it ever runs past
                # HOME_TEST_STALL_TIMEOUT_S.
                self._beat("deterrence")

    def _protect_ring_since(self, encounter: _Encounter, cutoff_wall_s: float) -> None:
        """Copy every ring frame at or after cutoff_wall_s not already in the encounter dir.

        Shared by _start_encounter (pre-roll, cutoff = start time minus
        HOME_TEST_PREROLL_S), _advance_encounter (continuous, cutoff = the
        encounter's own start time - see that method's docstring for why
        this needs to run every poll rather than only at the two edges),
        and _close_encounter (final post-roll catch-up, cutoff = the last
        qualifying detection). The per-file existence check makes repeated
        calls with an overlapping range cheap and idempotent - a frame
        already protected is skipped, not re-copied.
        """
        for path in sorted(config.HOME_TEST_RING_DIR.glob("*.jpg")):
            try:
                frame_wall_s = float(path.name.split("_", 1)[0])
            except ValueError:
                continue
            if frame_wall_s >= cutoff_wall_s and not (encounter.dir_path / path.name).exists():
                self._protect_frame(encounter, path)

    def _protect_frame(self, encounter: _Encounter, ring_path: Path) -> None:
        """Copy one ring frame into the encounter directory, respecting the session byte cap.

        A copy, not a move: _rotate_ring() in the capture thread only ever
        deletes frames older than the pre-roll window, so a ring frame that
        has already been protected simply ages out of the ring on its own
        shortly after - no coordination needed between the two.
        """
        if not encounter.protecting:
            return
        if self._protected_bytes >= config.HOME_TEST_MAX_TOTAL_BYTES:
            encounter.protecting = False
            logger.warning(
                "home_test: HOME_TEST_MAX_TOTAL_BYTES reached, no longer protecting new frames "
                "(detections keep logging)"
            )
            return
        try:
            data = ring_path.read_bytes()
        except OSError:
            return
        (encounter.dir_path / ring_path.name).write_bytes(data)
        self._protected_bytes += len(data)

    def _close_encounter(self, encounter: _Encounter) -> None:
        """Sweep any not-yet-protected frames still in the ring, then finish.

        _advance_encounter() has already been protecting continuously
        (cutoff = encounter start) on every poll while this encounter was
        active, so this call's own cutoff only needs to catch the tail
        written since that last poll - encounter.last_qualifying_wall_s is
        a safe, slightly-generous cutoff for that final catch-up, giving
        the clip its post-roll.
        """
        now_wall_s = self._clock()
        self._protect_ring_since(encounter, encounter.last_qualifying_wall_s)
        logger.info(
            "home_test: encounter closed at %s, duration=%.1fs, protected_bytes_total=%d",
            encounter.dir_path,
            now_wall_s - encounter.started_wall_s,
            self._protected_bytes,
        )

    def _fire_deterrence(self, encounter: _Encounter) -> None:
        """Thread C: run the unforked field deterrence path for this encounter.

        seismic_available=False is the only thing distinguishing this call
        from a real field footfall - see reflex_loop.handle_footfall_event's
        own docstring for exactly what that kwarg changes: fuse() drops the
        seismic modality, and _watch_length_s() grants the same extended
        vision-confirmation window a strong geophone reading would, since a
        vision-only trigger has no seismic-based reason to be watched any
        more cheaply. probability/sta_lta_ratio/feature_vector carry no real
        geophone reading (none exists in this mode) and are logged, not scored.
        """
        try:
            handle_footfall_event(
                config.SCHEMA_VERSION,
                0.0,
                0.0,
                [],
                camera=SharedFrameCamera(self),
                seismic_available=False,
                **self._footfall_kwargs,
            )
        except Exception:  # noqa: BLE001 - a deterrence failure must not kill the session
            logger.exception(
                "home_test: deterrence sequence failed for encounter at %s", encounter.dir_path
            )

    # The one actuator path in the tree that does not run through
    # handle_footfall_event, so it has to take reflex_loop's event lock
    # itself. A manual fire that lands mid-encounter is dropped: the horn
    # the operator is asking for is already sounding.
    @_one_event_at_a_time
    def _manual_fire_actuators(self, encounter: _Encounter) -> None:
        """Thread C, manual path: fire horn+LED (+IR at night) directly, no fuse/decide.

        Only reached from _check_manual_fire_trigger - every real detection
        still fires through the unmodified _fire_deterrence/
        handle_footfall_event() call, exactly as this module's docstring
        promises for the field's deterrence path. This method is the
        deliberate, narrow exception to that promise: it exists solely
        because a human saying "fire now" is not a detection to be fused
        and decided on, it is an instruction, and reflex_loop's own
        vision-confirm watch has no repeated corroboration to work with on
        a synthetic, single-shot trigger (see _check_manual_fire_trigger's
        docstring for the live incident this fixes).

        Always resolves Tier 3 (the strongest response) rather than asking
        select_tier - there is no fused probability or context bucket to
        rank tiers by here, and an explicit override should not be
        second-guessed down to a lower tier. For the same reason this never
        calls experience.record_attempt(): crediting the bandit's learned
        tier values for an event with no real detection signal behind it
        would corrupt them. Recording itself is untouched - HomeTestSession's
        own pre-roll/continuous/post-roll ring protection already runs
        independently of whichever deterrence function is called here.

        Mirrors handle_footfall_event's own actuator section exactly
        (drive_horn and drive_led together, each on its own thread, both
        joined before either ack is read) so the manual path startles an
        animal the same way the automatic one does. Wrapped in the same
        broad except _fire_deterrence uses: a manual-fire failure must not
        kill the persistent deterrence worker thread.

        This used to pulse IR first. It no longer does, and the mirror is
        closer for it: IR is a camera light, not a deterrent, and the
        automatic path now lights the scene during the vision watch rather
        than at the moment of the fire. There is no watch behind a button
        press, so there is nothing here for a pulse to illuminate - the
        session's own continuous recording is already exposed for the
        scene by ExposureAutoLock, which runs whether or not anyone
        presses anything.
        """
        try:
            kwargs = self._footfall_kwargs
            schema_version = config.SCHEMA_VERSION
            rng = random.Random()
            action = cognition_config.resolve_tier_action(
                Tier.TIER_3, rng, config.NODE_HOUSEHOLD_PROXIMITY, species="Elephant"
            )

            horn_result: dict[str, bool] = {}
            led_result: dict[str, bool] = {}

            def _fire_horn() -> None:
                horn_result["ack"] = kwargs["drive_horn"](
                    schema_version,
                    action.horn_gain_pct,
                    action.horn_duration_ms,
                    action.horn_track_id,
                )

            def _fire_led() -> None:
                led_result["ack"] = kwargs["drive_led"](
                    schema_version,
                    action.led_channel_id,
                    action.led_pattern_id,
                    action.led_gain_pct,
                    action.led_duration_ms,
                )

            horn_thread = threading.Thread(target=_fire_horn, daemon=True)
            led_thread = threading.Thread(target=_fire_led, daemon=True)
            horn_thread.start()
            led_thread.start()
            horn_thread.join()
            led_thread.join()

            logger.warning(
                "home_test: MANUAL FIRE actuated for encounter at %s - "
                "drive_horn ack=%s drive_led ack=%s",
                encounter.dir_path,
                horn_result.get("ack"),
                led_result.get("ack"),
            )
        except Exception:  # noqa: BLE001 - a deterrence failure must not kill the session
            logger.exception(
                "home_test: manual fire actuator sequence failed for encounter at %s",
                encounter.dir_path,
            )
