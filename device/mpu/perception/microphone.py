"""USB microphone capture for the acoustic modality.

Capture only. No classification happens here - the same split
perception/camera.py keeps against perception/detector.py, and for the same
reason: the trained artifact runs out-of-process behind an HTTP server
(perception/acoustic_detector.py), so mixing the two in one module would
make the capture path untestable without a model on the box.

Why a USB microphone at all
---------------------------
The original plan (ADR 0009) put a digital MEMS mic on the STM32's SAI
peripheral so the MCU could listen continuously in its low-power domain.
That is not reachable on this board with the stock platform: the Arduino
core for the UNO Q ships a *prebuilt* Zephyr loader and the sketch is an
LLEXT object dynamically loaded into it, so the devicetree - and therefore
which peripherals exist at all - is fixed at loader build time and a sketch
cannot add SAI to it. Rebuilding the loader is possible but replaces the
stock platform wholesale, and SAI sits outside the SmartRun low-power
domain anyway, so it could never have delivered the always-on listening
that was the entire reason to prefer it. See ADR 0028 for the full
argument. An always-on gunshot detector remains ADR 0009's analog ->
ADC4 -> LPBAM path and is deliberately still unbuilt.

What that leaves is event-gated capture on the Linux side, which is what
this module does: the seismic trigger (or a scheduled sweep) asks for a few
seconds of audio, and the clip is classified once. It costs USB power while
recording rather than microwatts continuously, which is the honest trade.

Transport
---------
`arecord` via subprocess, not a Python audio binding. The board's Python
3.13.5 image has no pip and no ensurepip and there is no sudo credential to
install either (perception/detector.py documents the same constraint for
the inference side), so sounddevice/pyaudio are not available and will not
become available. `arecord` is part of alsa-utils and is already present on
the image. `audioop`, which would have been the obvious stdlib way to get
an RMS out of the captured frames, was **removed in Python 3.13** - the
level maths below is done over `array.array` by hand for that reason, not
out of preference.

Sample rate is pinned to 8000 Hz, which is what the trained impulse takes
(EI_CLASSIFIER_FREQUENCY 8000, RAW_SAMPLE_COUNT 80000) because the corpus
is 8 kHz throughout. That is deliberately *not* the rate the front end runs
at: PANNs' filterbank is defined at 32 kHz (n_fft 1024, hop 320, 64 Slaney
mel bins, 50 Hz - 14 kHz), so a 4x upsample happens inside the DSP block on
both paths - librosa during training, the C++ port on-device. Capturing at
32 kHz here would not skip that upsample, it would feed it a signal already
four times too fast and put every frequency in the wrong mel bin, which a
PANNs backbone reports as confident wrong labels rather than as an error.
The device string uses `plughw:` rather than `hw:` deliberately: most USB
audio class codecs only advertise 44100/48000, and plughw is what makes
ALSA do the rate conversion in-kernel so we never need to do it in Python.

Health
------
The field mic is a BOYA BY-M1, an electret lavalier powered by a single
LR44 cell. When that cell dies the microphone does not fail loudly - it
keeps enumerating as a USB capture device and keeps returning frames, they
are just near-silent. Feeding that to the classifier produces confident
`ambient` forever, which is indistinguishable from a quiet forest. So every
clip is measured and `assess_health()` is the gate: a clip that fails it
must be reported to fusion as ACOUSTIC *unavailable*, never classified. A
modality that is broken has to say so; one that silently says "nothing
here" is worse than one that is absent, because fusion can drop an absent
modality and cannot drop a lying one.
"""

from __future__ import annotations

import array
import logging
import math
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

# Signed 16-bit PCM, the format requested from arecord below. Kept as
# module constants rather than inlined so assess_health()'s normalisation
# and the capture request cannot drift apart.
_SAMPLE_WIDTH_BYTES = 2
_FULL_SCALE = 32768.0


class MicrophoneError(RuntimeError):
    """Raised when a capture cannot be completed end-to-end.

    Covers a missing `arecord`, no capture device present, a non-zero
    arecord exit, a capture that overran its timeout, and a byte count that
    is not a whole number of frames. All are treated identically by the
    caller (services/reflex_loop.py): logged, and the ACOUSTIC modality
    reported unavailable to fuse() - the same "degrade loudly, never block"
    discipline perception.camera.CameraError and
    perception.detector.DetectionError already get there.
    """


@dataclass(frozen=True)
class AudioClip:
    """One captured window of mono PCM, plus the level statistics of it.

    The statistics are computed once at capture time rather than on demand
    because every caller needs them (assess_health() gates on them, the
    bench tooling logs them, and the classifier client needs the sample
    rate alongside the bytes) and a second pass over 160k samples in pure
    Python is not free.

    Attributes:
        samples: Signed 16-bit mono PCM in native byte order.
        sample_rate: Hz. Always SAMPLE_RATE_HZ for clips this module
            produces; carried explicitly so a clip loaded from a WAV in the
            bench tooling can travel the same path.
        device: The ALSA device string the clip came from, e.g.
            "plughw:1,0". Logged on failure so a mis-enumerated hub is
            diagnosable after the fact.
        rms: Root-mean-square level, normalised to 0-1 against full scale.
        peak: Largest absolute sample, normalised to 0-1.
        clipped_fraction: Fraction of samples at or beyond full scale.
            Non-zero means the capture gain is too high and the waveform
            the classifier sees is distorted.
        dc_offset: Mean sample value, normalised to 0-1 and unsigned. A
            large offset points at a bias/coupling fault rather than a real
            signal, and it inflates `rms` without inflating `peak`.
    """

    samples: array.array
    sample_rate: int
    device: str
    rms: float
    peak: float
    clipped_fraction: float
    dc_offset: float

    @property
    def duration_s(self) -> float:
        """Wall duration of the clip, derived rather than stored."""
        if self.sample_rate <= 0:
            return 0.0
        return len(self.samples) / float(self.sample_rate)

    def to_bytes(self) -> bytes:
        """Little-endian S16 bytes, the wire format the classifier wants.

        Byte order is forced rather than assumed: `array.array` is native
        order, the board is little-endian aarch64 so today they coincide,
        and a silent big-endian byte swap would show up as plausible-looking
        noise rather than an error.
        """
        if sys.byteorder == "big":
            swapped = array.array(self.samples.typecode, self.samples)
            swapped.byteswap()
            return swapped.tobytes()
        return self.samples.tobytes()


@dataclass(frozen=True)
class MicrophoneHealth:
    """Verdict on whether a clip is worth classifying.

    Attributes:
        ok: False means do not classify this clip and report ACOUSTIC
            unavailable to fuse().
        reason: Human-readable failure cause, None when ok. Logged
            verbatim; the wording is the operator's only clue about which
            physical fault to go and check.
        clip: The clip the verdict is about, so a caller can log levels and
            verdict together without holding both.
    """

    ok: bool
    reason: str | None
    clip: AudioClip


class CaptureRunner(Protocol):
    """Callable shape that actually executes the capture subprocess.

    Injected so tests can exercise every branch - silence, clipping, a
    short read, a non-zero exit - without an audio device, matching the
    structural-Protocol convention the rest of device/mpu uses for injected
    dependencies (perception/detector.py's VisionDetectFn,
    services/reflex_loop.py's DriveHornFn).
    """

    def __call__(self, argv: list[str], timeout_s: float) -> bytes:
        """Run `argv`, return its raw stdout, raise MicrophoneError on failure."""
        ...


def _run_arecord(argv: list[str], timeout_s: float) -> bytes:
    """Default CaptureRunner: run arecord and hand back raw PCM on stdout."""
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise MicrophoneError(
            f"{argv[0]} not found - alsa-utils is required for audio capture"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MicrophoneError(
            f"capture exceeded its {timeout_s:.1f}s timeout - device may be wedged"
        ) from exc
    except OSError as exc:
        raise MicrophoneError(f"could not run {argv[0]}: {exc}") from exc

    if completed.returncode != 0:
        # arecord's own stderr is the only useful diagnostic here ("No such
        # file or directory" for a wrong card, "Device or resource busy" if
        # something else holds the PCM), so it is carried through rather
        # than reduced to an exit code.
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise MicrophoneError(
            f"arecord exited {completed.returncode}: {detail or '(no stderr)'}"
        )
    return completed.stdout


# `arecord -l` lists capture hardware one card per stanza, e.g.
#   card 1: Device [USB PnP Sound Device], device 0: USB Audio [USB Audio]
# The card index and device index are what a plughw string is built from;
# the bracketed name is what distinguishes a USB dongle from the SoC's own
# internal codecs, which also appear in this list and cannot be recorded
# from usefully.
_ARECORD_CARD_RE = re.compile(
    r"^card\s+(\d+):\s+(\S+)\s+\[([^\]]*)\].*?device\s+(\d+):", re.MULTILINE
)

# Substrings that mark a card as the USB audio dongle rather than one of
# the QRB2210's on-die audio front ends. Matched case-insensitively against
# both the short card id and the bracketed long name. Deliberately broad:
# the CM108/PCM2902-class adapters in circulation announce themselves with
# a dozen different vendor strings and the only thing they reliably share
# is the words "USB" or "Audio".
_USB_CARD_HINTS = ("usb", "codec", "headset", "microphone")


def discover_capture_device(
    *,
    arecord_path: str = "arecord",
    runner: CaptureRunner | None = None,
) -> str:
    """Find the USB capture device and return its plughw string.

    Hardcoding "plughw:1,0" would work right up until the hub enumerates in
    a different order after a reboot, at which point the system would
    record silence from an on-die codec and never say why. Enumeration
    order on this board is not stable across reboots - the camera path has
    already been bitten by exactly that - so the card is looked up by name
    every time a Microphone is constructed.

    Args:
        arecord_path: Overridable for tests and for an image where
            alsa-utils is not on PATH.
        runner: Injected CaptureRunner; defaults to really running arecord.

    Returns:
        An ALSA device string such as "plughw:1,0".

    Raises:
        MicrophoneError: if arecord is missing, lists no capture hardware
            at all, or lists only devices that look like on-die codecs.
    """
    run = runner or _run_arecord
    if runner is None and shutil.which(arecord_path) is None:
        raise MicrophoneError(
            f"{arecord_path} not found on PATH - install alsa-utils or pass "
            "an explicit device"
        )

    raw = run([arecord_path, "-l"], 5.0)
    listing = raw.decode("utf-8", "replace")
    cards = _ARECORD_CARD_RE.findall(listing)
    if not cards:
        raise MicrophoneError(
            "arecord -l listed no capture devices - is the USB audio adapter "
            "plugged into the hub and enumerated?"
        )

    for card_index, short_name, long_name, device_index in cards:
        haystack = f"{short_name} {long_name}".lower()
        if any(hint in haystack for hint in _USB_CARD_HINTS):
            device = f"plughw:{card_index},{device_index}"
            logger.info(
                "acoustic capture device: %s (card %s '%s')",
                device,
                card_index,
                long_name,
            )
            return device

    listed = ", ".join(f"card {c} '{n}'" for c, _s, n, _d in cards)
    raise MicrophoneError(
        f"no USB capture device among the {len(cards)} card(s) ALSA lists "
        f"({listed}) - the on-die codecs cannot be recorded from"
    )


def assess_health(
    clip: AudioClip,
    *,
    min_rms: float,
    max_clipped_fraction: float,
    max_dc_offset: float,
) -> MicrophoneHealth:
    """Decide whether `clip` is worth handing to the classifier.

    Three independent faults, each of which produces frames that look
    perfectly well-formed to ALSA:

    - **Near-silence.** The BY-M1's LR44 cell is dead, or the mic is
      switched off, or the TRRS plug is seated in the headphone contact
      rather than the mic contact. All three yield a tiny but non-zero
      signal, which classifies as confident `ambient` and is
      indistinguishable from a genuinely quiet night.
    - **Clipping.** Capture gain (or the adapter's own mic boost) is too
      high. The log-mel front end sees a squared-off waveform whose
      harmonic content is an artifact of the ADC, not of the source.
    - **DC offset.** A bias or coupling fault. This one is worth separating
      from the other two because it *raises* RMS, so it can mask
      near-silence: a dead mic with a large offset passes a naive level
      check while carrying no signal at all.

    The thresholds are passed in rather than read from services/config.py
    so this function stays pure and directly testable; main.py binds the
    configured values.

    Returns:
        A MicrophoneHealth. The first failing check wins and names itself -
        callers log `reason` verbatim.
    """
    if clip.dc_offset > max_dc_offset:
        return MicrophoneHealth(
            ok=False,
            reason=(
                f"DC offset {clip.dc_offset:.4f} exceeds {max_dc_offset:.4f} - "
                "bias or coupling fault; note this inflates RMS, so the "
                "silence check below cannot be trusted on this clip"
            ),
            clip=clip,
        )
    if clip.rms < min_rms:
        return MicrophoneHealth(
            ok=False,
            reason=(
                f"RMS {clip.rms:.6f} below floor {min_rms:.6f} - microphone is "
                "effectively silent (check the LR44 cell, the on/off switch, "
                "and that the TRRS plug is fully seated)"
            ),
            clip=clip,
        )
    if clip.clipped_fraction > max_clipped_fraction:
        return MicrophoneHealth(
            ok=False,
            reason=(
                f"{clip.clipped_fraction * 100:.2f}% of samples clipped, over "
                f"{max_clipped_fraction * 100:.2f}% - capture gain too high; "
                "turn off the adapter's mic boost"
            ),
            clip=clip,
        )
    return MicrophoneHealth(ok=True, reason=None, clip=clip)


def _measure(samples: array.array) -> tuple[float, float, float, float]:
    """Return (rms, peak, clipped_fraction, dc_offset), all 0-1 normalised.

    One pass, no numpy. numpy is importable on the board (perception/
    camera.py already depends on cv2, which brings it), but this runs over
    a few hundred thousand samples once per acoustic event, and keeping the
    capture module import-light means the bench tooling and the unit tests
    can exercise it with nothing installed at all.
    """
    count = len(samples)
    if count == 0:
        return 0.0, 0.0, 0.0, 0.0

    total = 0
    square_total = 0
    peak = 0
    clipped = 0
    # -32768 has no positive counterpart in S16, so abs() of it sits one
    # count outside the nominal positive range; treating anything at or
    # beyond +/-32767 as clipped sidesteps that asymmetry and is what "at
    # full scale" means in practice anyway.
    for sample in samples:
        total += sample
        square_total += sample * sample
        magnitude = -sample if sample < 0 else sample
        if magnitude > peak:
            peak = magnitude
        if magnitude >= 32767:
            clipped += 1

    mean = total / count
    rms = math.sqrt(square_total / count) / _FULL_SCALE
    return (
        rms,
        peak / _FULL_SCALE,
        clipped / count,
        abs(mean) / _FULL_SCALE,
    )


class Microphone:
    """One USB capture device, recorded from on demand.

    Holds no OS handle between calls - each capture() spawns its own
    arecord and the device is closed again the instant it exits. That is a
    deliberate difference from perception/camera.py, which keeps a handle
    open across an event: the camera is opened once per event and read many
    times, whereas audio is captured as a single window, and an ALSA PCM
    held open across minutes of idle is a device that something else (a
    second process, a hub power cycle) can invalidate underneath us with no
    way to notice until the next read returns silence.
    """

    #: The only rate this class will capture at - see the module docstring.
    SAMPLE_RATE_HZ = 8000

    #: Seconds recorded and thrown away at the start of every capture.
    #:
    #: Measured on the board 30 Sept 2026 (Microdia 0c45:6366 on plughw:1,0,
    #: card 1). Every fresh arecord open produces a large decaying transient
    #: before the stream settles, and because capture() deliberately opens a
    #: new arecord per call (see the class docstring) it is paid every time,
    #: not once at startup. Reproducible to three significant figures across
    #: separate captures, which is what distinguishes it from a real scene:
    #:
    #:     window    rms       peak     clipped    dc
    #:     0-1 s     0.16662   1.0000   1.25e-4    -0.11704
    #:     0-4 s     0.09080   1.0000   3.10e-5    -0.00326
    #:     4-12 s    0.00795   0.0302   0          +0.00118
    #:     8-12 s    0.00727   0.0264   0          +0.00020
    #:
    #: The first second hard-clips at full scale and carries a DC offset of
    #: -0.117 - on its own that is 2.3x ACOUSTIC_MAX_DC_OFFSET, but averaged
    #: over a whole clip it disappears, so the health gate passes a clip
    #: whose loudest content is pure artifact. From 4 s on the stream is
    #: flat. 4.0 is that settling point with no extra margin added; it is
    #: measured, not invented.
    WARMUP_S = 4.0

    def __init__(
        self,
        device: str,
        *,
        sample_rate: int = SAMPLE_RATE_HZ,
        arecord_path: str = "arecord",
        timeout_margin_s: float = 3.0,
        warmup_s: float = WARMUP_S,
        runner: CaptureRunner | None = None,
    ) -> None:
        """Bind to an ALSA device; performs no I/O.

        Args:
            device: ALSA device string, e.g. "plughw:1,0". Use
                discover_capture_device() to obtain one rather than
                hardcoding it.
            sample_rate: Hz. Defaults to SAMPLE_RATE_HZ and should not be
                changed for the deployed path - the impulse declares 8 kHz
                and the 4x upsample to the PANNs front end happens inside
                the DSP block, not here.
            arecord_path: Overridable for tests / a non-standard image.
            timeout_margin_s: Added to the requested duration to form the
                subprocess timeout. arecord needs to open the PCM and drain
                its buffer either side of the recording itself, so a
                timeout equal to the duration would fire on every healthy
                capture.
            warmup_s: Seconds recorded and discarded at the head of every
                capture - see WARMUP_S. 0 disables the discard, which is
                what the bench tooling wants when it is characterising the
                transient itself.
            runner: Injected CaptureRunner; defaults to really running
                arecord.
        """
        if warmup_s < 0:
            raise MicrophoneError(f"warmup_s must not be negative, got {warmup_s}")
        self._device = device
        self._sample_rate = sample_rate
        self._arecord_path = arecord_path
        self._timeout_margin_s = timeout_margin_s
        self._warmup_s = warmup_s
        self._runner = runner or _run_arecord

    @property
    def device(self) -> str:
        """The ALSA device string this instance records from."""
        return self._device

    @property
    def sample_rate(self) -> int:
        """Capture rate in Hz."""
        return self._sample_rate

    def capture(self, duration_s: float) -> AudioClip:
        """Record `duration_s` of mono audio and measure it.

        Args:
            duration_s: Seconds to record. Must be positive.

        Returns:
            An AudioClip with level statistics already computed. The clip is
            *not* health-checked here - call assess_health() on it; keeping
            the two apart means the bench tooling can record and inspect a
            clip that would fail the gate.

        Raises:
            MicrophoneError: on any capture failure, including a short read.
        """
        if duration_s <= 0:
            raise MicrophoneError(f"duration_s must be positive, got {duration_s}")

        # Record the warm-up and the wanted window in ONE arecord run. A
        # separate throwaway capture would not help: the transient belongs
        # to opening the PCM, so a second open would just reproduce it.
        total_s = duration_s + self._warmup_s
        argv = [
            self._arecord_path,
            "-D", self._device,
            "-f", "S16_LE",
            "-c", "1",
            "-r", str(self._sample_rate),
            "-t", "raw",
            "-d", str(int(math.ceil(total_s))),
            "-q",
        ]
        raw = self._runner(argv, total_s + self._timeout_margin_s)

        if len(raw) % _SAMPLE_WIDTH_BYTES:
            raise MicrophoneError(
                f"captured {len(raw)} bytes, not a whole number of 16-bit "
                "frames - the capture was truncated mid-sample"
            )
        samples = array.array("h")
        samples.frombytes(raw)
        if sys.byteorder == "big":
            # arecord was asked for S16_LE explicitly; array.array read it
            # as native order, so on a big-endian host the two disagree.
            samples.byteswap()

        # Drop the warm-up before measuring. Doing it here rather than in
        # the caller means rms/peak/clipped/dc - and therefore the health
        # gate - all describe the settled stream only.
        warmup_samples = int(self._sample_rate * self._warmup_s)
        if warmup_samples:
            if len(samples) <= warmup_samples:
                raise MicrophoneError(
                    f"captured {len(samples)} samples, not more than the "
                    f"{warmup_samples}-sample warm-up - nothing left to "
                    "classify after the discard"
                )
            samples = samples[warmup_samples:]

        expected = int(self._sample_rate * duration_s)
        if len(samples) < expected // 2:
            # A capture that returns less than half what was asked for is a
            # device fault (unplugged mid-record, PCM stolen by another
            # process), not a short buffer. Below that line the clip is too
            # short to classify meaningfully anyway.
            raise MicrophoneError(
                f"short capture: got {len(samples)} samples, expected about "
                f"{expected} - device may have been removed mid-record"
            )

        rms, peak, clipped_fraction, dc_offset = _measure(samples)
        clip = AudioClip(
            samples=samples,
            sample_rate=self._sample_rate,
            device=self._device,
            rms=rms,
            peak=peak,
            clipped_fraction=clipped_fraction,
            dc_offset=dc_offset,
        )
        logger.debug(
            "captured %.2fs from %s: rms=%.5f peak=%.5f clipped=%.4f%% dc=%.5f",
            clip.duration_s,
            self._device,
            rms,
            peak,
            clipped_fraction * 100,
            dc_offset,
        )
        return clip
