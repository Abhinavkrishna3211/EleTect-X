#!/usr/bin/env bash
# Boot-time compose reassert for the EleTect-X App Lab container.
#
# Why this exists: App Lab's own boot-time app launch (arduino-app-cli.service,
# via arduino-app-cli daemon) regenerates ~/ArduinoApps/eletect-x/.cache/
# app-compose.yaml from its own internal state, the same way `arduino-app-cli
# app restart` does — confirmed reproducible 9 Sept. The regenerated file
# carries no restart policy and none of the ELETECT_*/vision-host overrides
# this deployment depends on. Rather than race or reverse-engineer exactly
# when in the boot sequence that regeneration happens, this unit runs after
# it and unconditionally recreates the container from a protected "golden"
# compose copy (app-compose.golden.yaml, a file App Lab never writes to).
# `docker compose up -d` is idempotent, so if App Lab's own launch already
# happened to produce a matching config this is a no-op.
#
# Installed on the board itself as a systemd --user unit (no sudo available
# on this box); relies on `loginctl enable-linger arduino`
# so user units start on boot without an interactive login session.
set -eu

COMPOSE_DIR="${HOME}/ArduinoApps/eletect-x/.cache"
COMPOSE_FILE="app-compose.golden.yaml"

cd "${COMPOSE_DIR}"
docker compose -f "${COMPOSE_FILE}" -p eletect-x up -d
