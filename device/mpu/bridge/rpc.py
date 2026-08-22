"""Bridge RPC function stubs, one per row of device/mpu/bridge/schema.md.

Signatures and docstrings only - no `Bridge.provide()` or `Bridge.call()`
wiring. `DEVICE_DEVELOPMENT_WORKFLOW.md` 3 documents a live, reproducible
bug where registering an extra `Bridge.provide()` function (a float-argument
one specifically) broke every previously-working function on the same
sketch; the practical discipline that earns is registering one function at
a time on real hardware, testing between each addition - not wiring a batch
of eight from a host build with no board attached. The MCU side observes
the same caution (device/mcu/src/main.cpp).

This module must stay importable with no board attached: `arduino.app_utils`
(the module that provides `Bridge`) only exists on the QRB2210's own Python
install, and importing it at module scope here would break
`tests/test_rpc_contract.py`, which runs on a dev laptop
(ENGINEERING_CONVENTIONS.md 1/4).

Two Bridge primitives, per schema.md's own header:
`Bridge.call(name, args) -> return_value` is synchronous request/response -
the caller blocks until a response or timeout. `Bridge.notify(name, args)`
is fire-and-forget - no return value, caller never blocks. The MCU→MPU
functions below are notify targets (the MCU must not stall on MPU wake
state); the MPU→MCU functions are call wrappers (the MPU needs to know the
action actually executed before deciding what happens next).
"""

from dataclasses import dataclass
from enum import Enum

# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


class AcousticClass(str, Enum):
    """Classifier output label for `report_acoustic_event`.

    Values match schema.md's `class_label` enum literally - the MCU sends
    one of these five strings, not a raw integer index.
    """

    GUNSHOT = "gunshot"
    CHAINSAW = "chainsaw"
    VEHICLE = "vehicle"
    ANIMAL_CALL = "animal_call"
    AMBIENT = "ambient"


@dataclass(frozen=True)
class SystemState:
    """Return shape of `get_system_state`.

    Identical to the struct `report_system_status` pushes periodically
    (schema.md: "same struct").
    """

    battery_v: float
    geophone_ok: bool
    acoustic_ok: bool
    uptime_s: int


# ---------------------------------------------------------------------------
# MCU -> MPU (STM32 notifies; MPU provides the handler)
# ---------------------------------------------------------------------------


def report_footfall_event(
    schema_version: int,
    probability: float,
    sta_lta_ratio: float,
    feature_vector: list[float],
) -> None:
    """Handle one geophone STA/LTA trigger crossing the footfall confidence gate.

    Bridge target: `notify` (fire-and-forget, MCU never blocks on this).
    Fires once per crossing that also clears the on-MCU EI footfall model's
    confidence gate (schema.md). If the MPU is suspended, this call is what
    triggers wake (ADR 0008) - Bridge's own reconnect/queue behavior handles
    the transport, this function only handles the payload once delivered.

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        probability: On-MCU footfall model's confidence, 0-1.
        sta_lta_ratio: STA/LTA ratio at the moment of trigger.
        feature_vector: The 8 features the on-MCU model computed the
            probability from.

    Returns:
        None - this is a notify target, the MCU does not read a return
        value.
    """
    raise NotImplementedError


def report_acoustic_event(
    schema_version: int,
    class_label: AcousticClass,
    confidence: float,
    capture_ref: int,
) -> None:
    """Handle one acoustic classifier event (on-MCU classifier or comparator-gated burst).

    Bridge target: `notify`. Fires once per on-MCU acoustic classifier
    crossing its confidence threshold (ADR 0009 primary path) or once per
    comparator-gated burst classification (ADR 0006 fallback) - same event
    shape either way (schema.md). Gunshot routes to a direct LoRa alert,
    bypassing elephant-presence fusion entirely (ADR 0007 5) - that
    routing is MPU-side logic this function is the entry point for, not
    implemented here.

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        class_label: One of AcousticClass.
        confidence: Classifier confidence, 0-1.
        capture_ref: Index into MCU SRAM's raw-window ring buffer, so the
            MPU can pull the raw audio via `read_acoustic_window()` if it
            wants more than the label. Indexing scheme not yet designed
            (schema.md "Open items").

    Returns:
        None - this is a notify target, the MCU does not read a return
        value.
    """
    raise NotImplementedError


def report_system_status(
    schema_version: int,
    battery_v: float,
    geophone_ok: bool,
    acoustic_ok: bool,
    lora_joined: bool,
    uptime_s: int,
) -> None:
    """Handle one periodic heartbeat from the MCU.

    Bridge target: `notify`. Fires on a slow periodic timer (proposed:
    every 10 minutes, SYSTEM_STATUS_PERIOD_MS in device/mcu/include/
    config.h), independent of any trigger, so the dashboard has a liveness
    signal through quiet periods. A missed status for >2x the period is the
    stale-node signal - that logic lives in web/backend, not here
    (schema.md).

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        battery_v: Battery rail voltage.
        geophone_ok: False if the last geophone read timed out or the
            window went stale.
        acoustic_ok: Same contract as geophone_ok, for the acoustic path.
        lora_joined: Whether the LoRaWAN OTAA join has succeeded.
        uptime_s: Seconds since MCU boot.

    Returns:
        None - this is a notify target, the MCU does not read a return
        value.
    """
    raise NotImplementedError


# ---------------------------------------------------------------------------
# MPU -> MCU (MPU calls; STM32 provides the handler)
# ---------------------------------------------------------------------------


def drive_horn(schema_version: int, gain_pct: float, duration_ms: int) -> bool:
    """Request a horn deterrence burst.

    Bridge target: `call` (synchronous, blocks up to
    services.config.BRIDGE_CALL_TIMEOUT_S). The MCU enforces its own
    burst-duration cap and cooldown (ADR 0003) regardless of what is
    requested - an out-of-bounds request is clamped, not rejected, and the
    returned ack reports that the (possibly clamped) values were used, not
    what was asked for (schema.md). Not idempotent - never retried on
    timeout (services.config.BRIDGE_ACTUATOR_CALL_RETRIES).

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        gain_pct: Requested output level, 0-100. Clamped to
            HORN_GAIN_MAX_PCT on the MCU side if out of bounds.
        duration_ms: Requested burst duration. Clamped to HORN_BURST_MAX_MS
            on the MCU side if out of bounds; refused outright (ack=False)
            if the horn is still in its cooldown window.

    Returns:
        True if the horn fired (with clamped values applied). False if the
        request was refused because the actuator is in cooldown. Never
        raises on a GPIO-level fault - the MCU logs it and still acks
        (schema.md: "always returns/acks even on a GPIO-level fault").
    """
    raise NotImplementedError


def drive_led(schema_version: int, pattern_id: int, duration_ms: int) -> bool:
    """Request an LED deterrence burst.

    Bridge target: `call`. Same cooldown/cap discipline as drive_horn, with
    independent counters (schema.md). Not idempotent - never retried on
    timeout.

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        pattern_id: Which strobe pattern to run; MCU-side defined.
        duration_ms: Requested burst duration. Clamped to LED_BURST_MAX_MS
            on the MCU side if out of bounds; refused outright (ack=False)
            if the LED actuator is still in its cooldown window.

    Returns:
        True if the LEDs fired (with clamped values applied). False if the
        request was refused because the actuator is in cooldown.
    """
    raise NotImplementedError


def pulse_ir(schema_version: int, duration_ms: int) -> bool:
    """Request an IR illuminator pulse for night capture.

    Bridge target: `call`. Gated by the IR MOSFET's own thermal/duty
    limits (device/mcu/include/config.h); an over-duration request clamps,
    and the clamp is reported in the ack, never silently dropped
    (schema.md). Not idempotent - never retried on timeout.

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        duration_ms: Requested pulse duration. Clamped to IR_PULSE_MAX_MS
            on the MCU side if out of bounds; refused outright (ack=False)
            if still inside IR_MIN_INTERVAL_MS of the last pulse.

    Returns:
        True if the illuminator pulsed (with clamped duration applied).
        False if the request was refused because the minimum interval
        since the last pulse has not elapsed.
    """
    raise NotImplementedError


def get_system_state(schema_version: int) -> SystemState:
    """Read the MCU's last-known system state.

    Bridge target: `call`, retried up to
    services.config.BRIDGE_STATE_CALL_RETRIES times on timeout - this is a
    cached-struct read, not a fresh sensor poll, so it is idempotent and
    safe to retry (schema.md: "Never blocks past one cached-struct read").

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.

    Returns:
        The same struct report_system_status pushes periodically:
        battery_v, geophone_ok, acoustic_ok, uptime_s. Never blocks past
        one cached-struct read on the MCU side.
    """
    raise NotImplementedError


def send_lora_alert(schema_version: int, confidence: float, capture_ref: int) -> bool:
    """Request a direct gunshot alert uplink (ADR 0007 5's anti-poaching path).

    Bridge target: `call` (synchronous, blocks up to
    services.config.BRIDGE_CALL_TIMEOUT_S). Not idempotent - never retried
    on timeout (services.config.BRIDGE_ACTUATOR_CALL_RETRIES): retrying a
    timed-out call would risk sending a duplicate alert, not just a
    duplicate request.

    No real LoRa transport exists on the MCU side yet - the Grove E5 module
    is not answering AT probes (docs/KNOWN_GAPS.md, 18 Aug entry), so the
    MCU-side handler only logs the request and always returns False. A True
    ack, once the module joins, would still mean "queued/logged on the
    MCU", never "delivered over the air" - schema.md's own wording for this
    row.

    Args:
        schema_version: Wire schema version; must equal SCHEMA_VERSION.
        confidence: Classifier confidence, 0-1, as reported by
            report_acoustic_event.
        capture_ref: Index into the MCU's raw-window ring buffer.

    Returns:
        True if the MCU queued/logged the alert. False today, always - no
        real transport exists for it to queue into yet.
    """
    raise NotImplementedError
