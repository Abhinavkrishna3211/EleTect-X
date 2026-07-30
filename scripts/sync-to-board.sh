#!/usr/bin/env bash
# One-directional sync: repo (device/mcu + device/mpu) -> the UNO Q's own App
# Lab app folder. The git monorepo is the source of truth
# (ENGINEERING_CONVENTIONS.md 5) — App Lab's on-board editor is never the
# place changes originate (DEVICE_DEVELOPMENT_WORKFLOW.md 2). Run this after
# every edit, before building/flashing from App Lab or the Arduino App CLI.
#
# Only syncs the real EleTect-X app's sketch/python trees. The disposable
# device/mpu/bench/ping app is deliberately not wired into this script — see
# device/mpu/README.md for its own plain rsync one-liner.
#
# Usage:
#   BOARD_HOST=eletect-x.local APP_NAME=eletect-x scripts/sync-to-board.sh
#
# Defaults match the board name used during App Lab's First Setup wizard
# (DEVICE_DEVELOPMENT_WORKFLOW.md 2) — override if this board was set up
# under a different name.
set -euo pipefail

BOARD_USER="${BOARD_USER:-arduino}"
BOARD_HOST="${BOARD_HOST:-eletect-x.local}"
APP_NAME="${APP_NAME:-eletect-x}"
# arduino-app-cli config get reports the real Apps Directory as
# ~/ArduinoApps (CamelCase) — confirmed on hardware 30 Jul 2026. Neither
# arduino-cli nor App Lab itself expose this path in their own docs, which
# say arduino_apps; that name doesn't exist on the board.
APP_ROOT="/home/${BOARD_USER}/ArduinoApps/${APP_NAME}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCU_DIR="${REPO_ROOT}/device/mcu"
MPU_DIR="${REPO_ROOT}/device/mpu"

echo "==> 1. Sanity: local device/mcu tree present"
[ -d "${MCU_DIR}/src" ] || { echo "   MISSING ${MCU_DIR}/src — aborting"; exit 1; }
[ -f "${MCU_DIR}/src/config.h" ] || { echo "   MISSING config.h — aborting"; exit 1; }
if [ ! -f "${MCU_DIR}/src/secrets.h" ]; then
  echo "   MISSING ${MCU_DIR}/src/secrets.h — copy secrets.h.example and fill in real"
  echo "   OTAA credentials before syncing to a board that needs to join (see the file's"
  echo "   own header comment). Aborting rather than sync a sketch with no LoRa identity."
  exit 1
fi

echo "==> 2. Reachability check: ${BOARD_USER}@${BOARD_HOST}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "${BOARD_USER}@${BOARD_HOST}" true 2>/dev/null; then
  echo "   Cannot reach ${BOARD_USER}@${BOARD_HOST} over SSH."
  echo "   Confirm the board is in Network Mode on the same Wi-Fi, and that"
  echo "   passwordless SSH (ssh-copy-id) or an agent key is set up — this script"
  echo "   does not prompt for a password."
  exit 1
fi

echo "==> 3. Ensure app skeleton exists on the board (${APP_ROOT})"
ssh "${BOARD_USER}@${BOARD_HOST}" "mkdir -p '${APP_ROOT}/sketch' '${APP_ROOT}/python' '${APP_ROOT}/assets'"

echo "==> 4. rsync src/ -> sketch/ (one-directional, deletes files removed locally)"
# --delete keeps the board's sketch/ an exact mirror of src/ so a file removed
# in the repo does not linger on the board as stale dead code. hostshim/ and
# tests/ are host-only (platformio.ini's build_src_filter) and never sync —
# App Lab's own build never sees them.
#
# device/mcu/src/ is itself flat (no subfolders) so this rsync produces the
# exact layout arduino-cli's sketch build requires: it only compiles .cpp
# files that are direct children of the sketch root and only puts the
# sketch root itself on the include search path (see docs/decisions/0010's
# addendum) — a nested sensors/, actuators/, etc. would silently vanish from
# the board build (compiles with zero errors, then fails at the link step),
# not just break an #include like the earlier config.h/secrets.h issue did.
rsync -avz --delete \
  "${MCU_DIR}/src/" \
  "${BOARD_USER}@${BOARD_HOST}:${APP_ROOT}/sketch/"

echo "==> 5. Sanity: local device/mpu tree present"
[ -d "${MPU_DIR}/bridge" ] || { echo "   MISSING ${MPU_DIR}/bridge — aborting"; exit 1; }

echo "==> 6. rsync device/mpu/ -> python/ (one-directional, deletes files removed locally)"
# --delete keeps the board's python/ an exact mirror of device/mpu/ so a file
# removed in the repo does not linger on the board as stale dead code.
# tests/, bench/ and pyproject.toml are host-only (ruff/pytest never run on
# the board) and never sync; __pycache__/*.pyc are build artifacts, not
# source. Excluding bench/ here is deliberate — the disposable ping app
# under device/mpu/bench/ping/ gets its own separate rsync one-liner
# (device/mpu/README.md), never this script, per the one-app-at-a-time
# discipline DEVICE_DEVELOPMENT_WORKFLOW.md 3 already applies to Bridge
# functions.
rsync -avz --delete \
  --exclude='tests/' \
  --exclude='bench/' \
  --exclude='pyproject.toml' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  "${MPU_DIR}/" \
  "${BOARD_USER}@${BOARD_HOST}:${APP_ROOT}/python/"

echo "==> 7. DONE. Build/flash from App Lab, or over SSH with the Arduino App CLI."
