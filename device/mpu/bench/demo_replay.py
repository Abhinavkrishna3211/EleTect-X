"""Host-only replay of both reflex-loop entry points, for the Robu bench demo.

No hardware attached, no Bridge, no camera. Two passes, and the difference
between them is load-bearing -- do not read the second as if it carried the
first's provenance:

- **Pass 1 (seismic, real captured data).** Feeds real captured bench-stomp
  data (docs/KNOWN_GAPS.md's "Multi-trial stomp validation protocol" entry,
  run 2026-08-15 on real hardware) through services/reflex_loop.py's real
  handle_footfall_event(). Every sta_lta_ratio and real_fused_p value in
  REPLAY_EVENTS below is a number the real board genuinely reported that
  day.
- **Pass 2 (acoustic routing, illustrative).** Calls the real
  handle_acoustic_event() once per AcousticClass value to make ADR 0007 5's
  three-way routing split watchable rather than merely provable: gunshot
  bypasses fuse() entirely, chainsaw/vehicle/animal_call fuse as one shared
  ACOUSTIC modality, ambient fuses as unavailable. The routing, the fusion
  and every printed number are real -- but the *inputs* are not captured
  data. No acoustic classifier runs on the MCU yet (docs/KNOWN_GAPS.md), so
  there is no bench capture to replay; pass 2 uses one fixed synthetic
  confidence for all five classes. See ILLUSTRATIVE_ACOUSTIC_CONFIDENCE.

Both passes call the actual sense -> fuse -> decide pipeline, not a mock of
it, and narrate each step to the terminal. See docs/KNOWN_GAPS.md
("Build-call 1" section, the "Multi-trial stomp validation protocol" entry)
for the full capture pass 1 replays.

Two things this script does openly fabricate:
- The on-MCU `probability` field. footfall_features.cpp derives it from
  peak_ratio via `x^2/(x^2+c^2)` (x = ratio-1, c =
  FOOTFALL_PROBABILITY_SATURATION_C = 1.2 -- docs/KNOWN_GAPS.md's
  "report_footfall_event's probability... is an honest placeholder"
  entry) -- replicated here as mcu_probability() rather than hand-typing
  12 more captured numbers this doc doesn't individually list. The doc
  *does* list each event's real fused_P, so every printed block also
  shows what the real board logged next to what this replay computes --
  they land within rounding of each other, which is this script's own
  proof that the replica formula is right, not an assertion to take on
  faith.
- feature_vector. Not consumed by fuse() at all (reflex_loop.py's own
  docstring: logged for explainability only) and no per-event 8-feature
  capture exists in docs/KNOWN_GAPS.md beyond the single 2026-08-14
  stomp, so this replay passes 8 zeros -- the same placeholder
  tests/test_reflex_loop.py already uses.

Always runs with safe_mode=True: this laptop has no horn/LED/IR to
drive. The "would fire" lines below are the real DeterrenceAction the
contextual bandit selected for that event -- the same request a real
alert would put on the wire on hardware. The actuator/camera fakes passed
in raise if ever called, since SAFE_MODE should make that impossible; a
raise here would mean SAFE_MODE itself broke, not a demo cosmetic issue.

The experience store is in-memory (cognition.experience.IN_MEMORY_PATH),
so a replay never writes to the real device/mpu/data/experience.sqlite3
and never contaminates learning state with synthetic events. That does
mean each run starts cold, which is the honest thing to show anyway: the
escalation visible across the twelve stomps comes from the habituation
floor, which is deterministic, not from values learned in some earlier
run the audience cannot see. The stomps arrive well inside
HABITUATION_WINDOW_S of each other, so the ladder climbs exactly as it
would for an animal that keeps coming back.
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# Puts device/mpu on sys.path so `from services import reflex_loop` resolves
# the same way it does under pytest (pyproject.toml's pythonpath = ["."]) --
# same pattern as bench/camera_check/capture_check.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge.rpc import AcousticClass  # noqa: E402
from cognition.experience import IN_MEMORY_PATH, ExperienceStore  # noqa: E402
from cognition.fusion import Modality  # noqa: E402
from services import config as services_config  # noqa: E402
from services import reflex_loop  # noqa: E402

# ---------------------------------------------------------------------------
# Real captured bench data (docs/KNOWN_GAPS.md, "Multi-trial stomp
# validation protocol", run 2026-08-15: 12 stomps at 60s intervals against
# real hardware, STA_LTA_TRIGGER_RATIO=4.0 on the MCU side)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StompEvent:
    """One real stomp from the 2026-08-15 bench run.

    Attributes:
        index: 1-based position in the real 12-stomp sequence.
        sta_lta_ratio: The MCU's own STA/LTA ratio at trigger (or the
            near-miss peak) -- docs/KNOWN_GAPS.md, verbatim.
        detected: Whether this ratio cleared STA_LTA_TRIGGER_RATIO on the
            real board. False only for stomp 4 (ratio 3.80).
        real_fused_p: The fused probability the real MPU actually logged
            for this event, or None for the undetected stomp (nothing
            reached fuse() on the real run either). Printed alongside
            what this replay computes, as a cross-check.
    """

    index: int
    sta_lta_ratio: float
    detected: bool
    real_fused_p: float | None


REPLAY_EVENTS: tuple[StompEvent, ...] = (
    StompEvent(1, 4.18, True, 0.982),
    StompEvent(2, 4.01, True, 0.979),
    StompEvent(3, 4.20, True, 0.982),
    StompEvent(4, 3.80, False, None),  # genuine near-miss, not a bug -- docs/KNOWN_GAPS.md
    StompEvent(5, 4.34, True, 0.984),
    StompEvent(6, 4.05, True, 0.980),
    StompEvent(7, 4.18, True, 0.982),
    StompEvent(8, 4.32, True, 0.983),
    StompEvent(9, 4.36, True, 0.984),
    StompEvent(10, 4.11, True, 0.981),
    StompEvent(11, 4.60, True, 0.986),  # matches the original 2026-08-14 single-stomp bench figure
    StompEvent(12, 4.20, True, 0.982),
)

# device/mcu/include/config.h, validated against real hardware -- see
# docs/KNOWN_GAPS.md's "STA_SAMPLES, STA_LTA_TRIGGER_RATIO" entry. Mirrored
# here (not imported -- this is Python, config.h is C++) purely so the
# narrative below can name the real gate value.
STA_LTA_TRIGGER_RATIO = 4.0

QUIET_FLOOR_NOTE = (
    "60s pre-stomp baseline, real hardware: 688 samples, ratio 1.08-1.23 "
    "(mean 1.149, stdev 0.031) -- zero false triggers, all below "
    f"STA_LTA_TRIGGER_RATIO={STA_LTA_TRIGGER_RATIO:.2f}"
)

# footfall_features.cpp's saturating fit, replicated -- see module docstring.
FOOTFALL_PROBABILITY_SATURATION_C = 1.2


def mcu_probability(sta_lta_ratio: float) -> float:
    """Replicate the real on-MCU probability(peak_ratio) formula.

    `x^2 / (x^2 + c^2)`, x = ratio - 1, c =
    FOOTFALL_PROBABILITY_SATURATION_C -- device/mcu/src/footfall/
    footfall_features.cpp, docs/KNOWN_GAPS.md. Anchored the same way the
    real firmware constant was: c chosen so ratio=4.60 (the original
    bench stomp) lands at p=0.9.
    """
    x = sta_lta_ratio - 1.0
    c = FOOTFALL_PROBABILITY_SATURATION_C
    return (x * x) / (x * x + c * c)


# ---------------------------------------------------------------------------
# Acoustic routing pass (pass 2) -- illustrative, not captured bench data.
# Unlike REPLAY_EVENTS above, no bench capture exists for this: no acoustic
# classifier runs on the MCU yet (docs/KNOWN_GAPS.md), so there is nothing
# real to replay. One fixed confidence stands in for all five classes --
# 0.87, matching the gunshot case already used in tests/test_reflex_loop.py's
# test_acoustic_event_is_logged_and_returns_its_outcome. capture_ref mirrors
# that same test's synthetic ring-buffer index.
# ---------------------------------------------------------------------------

ILLUSTRATIVE_ACOUSTIC_CONFIDENCE = 0.87
ILLUSTRATIVE_CAPTURE_REF = 42


# ---------------------------------------------------------------------------
# Fakes -- SAFE_MODE should make every one of these unreachable
# ---------------------------------------------------------------------------


def _never_called(label: str):
    """Build a callable that fails loudly if invoked.

    Passed in place of drive_horn/drive_led/pulse_ir/save_frames: this
    replay always runs safe_mode=True, so none of these should ever
    actually fire. A raise here means SAFE_MODE itself broke, not that
    this demo script has a cosmetic bug.
    """

    def _raise(*_args, **_kwargs):
        raise AssertionError(f"{label} must never fire: SAFE_MODE is always on in this replay")

    return _raise


class _NoOpCamera:
    """Camera stand-in that must never be touched -- see _never_called()."""

    def open(self) -> None:
        _never_called("camera.open")()

    def capture_burst(self, count: int, interval_s: float):
        return _never_called("camera.capture_burst")()

    def close(self) -> None:
        _never_called("camera.close")()


# ---------------------------------------------------------------------------
# Narrative printing
# ---------------------------------------------------------------------------

_WIDTH = 72


class _Style:
    """ANSI styling, on only when stdout is a real terminal and not suppressed."""

    def __init__(self, enabled: bool):
        self.bold = "\033[1m" if enabled else ""
        self.dim = "\033[2m" if enabled else ""
        self.green = "\033[32m" if enabled else ""
        self.yellow = "\033[33m" if enabled else ""
        self.reset = "\033[0m" if enabled else ""


def _print_banner(style: _Style) -> None:
    rule = "=" * _WIDTH
    title = "EleTect X -- reflex loop replay (no hardware attached)"
    print(style.bold + rule + style.reset)
    print(style.bold + title + style.reset)
    print(rule)
    print("source:   pass 1 -- docs/KNOWN_GAPS.md, multi-trial stomp validation, 2026-08-15")
    print("pipeline: pass 1  services.reflex_loop.handle_footfall_event()   (seismic)")
    print("          pass 2  services.reflex_loop.handle_acoustic_event()   (acoustic routing)")
    print("          real fuse()/decide()/bandit select, SAFE_MODE dry run")
    print("          experience store: in-memory (no learning state written)")
    print()
    print(QUIET_FLOOR_NOTE)
    print()


def _print_detected(
    event: StompEvent,
    outcome: reflex_loop.FootfallOutcome,
    probability: float,
    style: _Style,
) -> None:
    rule = "-" * _WIDTH
    header = f"STOMP {event.index}/12  sta_lta_ratio={event.sta_lta_ratio:.2f}"
    print(style.bold + rule + style.reset)
    print(style.bold + header + style.reset)
    print(rule)
    print(
        f"  incoming seismic signal   sta_lta_ratio = {event.sta_lta_ratio:.2f}  "
        f"(trigger gate {STA_LTA_TRIGGER_RATIO:.2f}, cleared on-MCU)"
    )
    print(
        f"  MCU on-board model        probability   = {probability:.3f}  "
        "(footfall_features.cpp saturating fit)"
    )
    contribution = outcome.fusion.contributions[Modality.SEISMIC]
    print(
        f"  sense -> fuse             seismic contribution = {contribution:+.3f}  "
        "(acoustic/vision unavailable, dropped)"
    )
    print(f"                            fused log-odds L    = {outcome.fusion.log_odds:+.3f}")
    real_p = f"{event.real_fused_p:.3f}" if event.real_fused_p is not None else "n/a"
    fused_p = f"{style.green}{outcome.fusion.probability:.3f}{style.reset}"
    print(
        f"  fuse -> decide            fused P(elephant) = {fused_p}"
        f"   (real bench capture: {real_p})"
    )
    verdict = "ALERT" if outcome.decision.alert else "no alert"
    verdict_color = style.green if outcome.decision.alert else style.dim
    print(
        f"  decide                    {verdict_color}{verdict}{style.reset}"
        f"  (threshold {outcome.decision.threshold:.2f})"
    )
    if outcome.decision.alert and outcome.action is not None:
        action = outcome.action
        source = "exploring" if outcome.exploring else "greedy"
        print(
            f"  decide -> select          bandit tier {style.green}"
            f"{int(action.tier)}{style.reset} of 3"
            f"   (context {outcome.context}, {outcome.repeat_count} repeats in window,"
            f" {source})"
        )
        print("  would actuate (SAFE_MODE -- dry run, no hardware attached)")
        print(
            f"    horn   gain={action.horn_gain_pct:.1f}%"
            f"   duration={action.horn_duration_ms}ms"
        )
        print(
            f"    led    pattern={action.led_pattern_id}"
            f"   duration={action.led_duration_ms}ms"
        )
        if action.fire_ir:
            print(f"    ir     duration={action.ir_duration_ms}ms")
        else:
            print("    ir     not fired at this tier")
    print()


def _print_miss(event: StompEvent, style: _Style) -> None:
    rule = "-" * _WIDTH
    header = f"STOMP {event.index}/12  sta_lta_ratio={event.sta_lta_ratio:.2f}"
    print(style.bold + rule + style.reset)
    print(style.bold + header + style.reset)
    print(rule)
    print(
        f"  incoming seismic signal   sta_lta_ratio = {event.sta_lta_ratio:.2f}  "
        f"(below trigger gate {STA_LTA_TRIGGER_RATIO:.2f})"
    )
    print(
        f"  {style.yellow}MCU never fires report_footfall_event"
        f" -- nothing reaches the MPU{style.reset}"
    )
    print("  a genuine sub-threshold human stomp, not a system fault -- docs/KNOWN_GAPS.md")
    print()


def _print_summary(style: _Style, alert_count: int, detected_count: int) -> None:
    rule = "=" * _WIDTH
    print(style.bold + rule + style.reset)
    print(
        f"{detected_count}/12 stomps crossed the MCU trigger gate "
        "(matches the real 2026-08-15 run: 11/12, 91.7%)"
    )
    print(
        f"{alert_count}/{detected_count} MCU triggers reached fuse()/decide() and alerted "
        "(matches real run: 11/11)"
    )
    print(rule)


# ---------------------------------------------------------------------------
# Acoustic routing pass (pass 2) -- narrative printing
# ---------------------------------------------------------------------------


class _LogCapture(logging.Handler):
    """Collect fully-formatted messages from services.reflex_loop's own logger.

    Used only by pass 2, to print the real [SAFE_MODE] gunshot alert line
    handle_acoustic_event() actually logs, rather than re-typing it here and
    risking drift from the real string.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@contextmanager
def _capturing_reflex_log():
    """Yield a list that fills with services.reflex_loop's INFO log lines.

    demo_replay.py configures no logging of its own, so reflex_loop.logger's
    logger.info() calls are silently dropped by the root default (WARNING)
    outside this context. Adds a handler and raises the level for the
    duration only, and always restores level/propagate on exit -- a replay
    should leave no global logging state behind it.
    """
    handler = _LogCapture()
    previous_level = reflex_loop.logger.level
    previous_propagate = reflex_loop.logger.propagate
    reflex_loop.logger.addHandler(handler)
    reflex_loop.logger.setLevel(logging.INFO)
    reflex_loop.logger.propagate = False
    try:
        yield handler.lines
    finally:
        reflex_loop.logger.removeHandler(handler)
        reflex_loop.logger.setLevel(previous_level)
        reflex_loop.logger.propagate = previous_propagate


def _print_acoustic_header(style: _Style) -> None:
    rule = "=" * _WIDTH
    print(style.bold + rule + style.reset)
    print(style.bold + "PASS 2 -- acoustic routing (ADR 0007 5), illustrative" + style.reset)
    print(rule)
    print(
        "unlike pass 1 above, this is NOT captured bench data: no acoustic classifier "
        "runs on the MCU yet, so there is nothing real to replay."
    )
    print(
        f"every class below uses one fixed synthetic confidence = "
        f"{ILLUSTRATIVE_ACOUSTIC_CONFIDENCE:.2f} -- only the input is synthetic; the "
        "routing and every printed number below come from the real handle_acoustic_event()"
    )
    print("pipeline: services.reflex_loop.handle_acoustic_event()")
    print()


def _print_acoustic(
    class_label: AcousticClass,
    outcome: reflex_loop.AcousticOutcome,
    first_fused_p: float | None,
    log_lines: list[str],
    style: _Style,
) -> None:
    rule = "-" * _WIDTH
    header = f"ACOUSTIC  class_label={class_label.value}"
    print(style.bold + rule + style.reset)
    print(style.bold + header + style.reset)
    print(rule)
    print(
        f"  incoming acoustic classification   class = {class_label.value}   "
        f"confidence = {ILLUSTRATIVE_ACOUSTIC_CONFIDENCE:.3f}  (illustrative, not captured)"
    )

    if outcome.fusion is None:
        print(
            f"  {style.yellow}route: direct anti-poaching alert -- never reaches fuse()"
            f"{style.reset}"
        )
        print(
            f"  {style.yellow}outcome.fusion is None -- never fused, not the same as a "
            f"FusionResult with acoustic unavailable{style.reset}"
        )
        print("  the alert line this event actually logged:")
        for line in log_lines:
            print(
                textwrap.fill(
                    line, width=_WIDTH - 4, initial_indent="    ", subsequent_indent="    "
                )
            )
        print()
        return

    fusion = outcome.fusion
    if Modality.ACOUSTIC in fusion.used:
        contribution = fusion.contributions[Modality.ACOUSTIC]
        print(
            f"  sense -> fuse             acoustic contribution = {contribution:+.3f}  "
            "(seismic/vision unavailable, dropped)"
        )
        print(f"                            fused log-odds L    = {fusion.log_odds:+.3f}")
        fused_p = f"{style.green}{fusion.probability:.3f}{style.reset}"
        print(f"  fuse                      fused P(elephant)   = {fused_p}")
        if first_fused_p is not None:
            print(
                f"  {style.dim}identical to the first fusing class's fused P "
                f"({first_fused_p:.3f}) -- one shared ACOUSTIC modality "
                f"(WEIGHT_ACOUSTIC/BASELINE_ACOUSTIC), not three (ADR 0007 5){style.reset}"
            )
        print(
            f"  {style.dim}no decide() and no actuation on this path -- acoustic is "
            f"corroboration only, and fuse() is stateless per event{style.reset}"
        )
    else:
        print(
            f"  {style.dim}route: fused as unavailable -- excluded from the sum, not "
            f"scored as negative evidence (INVENTED mapping, ADR 0007 never routes "
            f"ambient){style.reset}"
        )
        print(f"  dropped = {[m.value for m in fusion.dropped]}")
        fused_p = f"{style.dim}{fusion.probability:.3f}{style.reset}"
        print(f"  fuse                      fused P(elephant)   = {fused_p}  (prior alone)")
        print(
            f"  {style.dim}Modality.ACOUSTIC not in outcome.fusion.contributions -- "
            f"excluded, not scored as a zero{style.reset}"
        )
    print()


def _print_acoustic_summary(style: _Style) -> None:
    rule = "=" * _WIDTH
    print(style.bold + rule + style.reset)
    print(
        "5 classes, 3 routes (ADR 0007 5): gunshot bypasses fuse() entirely; "
        "chainsaw/vehicle/animal_call fuse as one shared ACOUSTIC modality; "
        "ambient fuses as unavailable."
    )
    print(
        f"every input above used one fixed synthetic confidence "
        f"({ILLUSTRATIVE_ACOUSTIC_CONFIDENCE:.2f}) -- illustrative, NOT captured bench data, "
        "unlike the seismic replay above it (real 2026-08-15 hardware capture)."
    )
    print(
        "the routing itself is real: handle_acoustic_event() was actually called for each "
        "class above -- only the inputs are synthetic."
    )
    print(rule)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> int:
    """Run pass 1 (REPLAY_EVENTS) then pass 2 (every AcousticClass). Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--interval",
        type=float,
        default=1.5,
        help="Seconds to pause between events, for demo pacing (default: 1.5; 0 = run flat out)",
    )
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI styling")
    args = parser.parse_args()

    style = _Style(enabled=(not args.no_color) and sys.stdout.isatty())

    _print_banner(style)
    time.sleep(args.interval)

    # In-memory, never the real path -- see module docstring.
    experience = ExperienceStore(IN_MEMORY_PATH)

    detected_count = 0
    alert_count = 0
    for event in REPLAY_EVENTS:
        if not event.detected:
            _print_miss(event, style)
            time.sleep(args.interval)
            continue

        detected_count += 1
        probability = mcu_probability(event.sta_lta_ratio)
        outcome = reflex_loop.handle_footfall_event(
            services_config.SCHEMA_VERSION,
            probability,
            sta_lta_ratio=event.sta_lta_ratio,
            feature_vector=[0.0] * 8,  # not consumed by fuse() -- see module docstring
            drive_horn=_never_called("drive_horn"),
            drive_led=_never_called("drive_led"),
            pulse_ir=_never_called("pulse_ir"),
            camera=_NoOpCamera(),
            save_frames=_never_called("save_frames"),
            experience=experience,
            safe_mode=True,
        )
        if outcome.decision.alert:
            alert_count += 1
        _print_detected(event, outcome, probability, style)
        time.sleep(args.interval)

    _print_summary(style, alert_count, detected_count)
    experience.close()

    _print_acoustic_header(style)
    time.sleep(args.interval)

    # First fusing class's fused P, so later fusing classes can show they
    # land on the identical value -- see _print_acoustic()'s docstring note.
    first_fused_p: float | None = None
    for class_label in AcousticClass:
        with _capturing_reflex_log() as log_lines:
            outcome = reflex_loop.handle_acoustic_event(
                services_config.SCHEMA_VERSION,
                class_label,
                ILLUSTRATIVE_ACOUSTIC_CONFIDENCE,
                ILLUSTRATIVE_CAPTURE_REF,
                send_lora_alert=_never_called("send_lora_alert"),
                safe_mode=True,
            )
        _print_acoustic(class_label, outcome, first_fused_p, log_lines, style)
        if (
            first_fused_p is None
            and outcome.fusion is not None
            and Modality.ACOUSTIC in outcome.fusion.used
        ):
            first_fused_p = outcome.fusion.probability
        time.sleep(args.interval)

    _print_acoustic_summary(style)
    return 0


if __name__ == "__main__":
    sys.exit(main())
