#!/usr/bin/env bash
# One-directional sync: repo (device/mcu) -> the UNO Q's own App Lab app
# folder. The git monorepo is the source of truth (ENGINEERING_CONVENTIONS.md
# 5) — App Lab's on-board editor is never the place changes originate
# (DEVICE_DEVELOPMENT_WORKFLOW.md 2). Run this after every edit, before
# building/flashing from App Lab or the Arduino App CLI.
#
# Usage:
#   BOARD_HOST=eletect-x.local APP_NAME=EleTect-X scripts/sync-to-board.sh
#
# Defaults match the board name used during App Lab's First Setup wizard
# (DEVICE_DEVELOPMENT_WORKFLOW.md 2) — override if this board was set up
# under a different name.
set -euo pipefail

BOARD_USER="${BOARD_USER:-arduino}"
BOARD_HOST="${BOARD_HOST:-eletect-x.local}"
APP_NAME="${APP_NAME:-EleTect-X}"
APP_ROOT="/home/${BOARD_USER}/arduino_apps/${APP_NAME}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCU_DIR="${REPO_ROOT}/device/mcu"

echo "==> 1. Sanity: local device/mcu tree present"
[ -d "${MCU_DIR}/src" ] || { echo "   MISSING ${MCU_DIR}/src — aborting"; exit 1; }
[ -f "${MCU_DIR}/include/config.h" ] || { echo "   MISSING config.h — aborting"; exit 1; }
if [ ! -f "${MCU_DIR}/include/secrets.h" ]; then
  echo "   MISSING ${MCU_DIR}/include/secrets.h — copy secrets.h.example and fill in real"
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
ssh "${BOARD_USER}@${BOARD_HOST}" "mkdir -p '${APP_ROOT}/sketch' '${APP_ROOT}/assets'"

echo "==> 4. rsync src/ -> sketch/ (one-directional, deletes files removed locally)"
# --delete keeps the board's sketch/ an exact mirror of src/ so a file removed
# in the repo does not linger on the board as stale dead code. hostshim/ and
# tests/ are host-only (platformio.ini's build_src_filter) and never sync —
# App Lab's own build never sees them.
rsync -avz --delete --exclude='config.h' --exclude='secrets.h' \
  "${MCU_DIR}/src/" \
  "${BOARD_USER}@${BOARD_HOST}:${APP_ROOT}/sketch/"

echo "==> 5. config.h + secrets.h -> sketch root"
# #include "config.h" then resolves identically in both builds: PlatformIO
# puts include/ on its search path, App Lab puts the sketch root on its.
rsync -avz \
  "${MCU_DIR}/include/config.h" \
  "${MCU_DIR}/include/secrets.h" \
  "${BOARD_USER}@${BOARD_HOST}:${APP_ROOT}/sketch/"

echo "==> DONE. Build/flash from App Lab, or over SSH with the Arduino App CLI."
