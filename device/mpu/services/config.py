"""MPU-side configuration constants.

Single source of every Bridge timeout, retry policy, and filesystem path the
cognition layer depends on (ENGINEERING_CONVENTIONS.md 2), mirroring the
shape of device/mcu/include/config.h: one rationale comment per constant, no
magic numbers inline in logic files.

Two things this file deliberately does NOT hold:
- Actuator burst caps, cooldowns and gain ceilings. Those are enforced
  on-MCU (device/mcu/include/config.h) and the MPU only ever sees the
  clamped ack, never a raw limit to duplicate here
  (device/mpu/bridge/schema.md).
- Fusion weights, bandit hyperparameters, and risk thresholds. Those belong
  to cognition/ once that module lands, not to this bridge-facing config.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Bridge RPC schema
# ---------------------------------------------------------------------------

# Every Bridge payload's first field (device/mpu/bridge/schema.md). Bump on
# any breaking field change; never reuse a version number.
SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# Bridge.call() timeout and retry policy
# ---------------------------------------------------------------------------
# Bridge.call() blocks the caller until a response or timeout
# (ENGINEERING_CONVENTIONS.md 6). These values only apply to the MPU-side
# wrappers (drive_horn, drive_led, pulse_ir, get_system_state) - MCU-side
# notify handlers never block and have no timeout to set.

# The longest MCU-side actuator burst is LED_BURST_MAX_MS (10_000,
# device/mcu/include/config.h), and drive_* never blocks past the commanded
# duration. 12s covers a legitimate full-length burst plus transport
# overhead without misreading a real in-progress burst as a hung call.
BRIDGE_CALL_TIMEOUT_S = 12.0

# drive_horn/drive_led/pulse_ir are not idempotent: a call that times out
# may have already fired the actuator, so retrying risks doubling a burst
# and defeating the MCU's own cooldown gate. Never retried.
BRIDGE_ACTUATOR_CALL_RETRIES = 0

# get_system_state reads a cached struct (device/mpu/bridge/schema.md: "not
# a fresh sensor poll"), so it is idempotent and safe to retry on a
# transport-level timeout.
BRIDGE_STATE_CALL_RETRIES = 2

# ---------------------------------------------------------------------------
# MPU wake/suspend (ADR 0008)
# ---------------------------------------------------------------------------

# How long the MPU stays awake after the last MCU→MPU event notify before
# it is allowed to re-suspend. INVENTED - no measured suspend/resume
# latency or fusion/decision runtime backs this number yet; ADR 0008 lists
# both as open bench items (docs/KNOWN_GAPS.md).
MPU_WAKE_HOLD_S = 30.0

# ---------------------------------------------------------------------------
# Filesystem paths
# ---------------------------------------------------------------------------
# Resolved relative to this module so they land inside the App's own folder
# on the board (arduino_apps/<app>/python/), not /tmp or a path that only
# exists on a dev laptop.

_MODULE_DIR = Path(__file__).resolve().parent.parent

# SQLite experience store backing the contextual bandit's never-repeat /
# stop-on-retreat learning (CONTEXT.md 4). Created by cognition/ once that
# module lands; only the path is fixed here.
DATA_DIR = _MODULE_DIR / "data"
EXPERIENCE_DB_PATH = DATA_DIR / "experience.sqlite3"

# On-device vision model artifacts (Edge Impulse export target).
MODELS_DIR = _MODULE_DIR / "models"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# INFO by default: quiet enough for continuous field operation, verbose
# enough to see wake/event/Bridge activity on the bench without extra
# configuration.
LOG_LEVEL = "INFO"
