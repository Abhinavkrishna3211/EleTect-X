#!/usr/bin/env bash
# Periodic on-board encounter-clip assembly for the EleTect-X home-test
# deployment.
#
# Why this exists: HOME_TEST_MODE writes each qualifying detection as a
# JPEG burst under python/data/home_test/encounters/<timestamp>/, not a
# video file (EVENT_VIDEO_ENABLED stays False). This unit periodically
# converts any not-yet-assembled burst into clip.mp4 inside the same
# directory, using the already-running app container's own opencv/ffmpeg
# support - see bench/camera_check/assemble_encounters_onboard.py for the
# encoder itself and its disk/CPU-safety reasoning. --limit keeps each
# firing small so this never competes hard with the live detection loop
# for CPU; nice keeps it low priority whenever there is contention.
#
# Installed as a systemd --user unit (no sudo on this box),
# alongside eletect-x-boot-reassert.service; relies on the same
# `loginctl enable-linger arduino` already in place.
#
# Robustness (10 Sept, field-trial run #1): the encoder once wedged for
# ~28 min and, because the systemd unit has no start timeout, blocked the
# timer from ever re-firing - no further encounters would have been
# assembled for the rest of an unattended trial. Two guards now:
#   1. any assembler still running in the container from a previous firing
#      is killed before this one starts (a wedged run must not accumulate);
#   2. the encoder runs under an in-container `timeout`, so a hang
#      self-terminates and frees the systemd job even if `docker exec` does
#      not forward the signal.
set -eu

CONTAINER=eletect-x-main-1
SCRIPT=/app/bench/camera_check/assemble_encounters_onboard.py
RUN_MAX_S=720

# Guard 1: clear any stale/wedged assembler from a previous firing.
if docker exec "${CONTAINER}" pgrep -f "assemble_encounters_onboard" >/dev/null 2>&1; then
    echo "assemble: a previous run is still in the container - killing it before starting"
    docker exec "${CONTAINER}" pkill -9 -f "assemble_encounters_onboard" || true
    sleep 2
fi

# Guard 2: hard wall-clock cap inside the container.
exec docker exec "${CONTAINER}" \
    timeout --signal=KILL "${RUN_MAX_S}" \
    nice -n 19 python3 "${SCRIPT}" --limit 3
