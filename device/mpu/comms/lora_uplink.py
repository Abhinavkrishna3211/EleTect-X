# LoRaWAN event uplink, MPU half (ADR 0031).
#
# The MCU owns the radio: it queues frames, joins, sends, retries and waits
# for the ACK (device/mcu/src/mac.cpp). What only this side knows is what an
# event *was* - whether the camera confirmed it, which tier the bandit chose,
# whether a deterrent actually fired - so this module turns a finished
# FootfallOutcome (or a gunshot) into send_lora_event's six scalars and
# hands them to the MCU over the Bridge.
#
# It runs on its own thread for the same reason the acoustic poll does
# (main.py): a Bridge.call that stalls must never hold up the next
# report_footfall_event, and a radio problem must never be what delays a
# deterrent. submit() only puts the event on a bounded queue and returns.
#
# Nothing here imports arduino.app_utils. The call function is injected -
# main.py binds Bridge.call - so the module is testable on a laptop.

from __future__ import annotations

import logging
import queue
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol

logger = logging.getLogger(__name__)

SEND_LORA_EVENT = "send_lora_event"

# Flag bits, byte 5 of the event frame. Wire values - device/mcu/src/uplink.h
# and web/ingest/src/payload.ts carry the same three.
FLAG_VISION_CONFIRMED = 0x01
FLAG_DETERRENT_FIRED = 0x02
FLAG_SAFE_MODE = 0x04


class EventClass(IntEnum):
    """What the node saw. Wire values - append only, never renumber."""

    UNCONFIRMED = 0
    ELEPHANT = 1
    BOAR = 2
    GUNSHOT = 3
    CHAINSAW = 4


# Vision label -> event class, for the labels a node may deter on
# (services/config.py DETERRENT_TARGET_LABELS).
_LABEL_CLASS = {"Elephant": EventClass.ELEPHANT, "Boar": EventClass.BOAR}


@dataclass(frozen=True)
class LoraEvent:
    """send_lora_event's arguments after schema_version, in wire order.

    Attributes:
        event_class: What was seen.
        confidence: Fused probability (or classifier confidence), 0-1. The
            MCU clamps and rounds it to a whole percent.
        tier: Deterrence tier that ran, 0 when nothing was selected.
        flags: FLAG_* bits.
        capture_ref: Links the uplink back to the local record; 0 when there
            is none.
    """

    event_class: EventClass
    confidence: float
    tier: int
    flags: int
    capture_ref: int = 0


class _Fusion(Protocol):
    probability: float


class _Decision(Protocol):
    alert: bool


class _Action(Protocol):
    tier: int


class FootfallOutcomeLike(Protocol):
    """The FootfallOutcome fields this module reads (services/reflex_loop.py)."""

    fusion: _Fusion
    decision: _Decision
    action: _Action | None
    horn_ack: bool | None
    led_ack: bool | None
    vision_confirmed: bool
    suppressed_by_vision: bool


def confirmed_class(target_labels: Sequence[str]) -> EventClass:
    """Class to report for a vision-confirmed event on this node.

    FootfallOutcome says *that* the camera confirmed a deterrent target,
    not which one. On a node that deters exactly one species that is
    enough. On a node that deters several it is not, and the frame goes out
    as UNCONFIRMED with FLAG_VISION_CONFIRMED set rather than guessing a
    species a ranger would then act on.

    Args:
        target_labels: The node's DETERRENT_TARGET_LABELS.

    Returns:
        The single target's class, or UNCONFIRMED.
    """
    if len(target_labels) == 1:
        return _LABEL_CLASS.get(target_labels[0], EventClass.UNCONFIRMED)
    return EventClass.UNCONFIRMED


def event_from_footfall(
    outcome: FootfallOutcomeLike,
    *,
    safe_mode: bool,
    target_labels: Sequence[str],
    capture_ref: int = 0,
) -> LoraEvent | None:
    """Map a finished footfall event to an uplink, or None if it is not one.

    An event is worth airtime when the camera confirmed a target, or when
    fusion alerted and vision did not overrule it. A trigger that fusion
    dismissed stays local - IN865 duty cycle is too scarce to spend on
    every footstep the geophone hears.

    Args:
        outcome: handle_footfall_event's return value.
        safe_mode: Whether the node ran as a dry run, so the dashboard can
            tell "deterrent held back on purpose" from "deterrent failed".
        target_labels: The node's DETERRENT_TARGET_LABELS.
        capture_ref: Local record reference, if the caller has one.

    Returns:
        The event to send, or None.
    """
    alerted = outcome.decision.alert and not outcome.suppressed_by_vision
    if not (alerted or outcome.vision_confirmed):
        return None

    flags = 0
    if outcome.vision_confirmed:
        flags |= FLAG_VISION_CONFIRMED
    if outcome.horn_ack or outcome.led_ack:
        flags |= FLAG_DETERRENT_FIRED
    if safe_mode:
        flags |= FLAG_SAFE_MODE

    return LoraEvent(
        event_class=(
            confirmed_class(target_labels) if outcome.vision_confirmed else EventClass.UNCONFIRMED
        ),
        confidence=float(outcome.fusion.probability),
        tier=int(outcome.action.tier) if outcome.action is not None else 0,
        flags=flags,
        capture_ref=capture_ref,
    )


def gunshot_event(confidence: float, capture_ref: int, *, safe_mode: bool) -> LoraEvent:
    """The direct gunshot alert (ADR 0007 5) as an uplink event."""
    return LoraEvent(
        event_class=EventClass.GUNSHOT,
        confidence=float(confidence),
        tier=0,
        flags=FLAG_SAFE_MODE if safe_mode else 0,
        capture_ref=capture_ref,
    )


class LoraUplink:
    """Hands events to the MCU's uplink queue from a background thread.

    Args:
        call: Bridge.call, or a stand-in: call(name, *args) -> ack.
        schema_version: BRIDGE_SCHEMA_VERSION, sent as the first argument.
        maxsize: Events held while the MCU is slow to answer. Past it the
            new event is dropped and logged - the MCU's own queue is four
            deep, so a backlog here would only ever be sent late.
    """

    def __init__(
        self,
        call: Callable[..., Any],
        schema_version: int,
        *,
        maxsize: int = 8,
    ) -> None:
        """Build the uplink; start() launches the worker thread."""
        self._call = call
        self._schema_version = schema_version
        self._queue: queue.Queue[LoraEvent | None] = queue.Queue(maxsize=maxsize)
        self._thread: threading.Thread | None = None
        self.sent = 0
        self.refused = 0
        self.dropped = 0

    def start(self) -> None:
        """Start the worker thread. Idempotent."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="lora-uplink", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 2.0) -> None:
        """Let queued events drain, then stop the worker. For tests and shutdown."""
        if self._thread is None:
            return
        self._queue.put(None)
        self._thread.join(timeout_s)
        self._thread = None

    def submit(self, event: LoraEvent | None) -> bool:
        """Queue an event for the MCU. Never blocks, never raises.

        Args:
            event: The event, or None (a no-op, so a caller can pass
                event_from_footfall()'s result straight through).

        Returns:
            True if queued.
        """
        if event is None:
            return False
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
            logger.warning("lora uplink: queue full, dropping %s event", event.event_class.name)
            return False
        return True

    def send_now(self, event: LoraEvent) -> bool:
        """Make the Bridge call on the calling thread. The worker uses this.

        Returns:
            The MCU's ack: True when it queued the frame for the radio.
            False on a refusal or any Bridge error - never raises.
        """
        try:
            ack = bool(
                self._call(
                    SEND_LORA_EVENT,
                    self._schema_version,
                    int(event.event_class),
                    float(event.confidence),
                    int(event.tier),
                    int(event.flags),
                    int(event.capture_ref) & 0xFFFFFFFF,
                )
            )
        except Exception as exc:  # noqa: BLE001 - a radio fault must not kill the thread
            logger.warning("lora uplink: %s failed (%s)", SEND_LORA_EVENT, exc)
            ack = False
        if ack:
            self.sent += 1
            logger.info(
                "lora uplink: queued %s conf=%.2f tier=%d flags=0x%02x",
                event.event_class.name,
                event.confidence,
                event.tier,
                event.flags,
            )
        else:
            self.refused += 1
            logger.warning("lora uplink: MCU did not queue %s event", event.event_class.name)
        return ack

    def _run(self) -> None:
        while True:
            event = self._queue.get()
            if event is None:
                return
            self.send_now(event)
