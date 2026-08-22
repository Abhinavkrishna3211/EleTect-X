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
- Fusion weights, bandit hyperparameters, and risk thresholds. Those live in
  cognition/config.py, not in this bridge-facing config.

Camera device path, resolution, and pixel format DO belong here even though
they're perception/-facing, not bridge-facing - they're device-configuration
constants in the same sense as the MCU's pin assignments (config.h), not
tuning knobs for cognition math.
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
# on the board (ArduinoApps/<app>/python/), not /tmp or a path that only
# exists on a dev laptop.

_MODULE_DIR = Path(__file__).resolve().parent.parent

# SQLite experience store backing the contextual bandit's never-repeat /
# stop-on-retreat learning (CONTEXT.md 4). Opened lazily by
# cognition/experience.py, which creates DATA_DIR on first write; only the
# path is fixed here. Tests and bench/demo_replay.py inject their own path
# (a tmp_path, or cognition.experience.IN_MEMORY_PATH) so neither ever
# writes real learning state.
DATA_DIR = _MODULE_DIR / "data"
EXPERIENCE_DB_PATH = DATA_DIR / "experience.sqlite3"

# On-device vision model artifacts (Edge Impulse export target).
MODELS_DIR = _MODULE_DIR / "models"

# ---------------------------------------------------------------------------
# Camera (perception/camera.py, IMX462 over USB-UVC)
# ---------------------------------------------------------------------------
# Capture-only constants. No trigger/IR-sync values here - pulse_ir() is an
# MCU-side Bridge call not registered on either side yet
# (device/mpu/bridge/rpc.py), and capture has no business calling it.

# Verified on real hardware 17 Aug 2026 (docs/KNOWN_GAPS.md): a bare index
# is not safe here. /dev/video0 - the previous default - turned out to be
# the QRB2210 SoC's own qcom-venus hardware encoder, not the camera at all;
# the IMX462 actually landed on /dev/video1 that run, but /dev/videoN
# indices reshuffle across reboots and hub reconnects/port changes, so even
# that number isn't trustworthy long-term. Using the udev-assigned by-id
# symlink instead - keyed on the camera's own USB serial (SN0001), not bus
# topology or enumeration order. Confirmed 17 Aug 2026: a full board reboot
# genuinely reshuffled the raw /dev/videoN indices under this camera (it
# held video1/2/4/5 before, video0/1/2/3 after - the SoC's own qcom-venus
# codec and the camera raced differently on the two boots), and a physical
# USB unplug/replug reassigned the bus device number too - the by-id path
# resolved correctly both times with zero code changes. See
# docs/KNOWN_GAPS.md for the full verification.
CAMERA_DEVICE = (
    "/dev/v4l/by-id/usb-Arducam_Technology_Co.__Ltd._USB_2.0_Camera_SN0001-video-index0"
)

# IMX462 is a 2MP sensor; 1920x1080 taken from the product listing
# (B0CQ4QDCXN), not from a queried V4L2 format list on this specific unit.
# UNVERIFIED - bench/camera_check's --probe flag closes this.
CAMERA_FRAME_WIDTH = 1920
CAMERA_FRAME_HEIGHT = 1080

# MJPG, not YUYV: most 1080p UVC webcams only sustain a useful frame rate
# over USB2/3 in MJPG - YUYV's uncompressed bandwidth typically caps near
# 5 fps at this resolution. UNVERIFIED for this specific unit (product
# listing doesn't state it) - bench/camera_check's --probe flag confirms
# which formats this camera actually offers.
CAMERA_PIXEL_FORMAT = "MJPG"

# UVC auto-exposure/AGC needs several frames after stream start before
# output is representative - the first few grabs after open() are commonly
# dark, over-bright, or otherwise unsettled. INVENTED - no AE-settle bench
# data backs this number yet; see docs/KNOWN_GAPS.md.
CAMERA_WARMUP_FRAMES = 3

# Camera.open() retry policy. A transient USB dropout at exactly the moment
# of open() (hub renegotiation, a jostled connector) shouldn't be a hard
# failure if the device comes back within a couple seconds - confirmed
# empirically 17 Aug 2026 that a real unplug/replug of this camera took
# ~8.6s to re-enumerate (dmesg: USB disconnect to new-device back-to-back),
# see docs/KNOWN_GAPS.md. Open (not capture_frame()/capture_burst(), which
# stay non-retrying by design - see their own docstrings) because a device
# that isn't there yet at startup is exactly the case a few spaced attempts
# can ride out. INVENTED counts - no real-world open-failure-rate data
# backs these numbers yet.
CAMERA_OPEN_RETRIES = 3
CAMERA_OPEN_RETRY_BACKOFF_S = 2.0

# Default burst size and inter-frame spacing for capture_burst(). 0.0
# interval means "as fast as the device delivers," not a real-time target.
# Both INVENTED - no detector-side timing requirement drives these yet.
CAMERA_BURST_FRAMES = 5
CAMERA_BURST_INTERVAL_S = 0.0

# ---------------------------------------------------------------------------
# Deterrent-event capture storage (perception/storage.py)
# ---------------------------------------------------------------------------
# Where reflex_loop.py's alert-path frame burst gets written, tagged with the
# triggering event's own metadata. Module-relative like DATA_DIR/MODELS_DIR
# above, for the same reason - lands inside the App's own folder on the
# board, not /tmp.
CAPTURE_DIR = _MODULE_DIR / "data" / "captures"

# perception/storage.py logs a warning (never fails silently, per
# ENGINEERING_CONVENTIONS.md 3's zero-filled-read precedent for "degrade
# loudly, don't go silent") when free space at CAPTURE_DIR drops below this.
# INVENTED - no measured field JPEG-size/trigger-frequency data backs this
# number yet; picked as a conservative "still room for hundreds more bursts"
# floor against the real board's ~3.6GB usable /home/arduino partition
# (.agents/skills/build-arduino-uno-q-app-lab/references/REFERENCE.md), not
# a tuned figure. See docs/KNOWN_GAPS.md.
CAPTURE_LOW_DISK_HEADROOM_BYTES = 500 * 1024 * 1024  # 500 MB

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# INFO by default: quiet enough for continuous field operation, verbose
# enough to see wake/event/Bridge activity on the bench without extra
# configuration.
LOG_LEVEL = "INFO"
