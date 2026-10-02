"""Tests for perception/night.py's ExposureAutoLock - the periodic lock/restore policy.

Entirely in terms of fake is_night/lock/restore callables and an injected
monotonic clock - no cv2, no camera, no real HSV maths. frame_mean_saturation()
and frames_are_night() already have their own coverage against real-shaped
data; what needs proving here is the policy wrapped around an injected
is_night: rate limiting, hysteresis, the kill switch, and the
never-raises contract.
"""

import types

import pytest

from perception import night as night_mod
from perception.night import ExposureAutoLock
from services import config


def _frames(n=3):
    """Build n Frame-like stand-ins; only .image is read, and only by frame_mean_brightness."""
    return [types.SimpleNamespace(image=object()) for _ in range(n)]


@pytest.fixture
def brightness(monkeypatch):
    """Force frame_mean_brightness() to a scripted value (or None) without cv2."""

    def _set(value):
        monkeypatch.setattr(night_mod, "frame_mean_brightness", lambda _img: value)

    return _set


@pytest.fixture
def clip_fraction(monkeypatch):
    """Force frame_clip_fraction() to a scripted value (or None) without cv2."""

    def _set(value):
        monkeypatch.setattr(night_mod, "frame_clip_fraction", lambda _img, _clip_value: value)

    return _set


class _Clock:
    """A monotonic/wall clock a test can advance by hand."""

    def __init__(self, start=0.0):
        self.value = start

    def __call__(self):
        return self.value

    def advance(self, seconds):
        """Move the clock forward by `seconds`."""
        self.value += seconds


class _Recorder:
    """A lock/restore fake that counts calls and returns a scripted result."""

    def __init__(self, result=True):
        self.result = result
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.result


class _ValueRecorder:
    """A lock_at fake that records each requested value and returns a scripted result."""

    def __init__(self, result=True):
        self.result = result
        self.calls = 0
        self.values: list[int] = []

    def __call__(self, value):
        self.calls += 1
        self.values.append(value)
        return self.result


def _is_night_const(answer):
    """An is_night fake that always returns `answer`, regardless of images."""

    def _fn(images):
        return answer

    return _fn


def _policy(is_night_answer=None, is_night_fn=None, monotonic=None, **kwargs):
    """An ExposureAutoLock wired to fresh lock/restore recorders and an injected clock.

    min_dwell_s defaults to 0.0 (disabled) so every test that is not
    specifically about the dwell cooldown can keep exercising interval_s /
    flip_consecutive / brightness-override behaviour in isolation, exactly
    as it did before that knob existed. Tests for the dwell guard itself
    pass min_dwell_s explicitly.
    """
    lock = kwargs.pop("lock", None) or _Recorder(True)
    restore = kwargs.pop("restore", None) or _Recorder(True)
    is_night = is_night_fn if is_night_fn is not None else _is_night_const(is_night_answer)
    clock = monotonic if monotonic is not None else _Clock()
    kwargs.setdefault("min_dwell_s", 0.0)
    policy = ExposureAutoLock(
        is_night=is_night,
        lock=lock,
        restore=restore,
        monotonic=clock,
        clock=clock,
        **kwargs,
    )
    return policy, lock, restore, clock


@pytest.fixture(autouse=True)
def _kill_switch_on(monkeypatch):
    """Default every test to the kill switch's normal on state; individual tests flip it."""
    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", True)


# ---------------------------------------------------------------------------
# rate limiting
# ---------------------------------------------------------------------------


def test_first_call_always_evaluates():
    """The very first maybe_update() call has nothing to rate-limit against."""
    policy, lock, restore, clock = _policy(is_night_answer=False, flip_consecutive=1)

    decision = policy.maybe_update([])

    assert decision is not None
    assert decision.night is False


def test_a_second_call_before_interval_s_elapses_returns_none_and_skips_is_night():
    """Returns None, and does not even call is_night, if interval_s has not passed."""
    calls = []

    def _counting_is_night(images):
        calls.append(images)
        return False

    policy, lock, restore, clock = _policy(
        is_night_fn=_counting_is_night, interval_s=30.0, flip_consecutive=1
    )
    policy.maybe_update([])
    clock.advance(10.0)

    decision = policy.maybe_update([])

    assert decision is None
    assert len(calls) == 1  # only the first call reached is_night


def test_a_call_at_or_past_interval_s_evaluates_again():
    """Once interval_s has elapsed, the next call re-evaluates."""
    policy, lock, restore, clock = _policy(
        is_night_answer=False, interval_s=30.0, flip_consecutive=1
    )
    policy.maybe_update([])
    clock.advance(30.0)

    decision = policy.maybe_update([])

    assert decision is not None


# ---------------------------------------------------------------------------
# hysteresis
# ---------------------------------------------------------------------------


def test_locks_on_confirmed_night_after_flip_consecutive_agreeing_reads():
    """A single night reading does not lock; flip_consecutive agreeing reads do."""
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=2
    )

    first = policy.maybe_update([])
    assert first.action == "hold"
    assert lock.calls == 0
    assert policy.locked is False

    clock.advance(1.0)
    second = policy.maybe_update([])

    assert second.action == "lock"
    assert lock.calls == 1
    assert policy.locked is True


def test_restores_on_confirmed_day_after_flip_consecutive_agreeing_reads():
    """Symmetric case: starting locked, flip_consecutive day reads triggers restore()."""
    answer = [True]  # mutable so the test can flip what is_night reports mid-run
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: answer[0], interval_s=1.0, flip_consecutive=1
    )
    policy.maybe_update([])  # locks immediately (flip_consecutive=1)
    assert policy.locked is True

    # Now the scene reads day, still with flip_consecutive=1.
    answer[0] = False
    clock.advance(1.0)
    decision = policy.maybe_update([])

    assert decision.action == "restore"
    assert restore.calls == 1
    assert policy.locked is False


def test_a_single_dissenting_reading_does_not_flip_state():
    """One disagreeing read among agreeing ones must not reset the debounce silently.

    Sets flip_consecutive=2, feeds night, night, day, night, night - the
    lone "day" between two "night" streaks must not let a stray reading
    contribute toward a later streak it did not participate in.
    """
    answers = iter([True, True, False, True, True])
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: next(answers), interval_s=1.0, flip_consecutive=2
    )

    results = []
    for _ in range(5):
        results.append(policy.maybe_update([]).action)
        clock.advance(1.0)

    # Second "True" locks (streak of 2). The lone "False" holds (streak
    # reset to 0, no restore since flip_consecutive=2 was not met by one
    # reading). The next two "True"s do not re-lock (already locked to
    # night; night == locked from the start, so they hold too - a
    # dissenting single reading did not carry over from the earlier streak).
    assert results == ["hold", "lock", "hold", "hold", "hold"]
    assert lock.calls == 1
    assert restore.calls == 0


def test_never_reissues_the_same_direction_twice():
    """Once locked, further confirmed-night reads must not call lock() again."""
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )

    for _ in range(4):
        policy.maybe_update([])
        clock.advance(1.0)

    assert lock.calls == 1
    assert restore.calls == 0


def test_a_failed_lock_does_not_update_the_locked_belief():
    """Locked must reflect a verified apply, not just an attempted one - lock() returning False."""
    policy, lock, restore, clock = _policy(
        is_night_answer=True, lock=_Recorder(False), interval_s=1.0, flip_consecutive=1
    )

    decision = policy.maybe_update([])

    assert decision.action == "lock"
    assert decision.applied is False
    assert lock.calls == 1
    assert policy.locked is False, "an unverified lock must not be believed"


def test_a_failed_restore_does_not_update_the_locked_belief():
    """Symmetric case: restore() returning False must leave the policy believing it is locked."""
    policy, lock, restore, clock = _policy(
        is_night_answer=False, restore=_Recorder(False), interval_s=1.0, flip_consecutive=1
    )
    policy.note_external_lock(True)
    assert policy.locked is True

    decision = policy.maybe_update([])

    assert decision.action == "restore"
    assert decision.applied is False
    assert restore.calls == 1
    assert policy.locked is True, "an unverified restore must not be believed either"


# ---------------------------------------------------------------------------
# brightness override (the dawn blind spot on the IR camera)
# ---------------------------------------------------------------------------


def test_brightness_override_flips_confirmed_night_to_day_and_restores(brightness):
    """is_night says night, but a daylit-level brightness forces day and restores."""
    brightness(config.NIGHT_BRIGHTNESS_DAY_THRESHOLD + 10.0)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )
    policy.note_external_lock(True)
    assert policy.locked is True

    decision = policy.maybe_update(_frames())

    assert decision.action == "restore"
    assert decision.night is False
    assert decision.brightness_override is True
    assert restore.calls == 1
    assert policy.locked is False


def test_brightness_just_below_threshold_does_not_override(brightness):
    """A frame dimmer than the threshold leaves the night answer untouched."""
    brightness(config.NIGHT_BRIGHTNESS_DAY_THRESHOLD - 1.0)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )
    policy.note_external_lock(True)

    decision = policy.maybe_update(_frames())

    assert decision.action == "hold"
    assert decision.night is True
    assert decision.brightness_override is False
    assert restore.calls == 0
    assert policy.locked is True


def test_brightness_override_still_respects_flip_consecutive(brightness):
    """One bright reading does not release the lock; flip_consecutive of them do."""
    brightness(config.NIGHT_BRIGHTNESS_DAY_THRESHOLD + 25.0)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=2
    )
    policy.note_external_lock(True)

    first = policy.maybe_update(_frames())
    assert first.action == "hold"
    assert restore.calls == 0

    clock.advance(1.0)
    second = policy.maybe_update(_frames())

    assert second.action == "restore"
    assert restore.calls == 1
    assert policy.locked is False


def test_brightness_override_never_imposes_a_lock(brightness):
    """Not locked + is_night night + bright frame: forced to day, so no lock() call."""
    brightness(config.NIGHT_BRIGHTNESS_DAY_THRESHOLD + 50.0)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )

    for _ in range(3):
        policy.maybe_update(_frames())
        clock.advance(1.0)

    assert lock.calls == 0
    assert policy.locked is False


def test_unmeasurable_brightness_does_not_override(brightness):
    """When every frame's brightness reads None the night answer stands."""
    brightness(None)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )
    policy.note_external_lock(True)

    decision = policy.maybe_update(_frames())

    assert decision.action == "hold"
    assert decision.night is True
    assert decision.brightness_override is False
    assert decision.median_brightness is None


def test_decision_carries_brightness_readings(brightness):
    """Every ExposureDecision reports the brightness readings that fed it."""
    brightness(120.0)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )

    decision = policy.maybe_update(_frames(n=3))

    assert decision.brightnesses == [120.0, 120.0, 120.0]
    assert decision.median_brightness == 120.0
    assert decision.brightness_override is False


# ---------------------------------------------------------------------------
# kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_forces_one_restore_and_then_holds(monkeypatch):
    """Disabled: issues restore() exactly once, then holds regardless of frame content."""
    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", False)
    policy, lock, restore, clock = _policy(is_night_answer=True, interval_s=1.0)

    first = policy.maybe_update([])
    assert first.action == "restore"
    assert first.night is None
    assert restore.calls == 1

    clock.advance(1.0)
    second = policy.maybe_update([])

    assert second.action == "hold"
    assert restore.calls == 1  # not re-issued
    assert lock.calls == 0


def test_kill_switch_never_locks_no_matter_what_the_frames_say(monkeypatch):
    """A confirmed-night burst still never locks while the kill switch is off."""
    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", False)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )

    for _ in range(3):
        policy.maybe_update([])
        clock.advance(1.0)

    assert lock.calls == 0


def test_re_enabling_the_kill_switch_resumes_normal_evaluation(monkeypatch):
    """Once the switch is back on, the policy evaluates and can lock again."""
    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", False)
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )
    policy.maybe_update([])
    clock.advance(1.0)

    monkeypatch.setattr(config, "NIGHT_EXPOSURE_LOCK_ENABLED", True)
    decision = policy.maybe_update([])

    assert decision.action == "lock"
    assert lock.calls == 1


# ---------------------------------------------------------------------------
# never raises
# ---------------------------------------------------------------------------


def test_an_is_night_exception_is_swallowed_and_leaves_state_unchanged():
    """A raising is_night() never propagates and never flips locked state."""

    def _raising(images):
        raise RuntimeError("frame decode blew up")

    policy, lock, restore, clock = _policy(is_night_fn=_raising, interval_s=1.0)

    decision = policy.maybe_update([])

    assert decision.action == "hold"
    assert decision.night is None
    assert policy.locked is False
    assert lock.calls == 0
    assert restore.calls == 0


def test_none_from_is_night_does_not_flip_state():
    """An unmeasurable burst (None) is treated like an unmeasured pixel batch - it holds."""
    policy, lock, restore, clock = _policy(
        is_night_answer=None, interval_s=1.0, flip_consecutive=1
    )

    decision = policy.maybe_update([])

    assert decision.action == "hold"
    assert decision.night is None
    assert policy.locked is False
    assert lock.calls == 0
    assert restore.calls == 0


# ---------------------------------------------------------------------------
# note_external_lock()
# ---------------------------------------------------------------------------


def test_note_external_lock_true_marks_locked_and_resets_the_streak():
    """A verified on-demand lock updates belief state so a later day read can restore."""
    policy, lock, restore, clock = _policy(
        is_night_answer=False, interval_s=1.0, flip_consecutive=1
    )

    policy.note_external_lock(True)

    assert policy.locked is True

    decision = policy.maybe_update([])
    assert decision.action == "restore"
    assert restore.calls == 1


def test_note_external_lock_false_does_not_change_belief_state():
    """A failed on-demand lock must not make the policy believe it is locked."""
    policy, lock, restore, clock = _policy(is_night_answer=True, interval_s=1.0)

    policy.note_external_lock(False)

    assert policy.locked is False


# ---------------------------------------------------------------------------
# min_dwell_s (self-sustaining oscillation guard, found live 11 Sept 2026)
# ---------------------------------------------------------------------------


def test_min_dwell_s_withholds_a_confirmed_flip_right_after_the_last_action():
    """A confirmed opposite flip within min_dwell_s of the last action holds instead."""
    answer = [True]
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: answer[0],
        interval_s=1.0,
        flip_consecutive=1,
        min_dwell_s=10.0,
    )
    policy.maybe_update([])  # locks immediately (flip_consecutive=1)
    assert policy.locked is True
    assert lock.calls == 1

    # Scene reads day right away - as it would if locking itself flipped
    # the signal - but only 1s after the lock, well inside min_dwell_s=10.
    answer[0] = False
    clock.advance(1.0)
    decision = policy.maybe_update([])

    assert decision.action == "hold"
    assert restore.calls == 0
    assert policy.locked is True, "withheld flip must not change belief state"


def test_min_dwell_s_allows_the_flip_once_the_cooldown_elapses():
    """The same confirmed flip goes through once min_dwell_s has actually passed."""
    answer = [True]
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: answer[0],
        interval_s=1.0,
        flip_consecutive=1,
        min_dwell_s=10.0,
    )
    policy.maybe_update([])  # locks immediately
    answer[0] = False
    clock.advance(1.0)
    policy.maybe_update([])  # held - only 1s into the cooldown
    assert restore.calls == 0

    clock.advance(10.0)  # now 11s past the lock - past min_dwell_s
    decision = policy.maybe_update([])

    assert decision.action == "restore"
    assert restore.calls == 1
    assert policy.locked is False


def test_min_dwell_s_breaks_a_self_sustaining_oscillation():
    """The exact bug found live: each action flips the reading the next check evaluates.

    Lock makes it read day, restore makes it read night, repeating every
    interval_s * flip_consecutive - min_dwell_s must stop the cycle from
    ever completing a second action.
    """
    answers = iter([True, False, True, False, True, False, True, False])
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: next(answers),
        interval_s=30.0,
        flip_consecutive=1,
        min_dwell_s=300.0,
    )

    for _ in range(8):
        policy.maybe_update([])
        clock.advance(30.0)

    # Only the very first reading (no prior action to be within cooldown of)
    # is ever allowed to act; every alternation after it is withheld.
    assert lock.calls == 1
    assert restore.calls == 0


def test_min_dwell_s_does_not_delay_the_very_first_action():
    """With no prior action, min_dwell_s has nothing to measure from and never blocks it."""
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1, min_dwell_s=9999.0
    )

    decision = policy.maybe_update([])

    assert decision.action == "lock"
    assert lock.calls == 1


def test_note_external_lock_starts_the_dwell_cooldown():
    """An on-demand external lock also counts as an action for min_dwell_s purposes."""
    policy, lock, restore, clock = _policy(
        is_night_answer=False, interval_s=1.0, flip_consecutive=1, min_dwell_s=10.0
    )

    policy.note_external_lock(True)
    clock.advance(1.0)
    decision = policy.maybe_update([])

    assert decision.action == "hold", "the external lock should start the same cooldown"
    assert restore.calls == 0
    assert policy.locked is True


# ---------------------------------------------------------------------------
# near-field clip trim
# ---------------------------------------------------------------------------


def test_clip_trim_disabled_without_lock_at(clip_fraction):
    """No lock_at supplied (the default) must skip the trim check entirely, whatever clips."""
    policy, lock, restore, clock = _policy(
        is_night_answer=True, interval_s=1.0, flip_consecutive=1
    )
    policy.maybe_update([])  # locks
    assert policy.locked is True

    clip_fraction(0.99)  # would clearly be over any real threshold
    clock.advance(1.0)
    decision = policy.maybe_update([])

    assert decision.trim_applied is False
    assert decision.median_clip_fraction is None
    assert decision.exposure_value == config.NIGHT_LOCKED_EXPOSURE


def test_clip_trim_steps_down_when_locked_and_over_threshold(clip_fraction):
    """A confirmed-clipping reading while locked to night steps the exposure down once."""
    lock_at = _ValueRecorder(True)
    policy, lock, restore, clock = _policy(
        is_night_answer=True,
        lock_at=lock_at,
        clip_fraction_threshold=0.02,
        exposure_trim_step=32,
        interval_s=1.0,
        flip_consecutive=1,
    )
    policy.maybe_update([])  # locks at the base value
    assert policy.locked is True

    clip_fraction(0.05)  # over the 0.02 threshold
    clock.advance(1.0)
    decision = policy.maybe_update(_frames())

    assert decision.trim_applied is True
    assert decision.median_clip_fraction == 0.05
    assert lock_at.calls == 1
    assert decision.exposure_value == config.NIGHT_LOCKED_EXPOSURE - 32


def test_clip_trim_does_not_trigger_below_threshold(clip_fraction):
    """A clip reading under threshold must hold the locked exposure unchanged."""
    lock_at = _ValueRecorder(True)
    policy, lock, restore, clock = _policy(
        is_night_answer=True,
        lock_at=lock_at,
        clip_fraction_threshold=0.02,
        interval_s=1.0,
        flip_consecutive=1,
    )
    policy.maybe_update([])
    assert policy.locked is True

    clip_fraction(0.01)  # under the 0.02 threshold
    clock.advance(1.0)
    decision = policy.maybe_update([])

    assert decision.trim_applied is False
    assert lock_at.calls == 0
    assert decision.exposure_value == config.NIGHT_LOCKED_EXPOSURE


def test_clip_trim_floors_and_stops(clip_fraction):
    """Repeated clipping ratchets the exposure down but never below exposure_floor."""
    lock_at = _ValueRecorder(True)
    policy, lock, restore, clock = _policy(
        is_night_answer=True,
        lock_at=lock_at,
        base_exposure=256,
        clip_fraction_threshold=0.02,
        exposure_trim_step=100,
        exposure_floor=128,
        interval_s=1.0,
        flip_consecutive=1,
    )
    policy.maybe_update([])  # locks at 256
    clip_fraction(0.5)

    clock.advance(1.0)
    first = policy.maybe_update(_frames())  # 256 -> 156
    clock.advance(1.0)
    second = policy.maybe_update(_frames())  # 156 -> floored at 128
    clock.advance(1.0)
    third = policy.maybe_update(_frames())  # already at floor, no further attempt

    assert first.exposure_value == 156
    assert second.exposure_value == 128
    assert third.trim_applied is False
    assert third.exposure_value == 128
    assert lock_at.calls == 2, "no trim attempt once the floor is reached"


def test_clip_trim_resets_on_the_next_fresh_lock(clip_fraction):
    """A trim from one night dwell must not carry over into the next lock cycle."""
    answer = [True]
    lock_at = _ValueRecorder(True)
    policy, lock, restore, clock = _policy(
        is_night_fn=lambda images: answer[0],
        lock_at=lock_at,
        base_exposure=256,
        clip_fraction_threshold=0.02,
        exposure_trim_step=32,
        interval_s=1.0,
        flip_consecutive=1,
    )
    policy.maybe_update([])  # locks at 256
    clip_fraction(0.5)
    clock.advance(1.0)
    trimmed = policy.maybe_update(_frames())
    assert trimmed.exposure_value == 224

    # Day, then night again - a fresh lock cycle.
    clip_fraction(None)
    answer[0] = False
    clock.advance(1.0)
    policy.maybe_update([])  # restores
    answer[0] = True
    clock.advance(1.0)
    relocked = policy.maybe_update([])

    assert relocked.action == "lock"
    assert relocked.exposure_value == 256, "a fresh lock must start back at the base value"


def test_a_failed_trim_does_not_change_the_believed_exposure(clip_fraction):
    """lock_at() returning False must leave the policy's tracked exposure unchanged."""
    lock_at = _ValueRecorder(False)
    policy, lock, restore, clock = _policy(
        is_night_answer=True,
        lock_at=lock_at,
        clip_fraction_threshold=0.02,
        interval_s=1.0,
        flip_consecutive=1,
    )
    policy.maybe_update([])
    clip_fraction(0.5)
    clock.advance(1.0)

    decision = policy.maybe_update(_frames())

    assert decision.trim_applied is False
    assert lock_at.calls == 1
    assert decision.exposure_value == config.NIGHT_LOCKED_EXPOSURE
