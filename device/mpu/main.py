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
from perception.camera import Camera
from perception.storage import save_burst
from services import config, reflex_loop

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL))
logger = logging.getLogger(__name__)

logger.info(
    "eletect-x reflex loop starting, SAFE_MODE=%s (export ELETECT_SAFE_MODE=0 "
    "to disable dry-run for a live session)",
    reflex_loop.SAFE_MODE,
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

# One Camera per process, reused across events - not opened here.
# Camera.__init__ does no I/O (perception/camera.py), so constructing this
# at module scope is safe even before Bridge/hardware are confirmed ready;
# only reflex_loop's own open()/close() calls around each alert touch the
# device, so the camera is never left held open between events.
_camera = Camera()

# One experience store per process, held open across events and across the
# MPU's suspend/resume cycles. Constructed at module scope for the same
# reason the camera is: ExperienceStore.__init__ does no I/O, so it neither
# creates the database nor touches the filesystem until the first real
# event. It is deliberately never closed here - the process runs until it is
# killed, and every method commits, so there is no unflushed state a close()
# would rescue.
_experience = ExperienceStore()


def _on_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
) -> None:
    """Bridge.provide() adapter for report_footfall_event - see schema.md.

    Thin wrapper: the real logic is reflex_loop.handle_footfall_event(),
    tested independently in tests/test_reflex_loop.py. This function exists
    only to bind the real Bridge.call-backed drive_horn/drive_led/pulse_ir,
    the real Camera, the real save_burst, and the real SQLite-backed
    experience store in as the injected dependencies reflex_loop's signature
    requires.
    """
    reflex_loop.handle_footfall_event(
        schema_version,
        probability,
        sta_lta_ratio,
        feature_vector,
        drive_horn=lambda sv, gain_pct, duration_ms: Bridge.call(
            "drive_horn", sv, gain_pct, duration_ms
        ),
        drive_led=lambda sv, pattern_id, duration_ms: Bridge.call(
            "drive_led", sv, pattern_id, duration_ms
        ),
        pulse_ir=lambda sv, duration_ms: Bridge.call("pulse_ir", sv, duration_ms),
        camera=_camera,
        save_frames=save_burst,
        experience=_experience,
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
    branch on the routing, not for this adapter. Same reason
    _on_footfall_event above drops its FootfallOutcome.
    """
    reflex_loop.handle_acoustic_event(
        schema_version,
        class_label,
        confidence,
        capture_ref,
        send_lora_alert=lambda sv, conf, cap_ref: Bridge.call(
            "send_lora_alert", sv, conf, cap_ref
        ),
    )


# NOT YET ENABLED - see module docstring's "Registration state" paragraph.
# Uncomment ONE of these, flash, and confirm on real hardware (including
# that debug_stream_raw_seismic_sample above still works) before uncommenting
# the other.
Bridge.provide("report_footfall_event", _on_footfall_event)
# Bridge.provide("report_acoustic_event", _on_acoustic_event)

# UNVERIFIED: whether App Lab's own runtime keeps this process alive after
# registration, or whether the script itself must block. Blocking here is
# the safe assumption either way - it is a no-op if the runtime already
# keeps the process alive, and required if it doesn't.
while True:
    time.sleep(1)
