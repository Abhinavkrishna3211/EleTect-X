#!/usr/bin/env bash
# Pin the app's deterrent-fire log lines to a file on the bind mount.
#
# Why this exists: the running app logs "drive_horn ack=True",
# "drive_led ack=True", "pulse_ir ack=True" and the home_test encounter-fire
# lines to stdout only, with no timestamp (main.py's logging.basicConfig
# sets no format string). `docker logs` is therefore the only source of
# these events, and it is lost the instant the container is recreated - App
# Lab regenerating app-compose.yaml, a --force-recreate, an image change -
# and it also rotates (json-file, max-size 5m x2 on this box).
#
# This tap appends any new fire line, prefixed with `docker logs -t`'s
# RFC3339 timestamp, to a file under python/data/home_test/. That path is on
# the host bind mount, so it survives container recreate and power cycles.
# bench/camera_check/assemble_encounters_onboard.py reads it on retrieval to
# burn the red DETERRENT FIRING banner onto clip_annotated.mp4 at the exact
# frames a deterrent fired.
#
# Idempotent: each run re-reads an overlapping --since window; the assembler
# drops exact-duplicate lines and clusters near-simultaneous events. Safe to
# run every few minutes from cron next to eletect-x-watchdog.sh. Fire lines
# are tiny and only appear during an encounter, so the file stays small with
# no rotation of its own.
set -eu

CONTAINER=eletect-x-main-1
OUT="${HOME}/ArduinoApps/eletect-x/python/data/home_test/fire_events.log"
SINCE="20m"

mkdir -p "$(dirname "${OUT}")"

docker logs -t --since "${SINCE}" "${CONTAINER}" 2>&1 \
  | grep -E 'drive_horn ack=True|drive_led ack=True|pulse_ir ack=True|home_test: encounter started|re-firing \(fire ' \
  >> "${OUT}" 2>/dev/null || true

exit 0
