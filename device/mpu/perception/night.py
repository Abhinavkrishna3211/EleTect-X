"""Frame-derived day/night classifier, used only to gate the IR illuminator.

The IMX462 day/night camera (ADR 0001) carries a mechanical IR-cut filter
it swaps on its own: in daylight the filter sits in front of the sensor
(colour image, the near-IR the external illuminator emits is blocked before
it reaches a pixel), and once the scene is dark enough the filter swings
out (monochrome image, sensor now IR-sensitive). Firing pulse_ir() while
the filter is in is pure waste - MOSFET duty budget and battery spent on
photons the sensor cannot see - so the reflex loop only fires it when the
filter is out.

Nothing on this board reports the filter position directly. But the swap is
plainly visible in the frame: a mono / IR-lit frame has almost no colour,
so its mean HSV saturation collapses to a handful of units (JPEG chroma
noise only), while any daylight frame - even a dull, overcast one - keeps
real chroma and reads tens of units. Keying "is it night?" off that
measured collapse, rather than a wall-clock sunset table or an added
photocell, means the gate is correct in exactly the awkward cases (heavy
overcast at noon, a yard light pointed near the lens at 3 a.m., the ten
minutes either side of the filter's own switch) because it keys on the same
optical state that decides whether IR would help at all.

Measured on the real rig, Kothamangalam backyard, 1-2 Sep 2026: a genuine
night frame read mean S = 0.0; a daylight colour frame read S > 30. The
threshold (services/config.py NIGHT_SATURATION_THRESHOLD) sits in that gap
with margin on both sides.

Deliberate cv2 dependency, function-local only, exactly as
perception/camera.py and perception/detector.py already justify it - this
module stays importable on a dev laptop with no OpenCV present, and only
the one function that actually reads pixels imports it.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from services import config

logger = logging.getLogger(__name__)


def frame_mean_saturation(image: Any) -> float | None:
    """Mean HSV saturation (0-255 scale) of one BGR frame, or None.

    None means the frame could not be measured at all: it was None (the
    camera fake hands those out, and a real failed grab never reaches
    here), had no usable shape, or cv2 raised on it. A real monochrome
    night frame returns a small positive number, not None.
    """
    if image is None:
        return None
    try:
        import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

        shape = getattr(image, "shape", None)
        if not shape or len(shape) != 3 or shape[2] != 3:
            # Not a 3-channel BGR frame - a single-channel buffer carries no
            # chroma to measure, so "night" cannot be inferred from it here.
            return None
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        return float(hsv[:, :, 1].mean())
    except Exception as exc:  # noqa: BLE001 - a bad frame must never propagate
        logger.warning("frame_mean_saturation failed on a frame: %s", exc)
        return None


def frame_mean_brightness(image: Any) -> float | None:
    """Mean pixel intensity (0-255 scale) of one frame, or None.

    Unlike frame_mean_saturation() this reads luma, not chroma, so it
    stays meaningful on the IR-cut-open monochrome frames the night camera
    produces - those carry no saturation to measure but their brightness
    still climbs as ambient light rises at dawn. A 3-channel BGR frame is
    converted to grayscale; a single-channel buffer is measured directly.

    None means the frame could not be measured at all: it was None, had no
    usable shape, or cv2 raised on it.
    """
    if image is None:
        return None
    try:
        import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

        shape = getattr(image, "shape", None)
        if not shape or len(shape) not in (2, 3):
            return None
        if len(shape) == 3:
            if shape[2] != 3:
                return None
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        return float(gray.mean())
    except Exception as exc:  # noqa: BLE001 - a bad frame must never propagate
        logger.warning("frame_mean_brightness failed on a frame: %s", exc)
        return None


def frame_clip_fraction(image: Any, clip_value: float) -> float | None:
    """Fraction of pixels at or above `clip_value` (0-255 luma), or None.

    Exists because frame_mean_brightness()'s frame-wide average is blind to
    a localized blowout: a night frame that is mostly black background with
    one small patch of near-field foliage driven to solid white by the IR
    pulse (IR intensity falls off with distance^2, so one fixed exposure
    tuned for a several-metre subject saturates anything a foot from the
    lens) can still average well below NIGHT_BRIGHTNESS_DAY_THRESHOLD - the
    dawn override's global mean cannot see it, but the fraction of clipped
    pixels can. Same 3-channel-or-grayscale handling as
    frame_mean_brightness(); a single-channel buffer is measured directly.

    None means the frame could not be measured at all: it was None, had no
    usable shape, or cv2 raised on it.
    """
    if image is None:
        return None
    try:
        import cv2  # noqa: PLC0415 (deliberately local, see module docstring)

        shape = getattr(image, "shape", None)
        if not shape or len(shape) not in (2, 3):
            return None
        if len(shape) == 3:
            if shape[2] != 3:
                return None
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        return float((gray >= clip_value).mean())
    except Exception as exc:  # noqa: BLE001 - a bad frame must never propagate
        logger.warning("frame_clip_fraction failed on a frame: %s", exc)
        return None


def frames_are_night(images: list[Any], saturation_threshold: float) -> bool | None:
    """Decide night vs day from a short burst of BGR frames.

    Args:
        images: Frame.image ndarrays (BGR), typically the pre-decision
            vision-check burst. Frames that cannot be measured are dropped.
        saturation_threshold: Mean HSV S below which a frame is read as a
            mono / IR-cut-open (night) frame. services/config.py's
            NIGHT_SATURATION_THRESHOLD is the real value.

    Returns:
        True  - the burst's median saturation is below the threshold: the
                IR-cut filter is out, the illuminator will land on a
                sensitive sensor, pulse_ir() is worth firing.
        False - median saturation is at or above the threshold: daylight /
                filter in, the illuminator would be invisible.
        None  - not one frame in the burst could be measured. The caller
                treats this the same as False for firing purposes (an
                unmeasurable vision-check burst means the evidence burst
                has nothing to illuminate either), but logs it distinctly.
    """
    sats = [s for s in (frame_mean_saturation(img) for img in images) if s is not None]
    if not sats:
        return None
    return median(sats) < saturation_threshold


@dataclass(frozen=True)
class ExposureDecision:
    """One ExposureAutoLock.maybe_update() outcome, shaped for logging.

    Attributes:
        wall_s: Wall-clock time of this re-evaluation (injected clock, not
            necessarily time.time() - see ExposureAutoLock's constructor).
        saturations: Per-frame frame_mean_saturation() readings that fed
            this decision (None entries dropped, same as frames_are_night).
        median_saturation: median(saturations), or None if every frame in
            the batch was unmeasurable.
        night: The is_night() answer this batch produced - True, False, or
            None if unmeasurable. Note this can differ from the *acted-on*
            state: hysteresis means a single dissenting reading shows up
            here with action="hold".
        action: "lock" or "restore" if this decision changed exposure
            state, "hold" if it left it alone (debounce not yet satisfied,
            answer agreed with current state, or is_night() raised).
        applied: Whether the underlying Camera.lock_night_exposure() /
            restore_auto_exposure() call verified its own read-back. False
            when action is "hold" (nothing was called) or when the
            underlying call itself reported failure.
        brightnesses: Per-frame frame_mean_brightness() readings that fed
            this decision (None entries dropped).
        median_brightness: median(brightnesses), or None if every frame in
            the batch was unmeasurable.
        brightness_override: True when is_night() answered night but the
            median brightness was at or above NIGHT_BRIGHTNESS_DAY_THRESHOLD,
            so `night` was forced to False - the dawn case on the IR
            camera, where saturation stays ~0 but the frame is plainly
            daylit. `night` above already reflects the forced value.
        clip_fractions: Per-frame frame_clip_fraction() readings that fed a
            trim check (only computed while locked to night exposure and
            `night` still reads True - see exposure_value). Empty when no
            trim check ran this tick.
        median_clip_fraction: median(clip_fractions), or None if no trim
            check ran or every frame in the batch was unmeasurable.
        exposure_value: The manual exposure value the device is holding
            after this decision - the locked base value, or a lower value
            if trim_applied ratcheted it down. None while not locked.
        trim_applied: True when this decision stepped the locked exposure
            down because median_clip_fraction was at or above
            NIGHT_CLIP_FRACTION_THRESHOLD - see the class docstring's
            "near-field clip trim" section.
    """

    wall_s: float
    saturations: list[float]
    median_saturation: float | None
    night: bool | None
    action: str
    applied: bool
    brightnesses: list[float] = field(default_factory=list)
    median_brightness: float | None = None
    brightness_override: bool = False
    clip_fractions: list[float] = field(default_factory=list)
    median_clip_fraction: float | None = None
    exposure_value: int | None = None
    trim_applied: bool = False


class ExposureAutoLock:
    """Periodically re-locks or restores exposure as a scene's day/night state changes.

    services/home_test.py's bug (6-7 Sept 2026): HomeTestSession.start()
    locked NIGHT_LOCKED_EXPOSURE once at camera open and never revisited
    it, so an indoor bench test under room lighting stayed locked at a
    dark-scene exposure for the whole session. services/reflex_loop.py's
    vision-watch illumination block already gets this right for a single
    event - it calls is_night() and only locks when the answer is True -
    but that is one decision made once per encounter, not a standing
    policy for a session that runs for hours across a real dusk or dawn.

    This class is that standing policy, built from pieces that already
    exist rather than a new detector: `is_night` is the same
    NightDecideFn callable services/reflex_loop.py and main.py's
    _is_night() already use (frames_are_night() bound to
    NIGHT_SATURATION_THRESHOLD); `lock`/`restore` are
    Camera.lock_night_exposure()/restore_auto_exposure() bound methods.
    Feed it a batch of recent frames on whatever cadence the caller
    already polls at; it decides internally whether enough time has
    passed to re-evaluate at all.

    Brightness override for the dawn blind spot: frames_are_night() keys on
    HSV saturation, which collapses to ~0 on the IR-cut-open monochrome
    frame and stays there whatever the ambient light. That is exactly right
    for "would the IR pulse help", but it means the classifier cannot see
    daybreak coming - at the Kothamangalam field trial (dawn, 10 Sept 2026)
    it held "night" straight through sunrise while the frame brightness
    climbed from a locked-scene ~138 to 190+, the exposure lock never
    released, and the over-exposed sensor fed a continuous run of spurious
    Boar boxes. So when is_night() answers night but the median frame
    brightness (frame_mean_brightness(), luma not chroma) is at or above
    NIGHT_BRIGHTNESS_DAY_THRESHOLD, the answer is forced to day before the
    hysteresis sees it - the override can only release a lock, never impose
    one, so a bright but genuinely dark scene just gets one interval of
    auto-exposure, not an over-exposure.

    Debounced three ways, all against real behaviour seen on this rig:
    - `interval_s` rate-limits re-evaluation - re-running an HSV
      conversion over every frame the caller happens to hand it would cost
      more than the scene changes that fast.
    - `flip_consecutive` requires that many consecutive *agreeing*
      re-evaluations before changing state - a single ambiguous reading
      right at the IR-cut filter's own mechanical transition (the "ten
      minutes either side of the filter's own switch" perception/night.py
      already calls out as an awkward case) must not flap the lock.
    - `min_dwell_s` withholds a confirmed flip if less than that many
      seconds have passed since the *last actual* lock()/restore() call.
      Found live, 11 Sept 2026: under a partially covered lens, locking to
      a fixed dark exposure made the scene read dark enough to confirm
      another lock, and restoring made the same scene read bright enough to
      confirm a restore - a self-sustaining lock/restore/lock cycle every
      interval_s * flip_consecutive seconds, because each action changes
      the very signal the next debounce evaluates. Neither of the other two
      knobs can fix that: each dwell state is internally consistent for its
      own full duration, so any fixed consecutive-count debounce is
      trivially satisfied every half-cycle regardless of its size. Without
      an action-anchored cooldown a real dusk/dawn transition and a
      self-induced oscillation look identical to flip_consecutive alone.

    Near-field clip trim: NIGHT_LOCKED_EXPOSURE was measured against a
    static, empty, far-field scene (services/config.py's own caveat) - it
    was never tested against near-field foliage a foot or two from the
    lens. IR intensity falls off with distance^2, so the single fixed
    exposure that correctly exposes a subject several metres out can drive
    close foliage to solid-white clipping (seen live in the field, 23 Sept
    2026 - a locked frame with foliage blown to white in the near field and
    the background near-black). The existing brightness_override cannot
    catch this: it watches the frame-wide mean, which stays low on a frame
    that is mostly black with just one localized blown patch. So, only
    while already locked to night exposure and still agreeing night=True
    (i.e. not in the middle of a day/night flip), each re-evaluation also
    checks frame_clip_fraction() against NIGHT_CLIP_FRACTION_THRESHOLD; if
    at or over threshold and `lock_at` was supplied, the locked exposure is
    stepped down by NIGHT_EXPOSURE_TRIM_STEP (floored at
    NIGHT_EXPOSURE_FLOOR, below which services/config.py documents the
    sensor as noise-limited). The trim only ever ratchets down within one
    lock dwell - it resets to the base NIGHT_LOCKED_EXPOSURE the next time a
    fresh lock() fires (the next dusk). This is deliberate: a monotonic,
    floor-limited decrease cannot re-create the self-sustaining oscillation
    min_dwell_s was built to stop (there is no path back up for the next
    check to react to), at the cost of not recovering full far-field reach
    later in the same night if the obstruction clears - an acceptable
    trade against a real, seen-in-the-field overexposure, and one to
    revisit once an overnight soak with the trim active gives real
    recovery-needed data (see docs/KNOWN_GAPS.md).

    Never raises: an is_night() exception is caught, logged, and leaves
    state exactly as it was - the same "perception failure never blocks
    capture or actuation" rule services/reflex_loop.py's own vision-watch
    illumination block follows for the same callable.

    The kill switch (NIGHT_EXPOSURE_LOCK_ENABLED, ELETECT_NIGHT_EXPOSURE_LOCK)
    stays a hard manual override: while it reads False, this issues
    restore() exactly once and then locks nothing, whatever the frames
    say, matching how the bench test used it on 6 Sept.
    """

    def __init__(
        self,
        is_night: Callable[[list[Any]], bool | None],
        lock: Callable[[], bool],
        restore: Callable[[], bool],
        *,
        lock_at: Callable[[int], bool] | None = None,
        base_exposure: int = config.NIGHT_LOCKED_EXPOSURE,
        clip_value: float = config.NIGHT_CLIP_VALUE,
        clip_fraction_threshold: float = config.NIGHT_CLIP_FRACTION_THRESHOLD,
        exposure_trim_step: int = config.NIGHT_EXPOSURE_TRIM_STEP,
        exposure_floor: int = config.NIGHT_EXPOSURE_FLOOR,
        interval_s: float = config.HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S,
        flip_consecutive: int = config.HOME_TEST_EXPOSURE_FLIP_CONSECUTIVE,
        min_dwell_s: float = config.HOME_TEST_EXPOSURE_MIN_DWELL_S,
        monotonic: Callable[[], float] = time.monotonic,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Construct the policy; does no I/O and issues no lock/restore call yet.

        Args:
            is_night: Same shape as main.py's _is_night() - takes a list of
                Frame objects (each with an .image ndarray), returns
                True/False/None. Matches the real call sites: main.py's
                _is_night(frames) and reflex_loop.py's
                is_night(vision_frames) both pass Frame objects, never
                raw images.
            lock: Called to switch to manual night exposure at the base
                value - typically Camera.lock_night_exposure (called with
                no args, so it uses its own default). Must return whether
                the write verified, never raise.
            restore: Called to switch back to auto exposure - typically
                Camera.restore_auto_exposure. Same contract as lock.
            lock_at: Called with an explicit exposure value to apply the
                near-field clip trim - typically the same bound
                Camera.lock_night_exposure as `lock`, just invoked with a
                value argument instead of its default. None (the default)
                disables the clip trim entirely: no frame_clip_fraction()
                calls, no stepping, existing lock/restore behaviour
                unchanged. Same never-raise, verified-return contract as
                lock.
            base_exposure: The value `lock` applies; the trim's ceiling and
                its reset point at the next fresh lock().
            clip_value: Luma (0-255) at or above which a pixel counts as
                clipped, passed to frame_clip_fraction().
            clip_fraction_threshold: median_clip_fraction at or above which
                a re-evaluation steps the locked exposure down.
            exposure_trim_step: How much to lower the locked exposure by
                per triggered trim.
            exposure_floor: Never trim below this value.
            interval_s: Minimum wall-clock gap between re-evaluations.
            flip_consecutive: Consecutive agreeing answers required before
                a state change is acted on.
            min_dwell_s: Minimum wall-clock gap since the last actual
                lock()/restore() call before another one is allowed, even
                once flip_consecutive agrees - the guard against a
                self-sustaining oscillation (see class docstring).
            monotonic: Injectable for tests, paces re-evaluation.
            clock: Injectable for tests, timestamps ExposureDecision only.
        """
        self._is_night = is_night
        self._lock = lock
        self._restore = restore
        self._lock_at = lock_at
        self._base_exposure = base_exposure
        self._clip_value = clip_value
        self._clip_fraction_threshold = clip_fraction_threshold
        self._exposure_trim_step = exposure_trim_step
        self._exposure_floor = exposure_floor
        self._interval_s = interval_s
        self._flip_consecutive = flip_consecutive
        self._min_dwell_s = min_dwell_s
        self._monotonic = monotonic
        self._clock = clock

        self._locked = False
        self._last_check_monotonic: float | None = None
        self._last_action_monotonic: float | None = None
        self._streak_answer: bool | None = None
        self._streak_count = 0
        self._kill_switch_restored = False
        self._current_exposure: int = base_exposure

    @property
    def locked(self) -> bool:
        """Whether the most recent applied decision was a verified lock."""
        return self._locked

    def note_external_lock(self, applied: bool) -> None:
        """Record that something outside maybe_update() already locked exposure.

        services/home_test.py's SharedFrameCamera.lock_night_exposure()
        calls Camera.lock_night_exposure() directly, on demand, right
        before an IR-lit evidence burst - bypassing this policy's own
        interval/debounce entirely, because that caller cannot wait out
        HOME_TEST_EXPOSURE_RECHECK_INTERVAL_S. Call this right after so
        the next periodic maybe_update() knows the device's real state
        instead of assuming it is still on auto - without it, a scene
        that later turns to day would never trigger restore(), because
        this policy would believe it was already unlocked.

        Only moves state to locked on a verified apply; a failed on-demand
        lock leaves this policy's belief about device state unchanged,
        matching the "False means continue on whatever the camera already
        had" contract every lock/restore call in this codebase follows.
        """
        if applied:
            self._locked = True
            self._last_action_monotonic = self._monotonic()
            self._streak_answer = None
            self._streak_count = 0
            self._current_exposure = self._base_exposure

    def maybe_update(self, frames: list[Any]) -> ExposureDecision | None:
        """Re-evaluate day/night from `frames` if `interval_s` has elapsed; act on it.

        `frames` is a list of Frame-like objects (each with an .image
        ndarray) - the same shape main.py's _is_night() and
        reflex_loop.py's is_night() call site both expect. Passed through
        to the injected is_night() unmodified; only unwrapped locally
        (via .image) for the saturation readings below.

        Returns:
            None if it is not yet time to re-evaluate (the common case on
            most calls - callers are expected to call this every poll and
            let it self-rate-limit). Otherwise an ExposureDecision - even
            when the decision was to hold, so a caller that wants to log
            every re-evaluation attempt can.
        """
        now_monotonic = self._monotonic()
        if (
            self._last_check_monotonic is not None
            and now_monotonic - self._last_check_monotonic < self._interval_s
        ):
            return None
        self._last_check_monotonic = now_monotonic

        saturations = [
            s for s in (frame_mean_saturation(f.image) for f in frames) if s is not None
        ]
        median_saturation = median(saturations) if saturations else None
        brightnesses = [
            b for b in (frame_mean_brightness(f.image) for f in frames) if b is not None
        ]
        median_brightness = median(brightnesses) if brightnesses else None

        if not config.NIGHT_EXPOSURE_LOCK_ENABLED:
            action = "hold"
            applied = False
            if not self._kill_switch_restored:
                applied = self._restore()
                self._locked = False
                self._kill_switch_restored = True
                action = "restore"
            self._streak_answer = None
            self._streak_count = 0
            return ExposureDecision(
                wall_s=self._clock(),
                saturations=saturations,
                median_saturation=median_saturation,
                night=None,
                action=action,
                applied=applied,
                brightnesses=brightnesses,
                median_brightness=median_brightness,
                exposure_value=self._current_exposure if self._locked else None,
            )
        self._kill_switch_restored = False

        try:
            night = self._is_night(frames)
        except Exception:  # noqa: BLE001 - perception must never block capture
            logger.exception("ExposureAutoLock: is_night() raised, leaving exposure unchanged")
            return ExposureDecision(
                wall_s=self._clock(),
                saturations=saturations,
                median_saturation=median_saturation,
                night=None,
                action="hold",
                applied=False,
                brightnesses=brightnesses,
                median_brightness=median_brightness,
                exposure_value=self._current_exposure if self._locked else None,
            )

        brightness_override = (
            night is True
            and median_brightness is not None
            and median_brightness >= config.NIGHT_BRIGHTNESS_DAY_THRESHOLD
        )
        if brightness_override:
            # IR-cut-open frame: chroma is ~0 whatever the ambient light, so
            # frames_are_night() cannot see dawn coming and would hold the
            # night lock straight through sunrise, over-exposing the sensor
            # (Kothamangalam field trial, dawn of 10 Sept 2026: median frame
            # brightness climbed 138 -> 190+ while median saturation stayed
            # 0.0, the lock never released, and the over-exposed foliage
            # texture drove a continuous run of spurious low-confidence Boar
            # boxes). Brightness is the signal that actually moves at dawn on
            # this sensor, so a daylit-level reading forces the day answer
            # and lets the normal hysteresis restore auto-exposure.
            night = False

        action = "hold"
        applied = False
        clip_fractions: list[float] = []
        median_clip_fraction: float | None = None
        trim_applied = False
        if night is None or night == self._locked:
            self._streak_answer = None
            self._streak_count = 0
            if self._locked and night is True and self._lock_at is not None:
                clip_fractions = [
                    c
                    for c in (frame_clip_fraction(f.image, self._clip_value) for f in frames)
                    if c is not None
                ]
                median_clip_fraction = median(clip_fractions) if clip_fractions else None
                if (
                    median_clip_fraction is not None
                    and median_clip_fraction >= self._clip_fraction_threshold
                    and self._current_exposure > self._exposure_floor
                ):
                    trimmed_value = max(
                        self._exposure_floor, self._current_exposure - self._exposure_trim_step
                    )
                    if self._lock_at(trimmed_value):
                        logger.info(
                            "exposure auto-lock: trimming locked exposure %d -> %d "
                            "(median clip fraction=%.3f >= %.3f)",
                            self._current_exposure,
                            trimmed_value,
                            median_clip_fraction,
                            self._clip_fraction_threshold,
                        )
                        self._current_exposure = trimmed_value
                        trim_applied = True
        else:
            if self._streak_answer == night:
                self._streak_count += 1
            else:
                self._streak_answer = night
                self._streak_count = 1
            if self._streak_count >= self._flip_consecutive:
                dwell_elapsed = (
                    None
                    if self._last_action_monotonic is None
                    else now_monotonic - self._last_action_monotonic
                )
                if dwell_elapsed is not None and dwell_elapsed < self._min_dwell_s:
                    # A confirmed flip, but too soon after the last actual
                    # lock()/restore() - withhold it rather than act, so a
                    # self-induced oscillation (the action itself flipping
                    # the signal the next check evaluates) cannot re-trigger
                    # every interval_s * flip_consecutive seconds. The
                    # streak is left standing: if the scene is genuinely
                    # transitioning it will still agree once the cooldown
                    # clears; if it was only oscillating off our own last
                    # action, the next reading (made against an exposure we
                    # did not just change) will most likely disagree and
                    # reset the streak below instead.
                    logger.info(
                        "exposure auto-lock: holding a confirmed flip to night=%s - "
                        "%.1fs into a %.1fs post-action cooldown (self-oscillation guard)",
                        night,
                        dwell_elapsed,
                        self._min_dwell_s,
                    )
                else:
                    if night:
                        applied = self._lock()
                        action = "lock"
                    else:
                        applied = self._restore()
                        action = "restore"
                    if applied:
                        self._locked = night
                        self._last_action_monotonic = now_monotonic
                        # A fresh lock/restore starts the next dwell at the
                        # base value - any earlier clip trim from a prior
                        # night belongs to a scene state that no longer
                        # applies (see class docstring's "near-field clip
                        # trim" section on why trims don't persist).
                        self._current_exposure = self._base_exposure
                    self._streak_answer = None
                    self._streak_count = 0
                    logger.info(
                        "exposure auto-lock: %s (median saturation=%s, median brightness=%s, "
                        "brightness_override=%s, applied=%s)",
                        action,
                        median_saturation,
                        median_brightness,
                        brightness_override,
                        applied,
                    )

        return ExposureDecision(
            wall_s=self._clock(),
            saturations=saturations,
            median_saturation=median_saturation,
            night=night,
            action=action,
            applied=applied,
            brightnesses=brightnesses,
            median_brightness=median_brightness,
            brightness_override=brightness_override,
            clip_fractions=clip_fractions,
            median_clip_fraction=median_clip_fraction,
            exposure_value=self._current_exposure if self._locked else None,
            trim_applied=trim_applied,
        )
