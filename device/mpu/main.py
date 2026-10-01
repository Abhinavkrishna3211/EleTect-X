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
import time

from arduino.app_utils import Bridge

from bridge.rpc import AcousticClass
from cognition.experience import ExperienceStore
from comms.lora_uplink import LoraUplink, direct_alert_event, event_from_footfall
from perception.camera import Camera
from perception.detector import HttpVisionDetector
from perception.night import frames_are_night
from perception.seismic_dataset import SeismicDatasetWriter, clear_part_files
from perception.seismic_stream import SeismicStream
from perception.storage import clear_orphaned_scratch, save_burst
from perception.video import EventVideoRecorder
from services import config, reflex_loop

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

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

    Args:
        volts: Raw geophone reading in volts, as sent by geophone_cpp's
            Bridge.notify("debug_stream_raw_seismic_sample", volts) call.
    """
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
if config.EVENT_VIDEO_ENABLED:
    logger.info("event video enabled (ADR 0020) - camera frames served from the GStreamer pipeline")
    _event_video: EventVideoRecorder | None = EventVideoRecorder()
    _camera: reflex_loop.CameraProtocol = _event_video
else:
    _event_video = None
    _camera = Camera()

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
    config.VISION_INFERENCE_URL, config.VISION_INFERENCE_TIMEOUT_S
)

# One experience store per process, held open across events and across the
# MPU's suspend/resume cycles. Constructed at module scope for the same
# reason the camera is: ExperienceStore.__init__ does no I/O, so it neither
# creates the database nor touches the filesystem until the first real
# event. It is deliberately never closed here - the process runs until it is
# killed, and every method commits, so there is no unflushed state a close()
# would rescue.
_experience = ExperienceStore()

# LoRa event uplink (ADR 0031). The Bridge call only puts the frame on the
# MCU's radio queue, so it gets the IR call's short timeout; the worker
# thread means even that wait never lands on a deterrence path.
_lora_uplink = LoraUplink(
    lambda *args: Bridge.call(*args, timeout=config.BRIDGE_IR_CALL_TIMEOUT_S),
    config.SCHEMA_VERSION,
)


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
    independently in tests/test_reflex_loop.py. This function exists only
    to bind the real Bridge.call-backed drive_horn/drive_led/pulse_ir, the
    real camera, the real save_burst, and the real SQLite-backed
    experience store in as the injected dependencies reflex_loop's
    signature requires. `event_video` is None unless
    config.EVENT_VIDEO_ENABLED is set, in which case it is the same object
    as `camera` - see the construction block above. `extra` is whatever the
    starting trigger adds on top of that, which today is the acoustic
    path's acoustic_confidence/seismic_available pair.

    The finished outcome is handed to the LoRa uplink, which decides
    whether it is worth airtime and sends it off this thread.
    """
    outcome = reflex_loop.handle_footfall_event(
        schema_version,
        probability,
        sta_lta_ratio,
        feature_vector,
        drive_horn=lambda sv, gain_pct, duration_ms, track_id: Bridge.call(
            "drive_horn",
            sv,
            gain_pct,
            duration_ms,
            track_id,
            timeout=config.BRIDGE_HORN_CALL_TIMEOUT_S,
        ),
        drive_led=lambda sv, channel, pattern_id, gain_pct, duration_ms: Bridge.call(
            "drive_led",
            sv,
            channel,
            pattern_id,
            gain_pct,
            duration_ms,
            timeout=config.BRIDGE_LED_CALL_TIMEOUT_S,
        ),
        pulse_ir=lambda sv, duration_ms: Bridge.call(
            "pulse_ir", sv, duration_ms, timeout=config.BRIDGE_IR_CALL_TIMEOUT_S
        ),
        is_night=lambda frames: frames_are_night(
            [f.image for f in frames], config.NIGHT_SATURATION_THRESHOLD
        ),
        camera=_camera,
        detect_vision=_vision_detector,
        save_frames=save_burst,
        experience=_experience,
        event_video=_event_video,
        seismic_stream=_seismic_stream,
        seismic_dataset=_seismic_dataset,
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


# The MCU's ground-motion stream, reassembled from its batched notifies
# (ADR 0035). Built unconditionally even though nothing feeds it yet: it is
# ~30 kB of list and holds no handle on anything, and a buffer that only
# exists once the registration below is uncommented is a buffer whose first
# run happens on the one night it matters.
_seismic_stream = SeismicStream()

# Where the camera-labelled records land. Also unconditional, and for a
# stronger reason than the buffer above: with no stream it still writes the
# vision half of every watch - the boxes, the species, and whether the
# camera could see at all - which is the labelled half and the half that
# cannot be reconstructed afterwards. The waveform appears in those records
# the moment report_seismic_batch is registered, with no other change.
_seismic_dataset = SeismicDatasetWriter()


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

    Returns whether the event was queued on this side; the radio reports
    delivery on its own.
    """
    del schema_version  # the uplink sends config.SCHEMA_VERSION itself
    return _lora_uplink.submit(
        direct_alert_event(
            acoustic_class, confidence, capture_ref, safe_mode=reflex_loop.SAFE_MODE
        )
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

# UNVERIFIED: whether App Lab's own runtime keeps this process alive after
# registration, or whether the script itself must block. Blocking here is
# the safe assumption either way - it is a no-op if the runtime already
# keeps the process alive, and required if it doesn't.
while True:
    time.sleep(1)
