"""Tests for comms/lora_uplink.py - what goes on air, and that it never blocks."""

import threading
from dataclasses import dataclass

import pytest

from comms.lora_uplink import (
    FLAG_DETERRENT_FIRED,
    FLAG_SAFE_MODE,
    FLAG_VISION_CONFIRMED,
    SEND_LORA_EVENT,
    EventClass,
    LoraEvent,
    LoraUplink,
    direct_alert_event,
    event_from_footfall,
    gunshot_event,
    observed_class,
)


@dataclass
class _Fusion:
    probability: float


@dataclass
class _Decision:
    alert: bool


@dataclass
class _Action:
    tier: int


@dataclass
class _Outcome:
    fusion: _Fusion
    decision: _Decision
    action: _Action | None = None
    horn_ack: bool | None = None
    led_ack: bool | None = None
    vision_confirmed: bool = False
    suppressed_by_vision: bool = False
    species: str | None = None


def _outcome(**kw):
    return _Outcome(
        fusion=_Fusion(kw.pop("probability", 0.9)),
        decision=_Decision(kw.pop("alert", True)),
        **kw,
    )


def test_dismissed_trigger_is_not_sent():
    """A trigger fusion did not alert on, with no camera confirmation, stays local."""
    assert event_from_footfall(_outcome(alert=False), safe_mode=False) is None


def test_vision_overruled_alert_is_not_sent():
    """An alert the camera overruled must not reach anyone's phone."""
    out = _outcome(alert=True, suppressed_by_vision=True)
    assert event_from_footfall(out, safe_mode=False) is None


def test_confirmed_elephant_that_was_deterred():
    """The main case: camera-confirmed elephant, tier 2 fired."""
    out = _outcome(
        probability=0.87,
        action=_Action(2),
        horn_ack=True,
        led_ack=False,
        vision_confirmed=True,
        species="Elephant",
    )
    ev = event_from_footfall(out, safe_mode=False, capture_ref=0x01020304)
    assert ev == LoraEvent(
        EventClass.ELEPHANT,
        pytest.approx(0.87),
        2,
        FLAG_VISION_CONFIRMED | FLAG_DETERRENT_FIRED,
        0x01020304,
    )


def test_seismic_only_alert_goes_out_unconfirmed():
    """A fusion alert without the camera is sent, but never labelled a species."""
    ev = event_from_footfall(_outcome(alert=True), safe_mode=True)
    assert ev is not None
    assert ev.event_class is EventClass.UNCONFIRMED
    assert ev.tier == 0
    assert ev.flags == FLAG_SAFE_MODE


def test_confirmation_counts_even_below_threshold():
    """A camera confirmation is sent even if fusion alone stayed under threshold."""
    ev = event_from_footfall(
        _outcome(alert=False, vision_confirmed=True, species="Elephant"), safe_mode=False
    )
    assert ev is not None and ev.event_class is EventClass.ELEPHANT


def test_observed_class_names_what_the_camera_saw():
    """Every registry species gets its own class, whatever else the node deters."""
    assert observed_class("Elephant") is EventClass.ELEPHANT
    assert observed_class("Boar") is EventClass.BOAR
    assert observed_class("Fox") is EventClass.FOX


def test_observed_class_never_guesses():
    """No confirmed label, no species on the frame - this is the fail-safe."""
    assert observed_class(None) is EventClass.UNCONFIRMED
    assert observed_class("Leopard") is EventClass.UNCONFIRMED


def test_multi_species_node_still_names_the_species():
    """The regression D4 exists for: a two-species node used to report UNCONFIRMED.

    confirmed_class() inferred the species from DETERRENT_TARGET_LABELS, so
    a node scoped to both gave up and sent UNCONFIRMED even though the
    watch knew which animal it had seen. The scope is no longer consulted.
    """
    ev = event_from_footfall(
        _outcome(
            alert=True, action=_Action(1), horn_ack=True, vision_confirmed=True, species="Boar"
        ),
        safe_mode=False,
    )
    assert ev is not None
    assert ev.event_class is EventClass.BOAR
    assert ev.flags & FLAG_VISION_CONFIRMED


def test_direct_alert_event_builds_both_poaching_classes():
    """The two classes that reach an officer without fusing (ADR 0033).

    Both carry tier 0: no deterrence runs on either, so there is no tier to
    report, and a non-zero one would read to an officer as a node that had
    tried something.
    """
    assert direct_alert_event("gunshot", 0.95, 7, safe_mode=False) == LoraEvent(
        EventClass.GUNSHOT, pytest.approx(0.95), 0, 0, 7
    )
    assert direct_alert_event("chainsaw", 0.8, 9, safe_mode=False) == LoraEvent(
        EventClass.CHAINSAW, pytest.approx(0.8), 0, 0, 9
    )


def test_direct_alert_event_refuses_a_class_it_cannot_route():
    """An unroutable class is a routing bug upstream, not a field condition.

    Degrading to UNCONFIRMED would put a frame on air that reads to an
    officer as a confirmed sighting of nothing, so this raises instead.
    """
    with pytest.raises(ValueError, match="not a direct-alert acoustic class"):
        direct_alert_event("elephant_call", 0.9, 1, safe_mode=False)


def test_direct_alert_event_carries_safe_mode():
    """A dry run must be distinguishable from a real gunshot at the backend."""
    ev = direct_alert_event("gunshot", 0.95, 7, safe_mode=True)
    assert ev.flags == FLAG_SAFE_MODE


def test_gunshot_event():
    """Gunshots carry their own class and no deterrence tier."""
    ev = gunshot_event(0.95, 7, safe_mode=False)
    assert ev == LoraEvent(EventClass.GUNSHOT, pytest.approx(0.95), 0, 0, 7)


def test_send_now_calls_bridge_with_wire_order():
    """Arguments go out in send_lora_event's order, as plain scalars."""
    calls = []
    up = LoraUplink(lambda *a: calls.append(a) or True, schema_version=4)
    assert up.send_now(LoraEvent(EventClass.ELEPHANT, 0.5, 1, 0x03, 2**32 + 5))
    assert calls == [(SEND_LORA_EVENT, 4, 1, 0.5, 1, 3, 5)]
    assert up.sent == 1


def test_send_now_swallows_bridge_errors():
    """A Bridge failure is counted and logged, never raised."""

    def boom(*_):
        raise TimeoutError("no answer")

    up = LoraUplink(boom, schema_version=4)
    assert up.send_now(gunshot_event(0.9, 0, safe_mode=False)) is False
    assert up.refused == 1


def test_submit_never_blocks_and_drops_past_capacity():
    """With the worker stalled, submit() still returns at once."""
    up = LoraUplink(lambda *_: True, schema_version=4, maxsize=2)
    ev = gunshot_event(0.9, 0, safe_mode=False)
    assert up.submit(ev) and up.submit(ev)
    assert up.submit(ev) is False
    assert up.dropped == 1
    assert up.submit(None) is False


def test_worker_drains_the_queue():
    """Submitted events reach the call function on the worker thread."""
    seen = []
    done = threading.Event()

    def call(*args):
        seen.append(threading.current_thread().name)
        if len(seen) == 2:
            done.set()
        return True

    up = LoraUplink(call, schema_version=4)
    up.start()
    up.submit(gunshot_event(0.9, 1, safe_mode=False))
    up.submit(gunshot_event(0.8, 2, safe_mode=False))
    assert done.wait(2.0)
    up.stop()
    assert seen == ["lora-uplink", "lora-uplink"]
    assert up.sent == 2
