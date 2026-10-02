"""Production Python entry point for the eletect-x Arduino App.

The real sense -> fuse -> decide -> actuate loop (CONTEXT.md 4) is wired
against cognition.fusion (via services/reflex_loop.py) and against
bridge/rpc.py's schema - reflex_loop.py's handler signatures and
AcousticClass usage match rpc.py's stubs, and are checked against them by
eye at every edit; rpc.py itself stays signature-only and is never called
here (raise NotImplementedError bodies - see that module's own header for
why). The loop logic lives in services/reflex_loop.py, not in this file, so
it can be pytest-tested on a dev laptop with no board attached
(tests/test_reflex_loop.py) - this file only wires the real
arduino.app_utils.Bridge in and registers handlers, mirroring
device/mpu/bench/ping/python/main.py's own thin-wiring pattern.

SAFE_MODE (services/reflex_loop.py, default on) gates every real side effect
this loop can have - drive_horn/drive_led/pulse_ir plus the camera/storage
capture that rides alongside them - behind a dry-run log. Flipping it off is
an explicit environment step for a live session with a human present
(`export ELETECT_SAFE_MODE=0`), never a code default.

Registration state, per the one-at-a-time discipline
`DEVICE_DEVELOPMENT_WORKFLOW.md` 3 documents (a live, reproducible bug where
an additional `Bridge.provide()` broke previously-working ones on the same
sketch - "not paranoia, a documented current failure mode",
`ENGINEERING_CONVENTIONS.md` 8): `debug_stream_raw_seismic_sample` and
`_on_footfall_event` are the two functions registered below as of the
2026-08-14 live session wiring up report_footfall_event end to end -
`_on_footfall_event` was added second, per that discipline, with
`debug_stream_raw_seismic_sample`'s continued operation checked afterward
(see docs/KNOWN_GAPS.md for that session's result). `_on_acoustic_event` is
written and ready - reflex_loop.py's logic behind it is host-tested - but
its `Bridge.provide()` call stays commented out until a future live session
flashes/tests it against real hardware, same discipline as the MCU-side
actuator registrations (device/mcu/src/main.cpp). Do not uncomment more
than one per test cycle; confirm the existing registrations still work
after each addition before moving to the next.

Note that `report_acoustic_event` now has no producer. ADR 0028 moved the
microphone from the MCU to this side - the Arduino core for this board
ships a prebuilt Zephyr loader with a fixed devicetree, so a sketch cannot
add the SAI peripheral ADR 0009 assumed. Acoustic therefore originates
here, on a polling daemon thread (see the ADR 0028 block below), and needs
no `Bridge.provide()` at all, which keeps it clear of the
one-registration-per-cycle hazard above entirely. `_on_acoustic_event`
survives for the always-on MCU gunshot path ADR 0009 still specifies and
docs/KNOWN_GAPS.md still tracks as unbuilt.

`_on_seismic_batch` (ADR 0035) is the second function waiting behind that
same gate, and it is further from running than `_on_acoustic_event` is:
its producer, the MCU's `SEISMIC_CAPTURE_ENABLED`, is also 0, so neither
half of that path has ever executed on hardware. Both have to come up in
one session, and the Bridge drops an oversized notify silently rather than
erroring, so the first check after enabling them is whether batches arrive
at all.

Same UNVERIFIED caveat this file has always carried: it is not confirmed
whether App Lab's own runtime keeps the process alive after registration
alone or whether the script itself must block - blocking is the safe
assumption either way.
"""

import logging
import threading
import time

from arduino.app_utils import Bridge

from bridge import wire_compat
from bridge.rpc import AcousticClass
from cognition.experience import ExperienceStore
from comms.lora_uplink import LoraUplink, direct_alert_event, event_from_footfall
from perception.acoustic_detector import AcousticDetectionError, HttpAcousticClassifier
from perception.camera import Camera, Frame
from perception.detector import HttpVisionDetector
from perception.microphone import Microphone, MicrophoneError, discover_capture_device
from perception.night import frames_are_night
from perception.seismic_dataset import SeismicDatasetWriter, clear_part_files
from perception.seismic_stream import SeismicStream
from perception.storage import clear_orphaned_scratch, save_burst
from perception.video import EventVideoRecorder
from services import acoustic_watch, config, home_test, reflex_loop

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

if not wire_compat.install():
    logger.warning(
        "wire_compat.install() could not import msgpack - drive_led/drive_horn/"
        "pulse_ir calls with small integer params (channel, pattern_id, "
        "track_id) will keep hitting the fixint decode bug on the MCU side"
    )

logger.info(
    "eletect-x reflex loop starting, SAFE_MODE=%s (export ELETECT_SAFE_MODE=0 "
    "to disable dry-run for a live session)",
    reflex_loop.SAFE_MODE,
)
# NODE_DETERRENCE_SCOPE (ADR 0023) beside SAFE_MODE, for the same reason:
# an operational setting that changes what this node does must be visible
# in the boot log, not just in an unread config file. This one carries a
# real hazard the SAFE_MODE line does not - EXPERIENCE_DB_PATH is derived
# from the scope (services/config.py's deterrence_scope_labels() and
# experience_db_filename()), so a mid-trial flip to "both" silently resumes
# whatever bandit policy the home-phase "both" run learned instead of the
# trial's own cold-started one. Logging both together is what makes that
# swap visible instead of invisible - see TRIAL_READINESS_PLAN.md's ship-day
# checklist, which reads this exact line back.
logger.info(
    "NODE_DETERRENCE_SCOPE=%s (export ELETECT_DETERRENCE_SCOPE=elephant_only|"
    "boar_only|both) deterrent_target_labels=%s event_video_target_labels=%s "
    "experience_db=%s",
    config.NODE_DETERRENCE_SCOPE,
    config.DETERRENT_TARGET_LABELS,
    config.EVENT_VIDEO_TARGET_LABELS,
    config.EXPERIENCE_DB_PATH,
)
# Third boot banner, same "must be visible in the boot log" reasoning as the
# two above - this flag turns on always-on capture (ADR 0020 exists
# specifically to forbid that in the field) plus the raised
# HOME_TEST_FIRE_MIN_CONFIDENCE/HOME_TEST_FIRE_CONSECUTIVE_POLLS bar for
# firing (services/config.py). ELETECT_HOME_TEST_MODE is independent of the
# MCU's own HOME_TEST_MODE #define (device/mcu/src/config.h) - both default
# off and both must be flipped for tonight's test to run as designed.
if config.HOME_TEST_MODE:
    logger.warning(
        "*** HOME_TEST_MODE=1 *** backyard test build: always-on capture, "
        "raised fire bar, NOT a field deployment build - see "
        "services/home_test.py and services/config.py's HOME_TEST_* block"
    )
else:
    logger.info("HOME_TEST_MODE=0 (export ELETECT_HOME_TEST_MODE=1 for the backyard test build)")


def debug_stream_raw_seismic_sample(volts: float) -> None:
    """Bench-only: re-print one raw geophone volts sample on the MPU's stdout.

    Receive side of SEISMIC_DEBUG_STREAM_RAW's Bridge.notify() path
    (device/mcu/src/geophone.cpp) - a live alternative to that flag's
    existing Serial.println path, read via
    `docker logs -f eletect-x-main-1 | python scripts/live_seismic_plot.py -`.
    Prints in exactly the wire format scripts/live_seismic_plot.py's
    parse_raw_volts_line() already expects (bare float, 6 decimals, one per
    line) so that script needs no changes. Notify target, per
    device/mpu/bridge/rpc.py's own convention: no return value - the MCU
    never waits on one.

    Under HOME_TEST_MODE, this appends to HOME_TEST_SEISMIC_CSV_PATH instead
    of printing - the geophone is unwired tonight so this produces nothing,
    but the receive-side plumbing is correct and ready for whenever it is
    wired again. Field/bench behaviour (the bare 6-decimal print
    live_seismic_plot.py parses) is unchanged when the flag is off.

    Args:
        volts: Raw geophone reading in volts, as sent by geophone_cpp's
            Bridge.notify("debug_stream_raw_seismic_sample", volts) call.
    """
    if config.HOME_TEST_MODE:
        # mpu_wall_s is the same time.time() clock detections.jsonl's own
        # wall_s uses (services/home_test.py) - scripts/join_seismic_
        # detections.py joins the two logs on it, per the plan's "this also
        # removes the clock-sync problem" note: one clock, no MCU-side
        # millis() to reconcile. HOME_TEST_DIR already exists by the time
        # this can fire - HomeTestSession.__init__ creates it before this
        # process reaches its Bridge.provide() registrations below.
        with open(config.HOME_TEST_SEISMIC_CSV_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"{time.monotonic():.6f},{time.time():.6f},{volts:.6f}\n")
        return
    # flush=True: stdout is captured via `docker logs`, not a TTY, so Python
    # defaults to block-buffering here - without an explicit flush, samples
    # sit in the buffer and reach the log in delayed bursts instead of as
    # they arrive, which reads as a discontinuous/gappy line on the live plot.
    print(f"{volts:.6f}", flush=True)


Bridge.provide("debug_stream_raw_seismic_sample", debug_stream_raw_seismic_sample)

# Clear any scratch recording left behind by a previous run that died
# between "started recording" and "committed or discarded" - on this board
# the likeliest cause is the 5V brown-out in docs/KNOWN_GAPS.md. Run
# unconditionally rather than behind EVENT_VIDEO_ENABLED, because the case
# that most needs cleaning up is precisely a run that recorded and was then
# restarted with the flag off: nothing else would ever remove those files.
# It only ever touches the scratch directory (perception/storage.py); a
# committed capture is not reachable from it.
clear_orphaned_scratch()

# The same cleanup for the dataset's own half-written records (ADR 0035).
# A .part file is a write a brown-out caught between the bytes landing and
# the rename, so it is incomplete by definition and there is nothing to
# recover from it. Separate call rather than folded into the one above
# because they clean different directories under different retention rules,
# and a capture must never be removed by dataset housekeeping.
clear_part_files()

# Bridge.call-backed actuator adapters, hoisted to module scope (rather than
# built inline in _on_footfall_event, as before HOME_TEST_MODE) so the exact
# same callables can go into _footfall_kwargs below and be reused verbatim
# by services/home_test.py's deterrence thread - one definition of "how this
# process drives the MCU", not two that could drift.
def _drive_horn(sv: int, gain_pct: float, duration_ms: int, track_id: int) -> bool:
    """Bridge.call adapter for drive_horn - see bridge/schema.md."""
    return Bridge.call(
        "drive_horn",
        sv,
        gain_pct,
        duration_ms,
        track_id,
        timeout=config.BRIDGE_HORN_CALL_TIMEOUT_S,
    )


def _drive_led(
    sv: int, channel: int, pattern_id: int, gain_pct: float, duration_ms: int
) -> bool:
    """Bridge.call adapter for drive_led - see bridge/schema.md."""
    return Bridge.call(
        "drive_led",
        sv,
        channel,
        pattern_id,
        gain_pct,
        duration_ms,
        timeout=config.BRIDGE_LED_CALL_TIMEOUT_S,
    )


def _pulse_ir(sv: int, duration_ms: int) -> bool:
    """Bridge.call adapter for pulse_ir - see bridge/schema.md."""
    return Bridge.call("pulse_ir", sv, duration_ms, timeout=config.BRIDGE_IR_CALL_TIMEOUT_S)


# LoRa event uplink (ADR 0031). The Bridge call only puts the frame on the
# MCU's radio queue, so it gets the IR call's short timeout; the worker
# thread means even that wait never lands on a deterrence path.
_lora_uplink = LoraUplink(
    lambda *args: Bridge.call(*args, timeout=config.BRIDGE_IR_CALL_TIMEOUT_S),
    config.SCHEMA_VERSION,
)


def _is_night(frames: list[Frame]) -> bool | None:
    """NightDecideFn adapter - see perception/night.py."""
    return frames_are_night([f.image for f in frames], config.NIGHT_SATURATION_THRESHOLD)


# One camera per process, reused across events - not opened here. Both
# constructors below do no I/O (perception/camera.py, perception/video.py),
# so constructing at module scope is safe even before Bridge/hardware are
# confirmed ready; only reflex_loop's own open()/close() calls around each
# alert touch the device, so the camera is never left held open between
# events.
#
# With ADR 0020's event video enabled, the recorder *is* the camera - one
# USB device cannot be held by cv2.VideoCapture and GStreamer's v4l2src at
# the same time, so the same object is passed as both `camera` and
# `event_video` below and serves the vision-check and evidence bursts off
# the frames its own recording pipeline is already producing. With the flag
# off (the default, services/config.py) this is the plain Camera and
# reflex_loop behaves exactly as it did before that ADR.
#
# HOME_TEST_MODE overrides both of the above: services/home_test.py's
# HomeTestSession owns the one real Camera for the whole process (its
# capture thread never stops running), and `_camera` here becomes a
# SharedFrameCamera reading from that session's buffer instead of a second
# handle on /dev/video0. This is what makes _on_footfall_event below safe to
# leave registered under HOME_TEST_MODE even though the geophone is unwired
# tonight - if it ever did fire, it would share the session's camera rather
# than race it for the device. EVENT_VIDEO_ENABLED is not combined with
# HOME_TEST_MODE - the ring/encounter pipeline is this mode's own equivalent
# evidence path.
if config.HOME_TEST_MODE:
    if config.EVENT_VIDEO_ENABLED:
        logger.warning(
            "HOME_TEST_MODE and EVENT_VIDEO_ENABLED are both set - ignoring "
            "EVENT_VIDEO_ENABLED. HOME_TEST_MODE's own ring/encounter capture "
            "(services/home_test.py) owns the camera tonight."
        )
    _event_video: EventVideoRecorder | None = None
elif config.EVENT_VIDEO_ENABLED:
    logger.info("event video enabled (ADR 0020) - camera frames served from the GStreamer pipeline")
    _event_video = EventVideoRecorder()
else:
    _event_video = None

# One HTTP vision-detector client per process, reused across events - same
# module-scope-construction reasoning as _camera above.
# HttpVisionDetector.__init__ does no I/O either (perception/detector.py):
# it only stores the base URL and timeout, the actual connection attempt
# happens per-call inside reflex_loop's pre-decision vision check. Points at
# the standing edge-impulse-linux-runner --run-http-server process
# (services/config.py's VISION_INFERENCE_URL) - starting/supervising that
# process is not this file's job (docs/KNOWN_GAPS.md); if nothing is
# listening yet, detect_vision() raises DetectionError and reflex_loop
# degrades VISION to unavailable, the same as a camera failure.
_vision_detector = HttpVisionDetector(
    config.VISION_INFERENCE_URL,
    config.VISION_INFERENCE_TIMEOUT_S,
    config.VISION_MIN_CONFIDENCE_BY_LABEL,
)

# The MCU's ground-motion stream, reassembled from its batched notifies
# (ADR 0035). Built unconditionally even though nothing feeds it yet: it is
# ~30 kB of list and holds no handle on anything, and a buffer that only
# exists once the Bridge registration below is uncommented is a buffer whose
# first run happens on the one night it matters.
_seismic_stream = SeismicStream()

# Where the camera-labelled records land. Also unconditional, and for a
# stronger reason than the buffer above: with no stream it still writes the
# vision half of every watch - the boxes, the species, and whether the
# camera could see at all - which is the labelled half and the half that
# cannot be reconstructed afterwards. The waveform appears in those records
# the moment report_seismic_batch is registered, with no other change.
_seismic_dataset = SeismicDatasetWriter()

# One experience store per process, held open across events and across the
# MPU's suspend/resume cycles. Constructed at module scope for the same
# reason the camera is: ExperienceStore.__init__ does no I/O, so it neither
# creates the database nor touches the filesystem until the first real
# event. It is deliberately never closed here - the process runs until it is
# killed, and every method commits, so there is no unflushed state a close()
# would rescue.
_experience = ExperienceStore()

# Every keyword handle_footfall_event needs except camera and
# seismic_available - both _on_footfall_event below and, under
# HOME_TEST_MODE, services/home_test.py's deterrence thread build their call
# from this one dict, so the two paths cannot drift apart on which
# actuators/detector/experience store they bind in.
_footfall_kwargs = {
    "drive_horn": _drive_horn,
    "drive_led": _drive_led,
    "pulse_ir": _pulse_ir,
    "is_night": _is_night,
    "detect_vision": _vision_detector,
    "save_frames": save_burst,
    "experience": _experience,
    "event_video": _event_video,
    "retreat_burst_frames": config.CAMERA_RETREAT_BURST_FRAMES,
    "retreat_burst_interval_s": config.CAMERA_RETREAT_BURST_INTERVAL_S,
    "seismic_stream": _seismic_stream,
    "seismic_dataset": _seismic_dataset,
}

if config.HOME_TEST_MODE:
    _home_test_session: home_test.HomeTestSession | None = home_test.HomeTestSession(
        detect_vision=_vision_detector, footfall_kwargs=_footfall_kwargs
    )
    _camera: reflex_loop.CameraProtocol = home_test.SharedFrameCamera(_home_test_session)
else:
    _home_test_session = None
    _camera = _event_video if _event_video is not None else Camera()


def _run_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
    **extra,
) -> reflex_loop.FootfallOutcome | None:
    """Run one full event, and put the result on the uplink if it earned one.

    Hoisted out of _on_footfall_event below because there are now two ways
    an event starts - a geophone notify and an acoustic elephant call
    (ADR 0033) - and the bindings the two share must not be able to drift
    into two different sets.

    The real logic is reflex_loop.handle_footfall_event(), tested
    independently in tests/test_reflex_loop.py. `_footfall_kwargs` binds
    the real Bridge.call-backed drive_horn/drive_led/pulse_ir, the real
    save_burst, and the real SQLite-backed experience store; `camera` is
    `_camera` from the construction block above, which is either the
    plain/event-video Camera (field) or a HomeTestSession's
    SharedFrameCamera (HOME_TEST_MODE) - this function does not need to
    know which. `extra` is whatever the starting trigger adds on top of
    that, which today is the acoustic path's
    acoustic_confidence/seismic_available pair.

    The finished outcome is handed to the LoRa uplink, which decides
    whether it is worth airtime and sends it off this thread.
    """
    outcome = reflex_loop.handle_footfall_event(
        schema_version,
        probability,
        sta_lta_ratio,
        feature_vector,
        camera=_camera,
        **_footfall_kwargs,
        **extra,
    )
    if outcome is None:
        # Another event already owned the camera and the actuators, so
        # this notify ran nothing at all - no trigger recorded, no watch,
        # no deterrence. There is no outcome to put on air, and inventing
        # one would tell a ranger a node responded when it did not.
        return None
    _lora_uplink.submit(
        event_from_footfall(
            outcome,
            safe_mode=reflex_loop.SAFE_MODE,
        )
    )
    return outcome


def _on_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
) -> None:
    """Bridge.provide() adapter for report_footfall_event - see schema.md.

    Thin wrapper over _run_footfall_event above, which holds every binding
    and the uplink. The returned outcome is dropped here because a notify
    has no return channel to put it on.
    """
    _run_footfall_event(schema_version, probability, sta_lta_ratio, feature_vector)


def _on_seismic_batch(
    schema_version: int,
    first_sample_index: int,
    count: int,
    samples: list[int],
    geophone_ok: bool,
) -> None:
    """Bridge.provide() adapter for report_seismic_batch - see schema.md.

    Deliberately does almost nothing. This runs on the Bridge's RPC thread
    at roughly 8 Hz, and that thread also carries the drive_horn/drive_led
    acks the reflex loop blocks on mid-encounter; anything slow here shows
    up as deterrence latency. SeismicStream.push() is a bounded copy under
    a lock with no I/O, and it swallows a malformed batch rather than
    raising, because an exception on this thread is a dropped handler, not
    a visible failure.

    A mismatched schema_version is logged and the batch is kept, matching
    what every MCU-side handler does in the other direction
    (device/mcu/src/bridge_handlers.cpp). The alternative - discarding the
    ground motion because a version byte disagrees - throws away the one
    thing on this path that cannot be recovered later.
    """
    if schema_version != config.SCHEMA_VERSION:
        logger.warning(
            "report_seismic_batch schema mismatch: got %s, expected %s - keeping the batch",
            schema_version,
            config.SCHEMA_VERSION,
        )
    _seismic_stream.push(
        first_sample_index, count, samples, geophone_ok, time.monotonic()
    )


def _start_vision_event(confidence: float) -> reflex_loop.FootfallOutcome | None:
    """Start a full vision-gated event from an acoustic elephant call.

    ADR 0033: an elephant call never alerts on the microphone alone. It
    runs the same pipeline a geophone trigger runs - the vision watch, the
    bandit, the deterrence tier, the retreat tail, the event video and the
    uplink - with no geophone reading behind it.

    `seismic_available=False` carries that absence into fusion: it is what
    makes fuse() drop the seismic modality instead of scoring
    probability=0.0 as "the ground says no", which would drag the combined
    log-odds down and could suppress an alert the call had already earned.
    It is also what earns this event the extended watch, since an animal
    the geophone never heard is exactly the case that needs the longer
    look.

    The zeroed probability/sta_lta_ratio/feature_vector are logged for
    explainability like any other event's. They are honest rather than
    invented: there is no geophone reading on this path, and
    seismic_available=False is the field that says so.
    """
    return _run_footfall_event(
        config.SCHEMA_VERSION,
        0.0,
        0.0,
        [0.0] * 8,
        acoustic_confidence=confidence,
        seismic_available=False,
    )


def _on_acoustic_event(
    schema_version: int,
    class_label: AcousticClass,
    confidence: float,
    capture_ref: int,
) -> None:
    """Bridge.provide() adapter for report_acoustic_event - see schema.md.

    Discards the returned AcousticOutcome: a notify has no return channel,
    so the outcome exists for tests and for a future caller that wants to
    branch on the routing, not for this adapter. Both uplinks this can
    produce are already sent from inside the handler - a direct alert's
    through send_lora_alert, and a vision-confirmed elephant call's from
    _run_footfall_event, which an elephant call reaches through
    _start_vision_event.
    """
    reflex_loop.handle_acoustic_event(
        schema_version,
        class_label,
        confidence,
        capture_ref,
        send_lora_alert=_send_lora_alert,
        start_vision_event=_start_vision_event,
    )


def _send_lora_alert(
    schema_version: int, acoustic_class: str, confidence: float, capture_ref: int
) -> bool:
    """Direct-alert branch's uplink: a GUNSHOT or CHAINSAW event on the queue.

    The class comes from the handler rather than being decided here, so
    there is exactly one place that says which acoustic classes alert
    directly (reflex_loop._DIRECT_ALERT_ACOUSTIC_CLASSES) and exactly one
    that says which EventClass each becomes (lora_uplink's own table). An
    unroutable class raises out of direct_alert_event rather than becoming a
    silent UNCONFIRMED frame, which would read to an officer as a confirmed
    sighting of nothing.

    Hoisted out of _on_acoustic_event because the MPU-side acoustic poll
    below needs the same binding, and the two paths must not be able to
    drift into calling different things. Returns whether the event was
    queued on this side; the radio reports delivery on its own.
    """
    del schema_version  # the uplink sends config.SCHEMA_VERSION itself
    return _lora_uplink.submit(
        direct_alert_event(
            acoustic_class, confidence, capture_ref, safe_mode=reflex_loop.SAFE_MODE
        )
    )


# ---------------------------------------------------------------------------
# MPU-side acoustic poll (ADR 0028)
# ---------------------------------------------------------------------------
# The microphone is on this side of the board, not the MCU's, so nothing
# calls report_acoustic_event any more - _on_acoustic_event above is kept
# for the MCU-side always-on gunshot detector ADR 0009 still specifies and
# docs/KNOWN_GAPS.md still tracks as unbuilt, not because anything sends it
# today.
#
# Why a thread rather than the main loop below: a check blocks for the
# capture plus roughly 4 s of inference per window, and it is not confirmed
# whether App Lab's runtime dispatches Bridge.provide() callbacks on this
# thread. If it does, blocking in the main loop would delay
# report_footfall_event - and a deterrence path that arrives late because
# the system was busy listening is worse than no acoustic modality at all.
# A daemon thread keeps that question from mattering either way, and dies
# with the process without needing a shutdown path this file has nowhere to
# put.

# Constructed at module scope because, like HttpVisionDetector, this does no
# I/O in __init__ - only the per-call POSTs touch the network.
_acoustic_classifier = HttpAcousticClassifier(
    config.ACOUSTIC_INFERENCE_URL,
    config.ACOUSTIC_INFERENCE_TIMEOUT_S,
    window_hop_fraction=config.ACOUSTIC_WINDOW_HOP_FRACTION,
    max_windows=config.ACOUSTIC_MAX_WINDOWS,
)


def _open_microphone() -> Microphone:
    """Resolve the capture device and build a Microphone.

    Not done at module scope: discovery shells out to `arecord -l`, which
    is real I/O, and a USB microphone that is unplugged at boot must not
    stop the whole app from starting - the seismic and vision paths do not
    depend on it.

    Returns:
        A Microphone bound to the resolved ALSA device.

    Raises:
        MicrophoneError: If no USB capture device can be found.
    """
    device = config.ACOUSTIC_CAPTURE_DEVICE or discover_capture_device()
    return Microphone(device, sample_rate=config.ACOUSTIC_SAMPLE_RATE_HZ)


def _acoustic_poll_forever() -> None:
    """Run an acoustic check every ACOUSTIC_POLL_INTERVAL_S, forever.

    Re-resolves the microphone after any capture failure rather than
    holding one Microphone for the life of the process. USB enumeration on
    this board is not stable across a re-plug, and the field failure this
    guards against - somebody reseating a connector during a site visit -
    would otherwise leave the modality dead until the next reboot.

    Never raises. An exception escaping here would kill the thread
    silently and take acoustic down with no log line saying so, which is
    exactly the "reports nothing rather than reports broken" failure the
    health gate exists to prevent.
    """
    mic: Microphone | None = None
    while True:
        try:
            if mic is None:
                mic = _open_microphone()
                logger.info("acoustic poll using capture device %s", mic.device)

            capture_s = _acoustic_classifier.required_capture_s(
                windows=config.ACOUSTIC_CAPTURE_WINDOWS
            )
            outcome = acoustic_watch.run_acoustic_check(
                microphone=mic,
                classify=_acoustic_classifier,
                send_lora_alert=_send_lora_alert,
                start_vision_event=_start_vision_event,
                capture_s=capture_s,
            )
            if acoustic_watch.is_positive(outcome):
                logger.info(
                    "acoustic poll heard %s", outcome.outcome.class_label.value
                )
        except MicrophoneError as exc:
            # Includes discovery failing outright. Drop the handle so the
            # next pass re-resolves the card rather than retrying a device
            # string that may no longer exist.
            logger.warning("acoustic poll: microphone unavailable (%s)", exc)
            mic = None
        except AcousticDetectionError as exc:
            # The runner is a separate process this file does not
            # supervise (docs/KNOWN_GAPS.md). Not fatal, and not a reason
            # to re-resolve the microphone.
            logger.warning("acoustic poll: inference unavailable (%s)", exc)
        except Exception:
            logger.exception("acoustic poll: unexpected error, continuing")
            mic = None

        time.sleep(config.ACOUSTIC_POLL_INTERVAL_S)


# Off by default. services/config.py's ACOUSTIC_ENABLED stays False until
# bench/mic_check/mic_check.py has been run against the real BY-M1 and the
# three health floors it prints have replaced the invented ones - an
# uncalibrated silence floor cannot tell a dead LR44 from a quiet night,
# and this is a deployment real forest officers depend on.
if config.ACOUSTIC_ENABLED:
    logger.info(
        "acoustic poll enabled (ADR 0028) - every %.0fs against %s",
        config.ACOUSTIC_POLL_INTERVAL_S,
        config.ACOUSTIC_INFERENCE_URL,
    )
    threading.Thread(
        target=_acoustic_poll_forever, name="acoustic-poll", daemon=True
    ).start()
else:
    logger.info(
        "acoustic poll disabled (services/config.py ACOUSTIC_ENABLED) - "
        "run bench/mic_check/mic_check.py calibrate first"
    )


_lora_uplink.start()

# NOT YET ENABLED - see module docstring's "Registration state" paragraph.
# Uncomment ONE of these, flash, and confirm on real hardware (including
# that debug_stream_raw_seismic_sample above still works) before uncommenting
# the other.
Bridge.provide("report_footfall_event", _on_footfall_event)
# Bridge.provide("report_acoustic_event", _on_acoustic_event)
# Bridge.provide("report_seismic_batch", _on_seismic_batch)
#
# report_seismic_batch has a second gate on top of that one: its MCU half
# (SEISMIC_CAPTURE_ENABLED in device/mcu/src/config.h) is 0, so nothing is
# being sent for this to receive. Both halves have to be turned on in the
# same hardware session, and the Bridge drops an oversized notify silently,
# so the first thing to check afterwards is that batches are arriving at
# all - not that they look right.

if _home_test_session is not None:
    # Starts the capture and inference daemon threads (services/home_test.py)
    # - this call returns immediately, it does not block. Not wrapped in
    # try/except: a camera that fails to open here is the one failure this
    # whole test depends on not having, and it should surface as a crash
    # with a real traceback in the boot log, not a swallowed warning that
    # leaves the night silently unrecorded.
    _home_test_session.start()

# UNVERIFIED: whether App Lab's own runtime keeps this process alive after
# registration, or whether the script itself must block. Blocking here is
# the safe assumption either way - it is a no-op if the runtime already
# keeps the process alive, and required if it doesn't.
while True:
    time.sleep(1)
    # Belt-and-suspenders alongside HomeTestSession._run_guarded's own hard
    # exit on thread crash: if a daemon thread ever died without that guard
    # catching it, this is what turns a silently-stalled session back into
    # a crash the container restart policy can see and recover from.
    if _home_test_session is not None and not _home_test_session.is_healthy():
        logger.error("home_test: session unhealthy (a daemon thread died) - exiting")
        raise SystemExit(1)
