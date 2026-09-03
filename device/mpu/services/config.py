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
#
# 1 -> 2 on 2026-09-01 (ADR 0014): drive_led's wire args changed from
# (pattern_id, duration_ms) to (channel, pattern_id, gain_pct, duration_ms) -
# `channel` split out as its own field, `gain_pct` added, `pattern_id`
# restored to meaning "which flash pattern".
#
# 2 -> 3 on 2026-09-01 (ADR 0014 E): drive_led's `channel` value 2 now means
# "both wings, driven together in one blocking call" (was "unrecognized ->
# left"), and `pattern_id` gains 4 = sweep, 5 = pulse both sync, 6 = flicker
# both independent. No field added or removed, but the changed meaning of an
# in-range value is a breaking change. Mirrors device/mcu/src/config.h's
# BRIDGE_SCHEMA_VERSION; both sides must bump together.
#
# 3 -> 4 on 2026-09-02 (ADR 0015): drive_horn gains a trailing `track_id`
# (uint8) field - the DFPlayer content index (AT+PLAYNUM) for this tier's
# sound category, so the horn escalates on *what* it plays, not only how
# loud. A real new wire field, so it bumps the version.
SCHEMA_VERSION = 4

# ---------------------------------------------------------------------------
# Node site attributes (set at commissioning, not sensed)
# ---------------------------------------------------------------------------

# True if this node is sited close enough to permanently-occupied homes that
# the deterrence ladder must never play a siren or firecracker/bang track at
# it - those categories carry a real nuisance/startle cost to residents and,
# for the siren, a published null result against elephants anyway (Hedges &
# Gunaryadi 2010). ADR 0016 Decision A/B: household proximity is orthogonal
# to habituation context (repeat-count governs *how hard* to escalate; this
# governs *which* content categories are eligible). A household-proximity
# node's tier 3 escalates on volume, LED and predator-growl variety, not on
# a new "louder artificial bang" category.
#
# Per-node value: overridden per deployment at commissioning time. False here
# is the safe-for-elephants, worst-case-for-residents default - a node with
# this left at False near homes would be allowed to fire the firecracker
# track, so every real near-home node MUST have this set True during
# commissioning. Not auto-detected: nothing on the device knows where it is.
NODE_HOUSEHOLD_PROXIMITY = False

# ---------------------------------------------------------------------------
# Bridge.call() timeout and retry policy
# ---------------------------------------------------------------------------
# Bridge.call() blocks the caller until a response or timeout
# (ENGINEERING_CONVENTIONS.md 6). These values only apply to the MPU-side
# wrappers (drive_horn, drive_led, pulse_ir, get_system_state) - MCU-side
# notify handlers never block and have no timeout to set.

# drive_* holds the caller for the whole commanded burst: the MCU does not
# ack until the burst finishes, and the deterrence ladder commands the
# uint16 protocol max on every tier (cognition/config.py TIER_DURATION_MS),
# which the MCU then clamps to its own per-actuator cap. So each wrapper
# needs its own timeout set just above *that* actuator's cap plus transport
# overhead - a single shared ceiling (the LED cap + margin) would make a
# hung horn or IR call block the reflex loop several seconds longer than
# that actuator can physically run. The caps are owned by
# device/mcu/src/config.h (HORN_BURST_MAX_MS 3000, LED_BURST_MAX_MS 10_000,
# IR_PULSE_MAX_MS 500); tests/test_config.py fails if any value here stops
# exceeding its cap.
BRIDGE_HORN_CALL_TIMEOUT_S = 5.0
BRIDGE_LED_CALL_TIMEOUT_S = 12.0
BRIDGE_IR_CALL_TIMEOUT_S = 2.0

# Generic ceiling for non-actuator calls (get_system_state), which read a
# cached struct and return at once. Kept under the historical name, equal to
# the longest actuator timeout, so bridge/rpc.py's docstrings and
# tests/test_config.py's drift check still resolve unchanged.
BRIDGE_CALL_TIMEOUT_S = BRIDGE_LED_CALL_TIMEOUT_S

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
# Vision inference (perception/detector.py)
# ---------------------------------------------------------------------------
# The trained .eim artifact runs out-of-process as a standing
# `edge-impulse-linux-runner --run-http-server <port>` HTTP server, not
# embedded via the edge_impulse_linux Python SDK - neither pip nor
# ensurepip exists on this board's Python 3.13.5 image and no sudo
# credential is available to install either (confirmed 28 Aug on the real
# board). See perception/detector.py's own module docstring for the full
# rationale and the live verification against a real image.

# 127.0.0.1, not the LAN address used during the 28 Aug bench verification -
# in production the runner is a same-host companion process to this loop,
# never reachable off-board. Starting/supervising that process
# (boot-persistent, restart-on-crash) is not yet built - tracked in
# docs/KNOWN_GAPS.md, not solved here; main.py assumes it is already
# running by the time an event needs it, and a detect() call against
# nothing listening degrades to VISION unavailable, same as a camera
# failure (perception/detector.py, services/reflex_loop.py).
VISION_INFERENCE_URL = "http://127.0.0.1:1337"

# Per-frame socket timeout for one detect call. Bench-measured
# classification time on the real board was ~20ms (28 Aug, real image over
# the LAN); 2.0s is a generous multiple of that, not a tuned figure -
# INVENTED, the same "bounded deliberately short so a hung call can't hang
# the whole event" reasoning as BRIDGE_CALL_TIMEOUT_S above, just guarding a
# different transport.
VISION_INFERENCE_TIMEOUT_S = 2.0

# How many frames the pre-decision vision check captures, distinct from
# CAMERA_BURST_FRAMES (the larger, IR-lit evidence burst captured only once
# an alert actually fires). INVENTED - a small odd number chosen to give
# the detector more than one chance at a moving animal without adding much
# latency ahead of decide(); no real-world tuning data backs this count
# yet. See docs/KNOWN_GAPS.md.
VISION_CHECK_FRAME_COUNT = 3

# ---------------------------------------------------------------------------
# Vision watch window (ADR 0022, services/reflex_loop.py)
# ---------------------------------------------------------------------------
# A geophone trigger and an elephant in frame are not the same moment, and
# the gap between them is large. The field-validated footfall detection
# range is 140m in natural environments (ADR 0008, Wijayakulasooriya et
# al.), and at a normal walking pace of 1.1-1.7 m/s that leaves 80-140
# seconds between the trigger and the animal reaching the boundary - the
# same arithmetic ADR 0008 used to size the wake budget. The camera sees a
# small fraction of that 140m. So a single VISION_CHECK_FRAME_COUNT burst
# taken two or three seconds after the trigger is, in most of the cases
# that matter, looking at an empty frame and correctly reporting "no
# elephant" about an elephant that is simply still 100m away.
#
# The fix is to keep looking for a bounded window instead of glancing once.
# Two window lengths rather than one, because the cost of watching falls
# almost entirely on the triggers that turn out to be nothing - cattle,
# wind, a vehicle on a nearby track - and those should be paid for cheaply.

# What every trigger gets. Sized to be cheap rather than sufficient: at
# VISION_WATCH_POLL_INTERVAL_S this is roughly eight detection passes
# against the single pass the loop did before, which is a real improvement
# for an animal already inside camera range, without committing the battery
# to a long watch on evidence that has not earned one. INVENTED - no field
# trigger-rate data exists yet to size the false-alarm cost against. Set
# this to 0.0 to restore the pre-ADR-0022 behaviour exactly: the watch
# always runs at least one poll, so a zero window is the old single burst.
VISION_WATCH_BASE_S = 8.0

# What a trigger that has already earned a longer look gets - see
# reflex_loop._watch_length_s for the two qualifying conditions (a repeat
# within the habituation window, or seismic evidence strong enough to clear
# the alert threshold on its own).
#
# 45s is not a guess. ADR 0008 puts the *worst-case* lead time - the same
# 140m covered at an agitated 2.5-3+ m/s rather than a walking pace - at
# 45-65 seconds. Capping the watch at the bottom of that band means the
# fallback fire, the one that happens when the window expires without a
# vision confirmation, still lands before even a fast-moving animal could
# have crossed the geophone's own detection range. A longer window would
# buy more chances at a confirmation and start risking a horn that fires
# after the elephant is already past the thing it was protecting.
VISION_WATCH_EXTENDED_S = 45.0

# Interval between watch polls, measured start-of-poll to start-of-poll.
# The real board classifies at a measured 138ms mean per frame (~5.7 FPS
# end to end across 123 live frames, 29-30 Aug - ml/vision/README.md), so a
# VISION_CHECK_FRAME_COUNT=3 poll costs roughly 0.4s of inference and this
# leaves the rest of each second to the H.264 encoder sharing the same four
# A53 cores. Polling flat out instead would give about five times the
# attempts at a target that takes tens of seconds to cross a 95-degree
# field of view (hardware/cad/enclosure-design-concept.md) - very little
# extra recall for several times the CPU and the power behind it. INVENTED
# as a ratio; the 138ms it is sized against is measured.
VISION_WATCH_POLL_INTERVAL_S = 1.0

# Consecutive polls that return no frames at all before the watch gives up
# and lets the event proceed on seismic alone. A camera that has stopped
# delivering is not going to start again inside this window, and holding
# the deterrence sequence behind a dead device is exactly the failure the
# reflex loop's "vision must never block actuation" rule exists to prevent.
# One empty poll is tolerated because a single dropped frame grab is a
# normal USB event (perception/camera.py); three in a row is a fault.
VISION_WATCH_MAX_EMPTY_POLLS = 3

# ADR 0022 Decision B: the deterrent fires on a vision confirmation, not on
# the fused decision alone.
#
# A geophone trigger says something heavy moved within 140m. It does not say
# an elephant is at the boundary, nor that it is coming this way at all.
# Firing the horn on that alone spends the burst on an animal still deep in
# the forest, and cognition/bandit.py's habituation model is explicit that a
# deterrent firing where it achieves nothing is what teaches an animal to
# ignore it. Waiting for the camera puts the burst at boundary range, at
# something demonstrably there - and it is also the only way an event
# produces footage of anything.
#
# The gate is narrow by construction and only ever engages when vision
# actually had a chance: reflex_loop._vision_could_see() sends a failed
# camera, a dead inference server, and an unilluminated night frame all
# straight back to the seismic decision. That last case is not a corner -
# it is every night event until proactive IR illumination is decided
# (docs/KNOWN_GAPS.md), and without it this constant would silently switch
# the whole system off from dusk to dawn.
#
# What this does NOT gate is warning people. The trigger is still recorded,
# logged and settled on seismic alone. There is no footfall uplink on this
# device yet to hold or release (the LoRa module is not joining -
# docs/KNOWN_GAPS.md), so "seismic warns, vision fires" is today only half
# implemented, and the implemented half is the fire gate.
#
# False restores the pre-ADR-0022 behaviour: fire whenever decide() says
# alert, whatever the camera saw.
DETERRENT_REQUIRES_VISION_CONFIRMATION = True

# ---------------------------------------------------------------------------
# External IR illuminator gating (perception/night.py, services/reflex_loop.py)
# ---------------------------------------------------------------------------
# pulse_ir() only helps when the IMX462's IR-cut filter is out (night): in
# daylight the filter blocks the illuminator's near-IR band before it
# reaches a pixel, so the pulse is spent MOSFET duty budget and battery for
# no image gain. perception/night.frames_are_night() infers the filter state
# from the pre-decision vision-check burst's own colour saturation - a
# mono / IR-cut-open frame reads near-zero mean HSV S, a daylight colour
# frame reads tens of units. A burst whose median mean-S is below this is
# treated as night and the IR pulse is allowed; at or above it, pulse_ir()
# is suppressed for the event (logged, tier otherwise unchanged).
#
# Measured on the real rig (Kothamangalam backyard, 1-2 Sep 2026): a
# genuine night frame read mean S = 0.0; a daylight colour frame read
# S > 30. 12 sits in that gap with margin on both sides. Not a tuned figure
# beyond that separation - see docs/KNOWN_GAPS.md.
NIGHT_SATURATION_THRESHOLD = 12.0

# ---------------------------------------------------------------------------
# Which species this node acts on (services/reflex_loop.py)
# ---------------------------------------------------------------------------
# ETX-V is a two-class detector - perception/detector.py's module docstring
# records the deployed model's labels as ["Boar", "Elephant"] - and the two
# classes are wanted for different things at different times, so they get
# two separate lists rather than one switch.
#
# DETERRENT_TARGET_LABELS is the heavier of the two. A label in here counts
# as a vision confirmation, which means it feeds fuse() as positive
# evidence and, under ADR 0022 Decision B, is what releases the horn. A
# label NOT in here can still be detected, logged and filmed; it just
# cannot fire an actuator.
#
# EVENT_VIDEO_TARGET_LABELS only decides whether an event's recording is
# kept instead of discarded. Keeping footage costs disk and nothing else -
# no horn, no battery, no habituation - so it is the cheap list, and it is
# the right place to start with a new species.
#
# The three configurations worth naming, so the change is one edit:
#
#   1. Elephant only (default, and what the first field trial runs):
#          DETERRENT_TARGET_LABELS = ("Elephant",)
#          EVENT_VIDEO_TARGET_LABELS = ("Elephant",)
#   2. Deter elephants, but collect boar footage - the honest next step,
#      because it produces the evidence for whether boar deterrence is even
#      worth doing before any horn fires at one:
#          DETERRENT_TARGET_LABELS = ("Elephant",)
#          EVENT_VIDEO_TARGET_LABELS = ("Elephant", "Boar")
#   3. Deter both:
#          DETERRENT_TARGET_LABELS = ("Elephant", "Boar")
#          EVENT_VIDEO_TARGET_LABELS = ("Elephant", "Boar")
#
# Config 3 carries a real caveat that config 2 does not, and it is not a
# style objection. The bandit in cognition/bandit.py learns one deterrence
# policy per node, not one per species, and the habituation window
# (ADR 0017) counts triggers without asking what caused them. Deterring
# boar therefore spends the same escalation ladder and the same encounter
# memory that elephant deterrence depends on: a night of boar visits can
# walk the node up to tier 3 and leave an elephant arriving at dawn facing
# an already-habituated response. Nothing here prevents that, and nothing
# in the ADRs has decided it - so config 3 is a deliberate choice to make
# with that trade in view, not a free upgrade. See docs/KNOWN_GAPS.md.
DETERRENT_TARGET_LABELS: tuple[str, ...] = ("Elephant",)
EVENT_VIDEO_TARGET_LABELS: tuple[str, ...] = ("Elephant",)

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
# Trigger-gated event video (ADR 0020, perception/video.py)
# ---------------------------------------------------------------------------
# ADR 0020 records a real video per event to a scratch path, runs the vision
# check against that same live stream, and keeps the file only if the event
# is confirmed - discarded triggers never reach the permanent capture
# directory at all. Everything below sizes that one lifecycle.
#
# What this section deliberately does NOT configure: a continuous rolling
# pre-event buffer. ADR 0020 rejects one outright on power grounds (a
# permanently-running camera and encoder against a solar/battery budget that
# is already baseline-dominated), and that rejection got *stronger*, not
# weaker, when the board's real idle draw turned out to be far above the
# figure the budget was sized on (ADR 0008's 2 Sept addendum). There is no
# constant here to turn one on, by design.

# Master switch, default OFF. The GStreamer pipeline in perception/video.py
# has never been run against the real camera - no live-camera work has been
# done since this was written, and the field power topology it would run
# under (VIN rather than USB-C) has its own unresolved camera-enumeration
# question in docs/KNOWN_GAPS.md. Off means device/mpu/main.py wires the
# existing perception.camera.Camera and the JPEG-burst path exactly as
# before and nothing in perception/video.py is ever constructed, so this
# whole feature is inert until someone flips it with the board in front of
# them.
EVENT_VIDEO_ENABLED = False

# Scratch directory for in-progress recordings, deliberately a subdirectory
# of CAPTURE_DIR rather than /tmp or the container's own root overlay: the
# commit step is an os.replace() of the finished file into CAPTURE_DIR, and
# os.replace is only atomic within a single filesystem. On the board those
# are genuinely different filesystems (CAPTURE_DIR lives on the 18G
# /home/arduino mmcblk0p69; the container's /tmp is the ~1G root overlay),
# so a scratch path outside CAPTURE_DIR would silently degrade the commit
# into a copy-then-delete with a window where a brown-out leaves a
# half-written file in the permanent directory. Leading dot so a directory
# listing of captures shows finished footage only.
EVENT_VIDEO_SCRATCH_DIR = CAPTURE_DIR / ".scratch"

# A raw H.264 Annex-B elementary stream, not a Matroska or MP4 container.
# The original design called for Matroska specifically because an MP4's
# moov atom is written when the file is closed, so a recording cut short -
# which on this board means a 5V brown-out, a documented and observed
# failure (docs/KNOWN_GAPS.md, 2 Sept) - leaves a file no player will
# open. That reasoning turned out to prove too little: on real hardware,
# matroskamux can't be used at all. v4l2h264enc's src pad only ever emits
# byte-stream H.264; matroskamux's sink only accepts avc/avc3. Bridging
# the two needs h264parse, which lives in gstreamer1.0-plugins-bad -
# confirmed absent from the production container and uninstallable there
# (no installation candidate in the pinned Debian snapshot repo, and the
# container user has no root). jpegparse, upstream of the decode, is
# missing from the same package for the same reason, but turned out to be
# unnecessary: jpegdec accepts v4l2src's MJPEG buffers directly.
#
# Dropping the muxer is not a downgrade of the truncation-resilience
# argument, it's a stronger version of it: an elementary stream has no
# header or index to corrupt in the first place, so a brown-out mid-write
# leaves a valid, playable stream missing only its trailing frames -
# "playable up to the crash" without even needing incremental-write
# semantics from a container format to get there. Validated end-to-end on
# the real board (6s bench recording, decoded cleanly via OpenCV/FFmpeg on
# a separate machine) - on USB-C/hub power, not yet under VIN; see
# docs/KNOWN_GAPS.md for the still-open VIN-power camera question.
EVENT_VIDEO_SUFFIX = ".h264"

# Upper bound on how long a recording may run before the keep-or-discard
# decision has to have been made (ADR 0020 Decision B3's "~15-20s"). The
# as-built reflex loop is synchronous and reaches that decision far sooner
# than this - camera open, one VISION_CHECK_FRAME_COUNT burst, one
# detect_vision() call bounded by VISION_INFERENCE_TIMEOUT_S, then fuse()
# and decide(), which are pure functions - so this is not a timer the loop
# waits on. It is the budget those stages must stay inside, checked as an
# invariant in tests/test_config.py rather than enforced by a watchdog
# thread this loop does not need and would have to get right.
#
# Raised from 20.0 to cover ADR 0022's watch window: the loop now keeps
# looking for up to VISION_WATCH_EXTENDED_S before it decides, so the
# budget that decision has to fit inside had to grow with it. The margin
# above the watch length is the camera-open retries and the final
# inference call, which tests/test_config.py checks explicitly.
EVENT_VIDEO_CONFIRM_WINDOW_S = 60.0

# How long to keep recording after the actuator sequence completes on a
# confirmed event - the retreat tail, ADR 0020 Decision B4's "30-60s from
# confirmation". Replaces (does not add to) CAPTURE_POST_FIRE_TAIL_S's 2.0s
# when video recording is active: that 2s tail was sized for a JPEG burst,
# and 2s of video would show the horn firing and nothing after it.
#
# The honest cost, stated plainly because it is a real behaviour change:
# the reflex loop blocks for this whole tail, so a second footfall notify
# arriving during it is queued behind it rather than handled. That is
# already true of the 2s tail; 45s makes it matter. It is one of the
# reasons EVENT_VIDEO_ENABLED defaults to False. INVENTED - no footage
# review backs 45s over 30s or 60s, same as CAPTURE_POST_FIRE_TAIL_S.
EVENT_VIDEO_RETREAT_TAIL_S = 45.0

# Recording resolution and frame rate. 720p rather than the camera's
# CAMERA_FRAME_WIDTH/HEIGHT stills resolution, for the same reason as
# before: the recorder decodes MJPEG in software before encoding H.264,
# and 1080p decode-plus-encode on four A53 cores would compete with the
# vision inference running off the same pipeline. The framerate is not a
# design choice, though - it is measured. GStreamer's v4l2src negotiates
# exact discrete caps and rejects anything the sensor doesn't advertise
# (unlike OpenCV's V4L2 backend elsewhere in this codebase, which snaps
# silently to the nearest supported mode - the two are not interchangeable
# assumptions). Swept on the real board: at 1280x720, 5/10/15/20/25fps all
# fail not-negotiated; only 30fps links. A broader sweep across several
# resolutions found no combination that offers 15fps at all - 30fps is
# this sensor's only mode at any usable size, not a fallback from one.
# 720p30 therefore costs roughly double the software JPEG-decode work the
# original 720p15 figure assumed; no encode-load measurement on this
# board backs the resulting number, so headroom is unverified either way.
EVENT_VIDEO_WIDTH = 1280
EVENT_VIDEO_HEIGHT = 720
EVENT_VIDEO_FRAMERATE = 30

# H.264 target bitrate. ADR 0020 sizes a 60-90s event clip at 10-20MB;
# 2 Mbps lands a 60s clip at ~15MB, inside that range. Kept as an explicit
# constant rather than left to the encoder's default so the storage
# arithmetic in ADR 0020 stays traceable to a number in the code.
# NOT CONFIRMED TAKING EFFECT: a 6s bench recording at this setting
# produced a ~24.8MB file (~33 Mbps effective, ~16x over target).
# extra-controls on v4l2h264enc silently drops unrecognised control
# names rather than erroring, so "video_bitrate" is suspected wrong for
# this board's Venus encoder rather than the encoder ignoring the value
# outright; the real control name hasn't been enumerated (v4l2-ctl is not
# present in the production container). See docs/KNOWN_GAPS.md. Until
# this is resolved, size storage and EVENT_VIDEO_RETREAT_TAIL_S against
# the observed rate, not this constant.
EVENT_VIDEO_BITRATE_BPS = 2_000_000

# How long to wait for the pipeline to flush and finish the file after
# end-of-stream is sent. The recording is a raw H.264 Annex-B elementary
# stream (see EVENT_VIDEO_SUFFIX above) with no container index to
# finalise, so a stuck EOS costs nothing beyond whatever the encoder
# itself has buffered - but a stuck pipeline still must not hold the
# reflex loop open indefinitely, so this timeout bounds the wait rather
# than trusting the encoder to always report done. INVENTED.
EVENT_VIDEO_STOP_TIMEOUT_S = 5.0

# How long a single frame pull off the recording pipeline may block. Sized
# generously against EVENT_VIDEO_FRAMERATE's ~33ms frame interval so a
# momentary encoder stall does not read as a dead camera, and bounded so a
# genuinely dead pipeline degrades to "no frames" (which the reflex loop
# already handles as vision-unavailable) instead of blocking the event.
# INVENTED.
EVENT_VIDEO_FRAME_TIMEOUT_S = 2.0

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

# INFO by default: quiet enough for continuous field operation, verbose
# enough to see wake/event/Bridge activity on the bench without extra
# configuration.
LOG_LEVEL = "INFO"
