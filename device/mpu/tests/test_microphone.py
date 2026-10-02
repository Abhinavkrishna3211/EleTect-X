"""Capture, measurement and health gating in perception.microphone."""

from __future__ import annotations

import array
import math

import pytest

from perception.microphone import (
    AudioClip,
    Microphone,
    MicrophoneError,
    assess_health,
    discover_capture_device,
)

# Health floors used throughout. Deliberately not imported from
# services.config: these tests assert the gate's *logic*, and pinning them
# here means a future recalibration of the real floors cannot quietly turn
# a passing assertion into a vacuous one.
FLOORS = {"min_rms": 0.001, "max_clipped_fraction": 0.01, "max_dc_offset": 0.05}


def _pcm(samples: list[int]) -> bytes:
    """Little-endian S16 bytes, the way arecord would hand them over."""
    buf = array.array("h", samples)
    return buf.tobytes()


def _tone(count: int, amplitude: int, *, offset: int = 0) -> list[int]:
    """A sine at an arbitrary period, offset by a DC bias if asked."""
    return [
        int(amplitude * math.sin(2 * math.pi * i / 64)) + offset for i in range(count)
    ]


def _runner_returning(payload: bytes, seen: list | None = None):
    def run(argv: list[str], timeout_s: float) -> bytes:
        if seen is not None:
            seen.append((argv, timeout_s))
        return payload

    return run


def _clip(samples: list[int], **kwargs) -> AudioClip:
    """Build a clip directly, bypassing capture, for health-gate tests."""
    defaults = {
        "sample_rate": 8000,
        "device": "plughw:1,0",
        "rms": 0.1,
        "peak": 0.2,
        "clipped_fraction": 0.0,
        "dc_offset": 0.0,
    }
    defaults.update(kwargs)
    return AudioClip(samples=array.array("h", samples), **defaults)


# --------------------------------------------------------------------------
# capture()
# --------------------------------------------------------------------------


def test_capture_requests_the_impulses_own_rate_and_format() -> None:
    """The arecord invocation is part of the contract, not an internal detail.

    8 kHz mono S16_LE is what the deployed impulse declares, and the 4x
    upsample to the PANNs front end happens inside the DSP block. A drift
    in any of these three values breaks inference rather than merely
    degrading it, and 32000 in particular would look plausible while
    putting every frequency in the wrong mel bin.
    """
    seen: list = []
    mic = Microphone(
        "plughw:1,0",
        warmup_s=0,
        runner=_runner_returning(_pcm(_tone(8000, 8000)), seen),
    )
    mic.capture(1.0)

    argv, timeout_s = seen[0]
    assert argv[0] == "arecord"
    assert argv[argv.index("-D") + 1] == "plughw:1,0"
    assert argv[argv.index("-f") + 1] == "S16_LE"
    assert argv[argv.index("-c") + 1] == "1"
    assert argv[argv.index("-r") + 1] == "8000"
    assert argv[argv.index("-t") + 1] == "raw"
    # The timeout must exceed the recording itself or every healthy
    # capture would time out on its own drain.
    assert timeout_s > 1.0


def test_capture_measures_rms_peak_and_clipping() -> None:
    """Every clip carries its own levels, because the health gate needs them.

    audioop was removed in Python 3.13, so this maths is hand-rolled over
    array.array and is worth pinning against a signal whose RMS and peak
    are known analytically.
    """
    # 1024 samples is 16 whole periods of _tone's 64-sample cycle. A count
    # that cuts the sine mid-cycle leaves a real DC residue and the offset
    # assertion below stops measuring what it is named for.
    mic = Microphone(
        "plughw:1,0", warmup_s=0, runner=_runner_returning(_pcm(_tone(1024, 16384)))
    )
    clip = mic.capture(0.128)

    assert clip.sample_rate == 8000
    assert clip.duration_s == pytest.approx(0.128, abs=1e-6)
    # A full-period sine of amplitude A has RMS A/sqrt(2).
    assert clip.rms == pytest.approx(16384 / math.sqrt(2) / 32768, rel=0.02)
    assert clip.peak == pytest.approx(16384 / 32768, rel=0.02)
    assert clip.clipped_fraction == 0.0
    assert clip.dc_offset == pytest.approx(0.0, abs=1e-3)


def test_capture_reports_a_dc_offset() -> None:
    """A bias fault inflates RMS, so it has to be measured separately."""
    mic = Microphone(
        "plughw:1,0",
        warmup_s=0,
        runner=_runner_returning(_pcm(_tone(1024, 1000, offset=8000))),
    )
    clip = mic.capture(0.128)
    assert clip.dc_offset == pytest.approx(8000 / 32768, rel=0.02)


def test_capture_counts_clipped_samples() -> None:
    """Clipping is counted as a fraction, not flagged on a single peak."""
    samples = [32767] * 100 + [0] * 900
    mic = Microphone("plughw:1,0", warmup_s=0, runner=_runner_returning(_pcm(samples)))
    clip = mic.capture(1000 / 8000)
    assert clip.clipped_fraction == pytest.approx(0.1)


def test_capture_rejects_an_odd_byte_count() -> None:
    """A truncated final sample means the capture was cut mid-frame."""
    mic = Microphone("plughw:1,0", runner=_runner_returning(b"\x01\x02\x03"))
    with pytest.raises(MicrophoneError, match="whole number of 16-bit"):
        mic.capture(1.0)


def test_capture_rejects_a_short_read() -> None:
    """Far less audio than asked for is a device fault, not a short buffer.

    A microphone unplugged mid-record, or a PCM stolen by another process,
    returns a partial buffer with a zero exit status - so the byte count is
    the only signal that anything went wrong.
    """
    mic = Microphone("plughw:1,0", warmup_s=0, runner=_runner_returning(_pcm([0] * 100)))
    with pytest.raises(MicrophoneError, match="short capture"):
        mic.capture(1.0)


def test_capture_rejects_a_non_positive_duration() -> None:
    """Caught here rather than passed to arecord, which would hang."""
    mic = Microphone("plughw:1,0", runner=_runner_returning(b""))
    with pytest.raises(MicrophoneError, match="must be positive"):
        mic.capture(0.0)


def test_capture_propagates_a_runner_failure() -> None:
    """Capture raises; it is the orchestrator's job to absorb it, not this one's."""

    def boom(argv: list[str], timeout_s: float) -> bytes:
        raise MicrophoneError("arecord exited 1: No such file or directory")

    mic = Microphone("plughw:9,0", runner=boom)
    with pytest.raises(MicrophoneError, match="No such file"):
        mic.capture(1.0)


# --------------------------------------------------------------------------
# assess_health() - the dead-LR44 gate
# --------------------------------------------------------------------------


def test_health_passes_a_normal_clip() -> None:
    """The gate has to let ordinary audio through, or it gates everything."""
    health = assess_health(_clip([0] * 10, rms=0.05), **FLOORS)
    assert health.ok
    assert health.reason is None


def test_health_rejects_near_silence() -> None:
    """The BY-M1's dead-cell failure mode: well-formed frames, no signal."""
    health = assess_health(_clip([0] * 10, rms=0.00001), **FLOORS)
    assert not health.ok
    assert "silent" in health.reason
    # The reason text is the operator's only clue about which physical
    # thing to go and check, so it names the parts rather than the number.
    assert "LR44" in health.reason


def test_health_rejects_clipping() -> None:
    """A badly set capture gain on the USB adapter, not a loud event."""
    health = assess_health(_clip([0] * 10, rms=0.4, clipped_fraction=0.2), **FLOORS)
    assert not health.ok
    assert "clipped" in health.reason


def test_health_checks_dc_offset_before_the_silence_floor() -> None:
    """Ordering is load-bearing, not cosmetic.

    A DC offset raises RMS. A dead microphone with a bias fault therefore
    passes a naive level check while carrying no signal at all, so the
    offset test has to run first or the silence floor can be masked by the
    very fault it would otherwise catch.
    """
    health = assess_health(
        _clip([0] * 10, rms=0.00001, dc_offset=0.5),
        **FLOORS,
    )
    assert not health.ok
    assert "DC offset" in health.reason
    assert "silent" not in health.reason


# --------------------------------------------------------------------------
# discover_capture_device()
# --------------------------------------------------------------------------

_LISTING = b"""**** List of CAPTURE Hardware Devices ****
card 0: SM8250 [SM8250-MTP], device 0: Primary MI2S [Primary MI2S]
  Subdevices: 1/1
card 1: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
"""


def test_discover_picks_the_usb_card_not_the_on_die_codec() -> None:
    """Card index is looked up by name because enumeration order drifts.

    A hardcoded plughw:1,0 works until the hub enumerates differently after
    a reboot, at which point the system records silence from an on-die
    codec and never says why.
    """
    device = discover_capture_device(runner=_runner_returning(_LISTING))
    assert device == "plughw:1,0"


def test_discover_raises_when_only_on_die_codecs_are_present() -> None:
    """Better to fail loudly at startup than to record from the wrong card."""
    listing = b"card 0: SM8250 [SM8250-MTP], device 0: Primary MI2S [Primary MI2S]\n"
    with pytest.raises(MicrophoneError, match="no USB capture device"):
        discover_capture_device(runner=_runner_returning(listing))


def test_discover_raises_when_nothing_is_listed() -> None:
    """An empty listing means no sound card at all, which is its own message."""
    with pytest.raises(MicrophoneError, match="no capture devices"):
        discover_capture_device(runner=_runner_returning(b"\n"))


# --- warm-up discard -------------------------------------------------------
#
# Measured on the board 30 Sept 2026: every fresh arecord open produces a
# decaying transient whose first second hard-clips at full scale and carries
# a DC offset of -0.117, settling by 4 s. Because capture() opens a new
# arecord per call, it is paid on every capture, not once at startup. See
# Microphone.WARMUP_S for the measurement table.


def test_capture_records_the_warmup_on_top_of_the_window() -> None:
    """The recorder must be asked for warm-up + window, not just the window.

    If the warm-up were taken out of the requested duration instead of added
    to it, the caller would silently get a shorter clip than it asked for -
    and for a 10 s impulse window that is a feature-count mismatch, which
    POST /api/features rejects outright rather than degrades.
    """
    seen: list = []
    mic = Microphone(
        "plughw:1,0",
        warmup_s=4.0,
        runner=_runner_returning(_pcm([0] * (8000 * 14)), seen),
    )
    mic.capture(10.0)

    argv, timeout_s = seen[0]
    assert argv[argv.index("-d") + 1] == "14"
    # The timeout has to cover the warm-up too, or every healthy capture of
    # a full window would trip it.
    assert timeout_s > 14.0


def test_capture_returns_only_the_settled_samples() -> None:
    """The discarded head must not reach the caller."""
    warmup = [32767] * (8000 * 4)
    wanted = [1000] * (8000 * 2)
    mic = Microphone(
        "plughw:1,0", warmup_s=4.0, runner=_runner_returning(_pcm(warmup + wanted))
    )
    clip = mic.capture(2.0)

    assert len(clip.samples) == 8000 * 2
    assert clip.duration_s == pytest.approx(2.0, abs=1e-6)
    assert set(clip.samples) == {1000}


def test_warmup_is_discarded_before_levels_are_measured() -> None:
    """The health gate must describe the settled stream, not the transient.

    This is the whole point of doing the discard inside capture(): a clip
    whose first seconds clip at full scale and sit at DC -0.117 passes the
    averaged gate, so measuring first and trimming later would keep the
    fault invisible exactly where it matters.
    """
    warmup = [32767] * (8000 * 4)
    wanted = [0] * (8000 * 2)
    mic = Microphone(
        "plughw:1,0", warmup_s=4.0, runner=_runner_returning(_pcm(warmup + wanted))
    )
    clip = mic.capture(2.0)

    assert clip.peak == 0.0
    assert clip.rms == 0.0
    assert clip.clipped_fraction == 0.0
    assert clip.dc_offset == pytest.approx(0.0, abs=1e-9)


def test_capture_rejects_a_read_shorter_than_the_warmup() -> None:
    """Nothing survives the discard, which is a fault, not an empty clip."""
    mic = Microphone(
        "plughw:1,0", warmup_s=4.0, runner=_runner_returning(_pcm([0] * 100))
    )
    with pytest.raises(MicrophoneError, match="warm-up"):
        mic.capture(2.0)


def test_warmup_can_be_disabled_for_bench_characterisation() -> None:
    """warmup_s=0 hands back the transient, which is what mic_check wants."""
    mic = Microphone(
        "plughw:1,0", warmup_s=0, runner=_runner_returning(_pcm([32767] * 8000))
    )
    clip = mic.capture(1.0)
    assert clip.peak == pytest.approx(32767 / 32768, rel=1e-6)


def test_negative_warmup_is_rejected() -> None:
    """A negative warm-up would slice from the tail instead of the head."""
    with pytest.raises(MicrophoneError, match="warmup_s"):
        Microphone("plughw:1,0", warmup_s=-1.0)
