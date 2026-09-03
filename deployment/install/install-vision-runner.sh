#!/usr/bin/env bash
# Installs the process-death half of the vision runner's two-layer
# supervision (Step 0 of the Boar-gap plan, docs/qa/boar-gap-session-notes.md).
#
# Why two layers: `edge-impulse-linux-runner --run-http-server` must run
# host-side as the arduino user, not in the App Lab container — the
# container sits on a bridge network and cannot reach host 127.0.0.1:1337
# (HANDOVER.md). It was previously started by hand and had no supervision
# at all, so a crash or a reboot left vision permanently dead until someone
# noticed and SSH'd in.
#
# This installer covers process death only: a systemd --user unit with
# Restart=always gives second-scale recovery, following the same pattern as
# the board's existing exposure-ladder.service (sudo-free, reboot-surviving
# via `loginctl enable-linger`). It does NOT cover a runner that is running
# but no longer answering HTTP requests — that hung-but-alive case is
# covered separately by the port-1337 probe added to the existing
# scripts/eletect-x-watchdog.sh cron job, which already supervises the App
# Lab container. Do not collapse these into one mechanism: Restart=always
# cannot see a wedged-but-alive process, and a 5-minute cron tick cannot
# give the seconds-scale recovery a vision-gated deterrent needs.
#
# Usage:
#   BOARD_HOST=eletect-x.local scripts/../deployment/install/install-vision-runner.sh
# or, run directly on the board as the arduino user:
#   ./install-vision-runner.sh --local
set -euo pipefail

BOARD_USER="${BOARD_USER:-arduino}"
BOARD_HOST="${BOARD_HOST:-eletect-x.local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_FILE="${SCRIPT_DIR}/eletect-x-vision-runner.service"

if [ "${1:-}" = "--local" ]; then
  echo "==> 1. Installing unit on the local machine (assumes this IS the board)"
  mkdir -p "${HOME}/.config/systemd/user" "${HOME}/.local/state/eletect-x-vision-runner"
  cp "${UNIT_FILE}" "${HOME}/.config/systemd/user/eletect-x-vision-runner.service"
  echo "==> 2. Reload, enable, start"
  systemctl --user daemon-reload
  systemctl --user enable --now eletect-x-vision-runner.service
  echo "==> 3. Enable linger so the unit survives logout (no sudo required for the user's own linger bit)"
  loginctl enable-linger "$(whoami)" 2>/dev/null || echo "   (enable-linger needs polkit/sudo on some setups; already 'yes' on this board as of 3 Sep 2026)"
  echo "==> 4. Verify"
  sleep 6
  systemctl --user is-active eletect-x-vision-runner.service
  curl -s -m 5 127.0.0.1:1337/api/info >/dev/null && echo "   /api/info OK" || echo "   /api/info NOT RESPONDING YET (model load can take a few seconds)"
  exit 0
fi

echo "==> 1. Reachability check: ${BOARD_USER}@${BOARD_HOST}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "${BOARD_USER}@${BOARD_HOST}" true 2>/dev/null; then
  echo "   Cannot reach ${BOARD_USER}@${BOARD_HOST} over SSH. Same preconditions as sync-to-board.sh."
  exit 1
fi

echo "==> 2. Copy unit file to the board"
ssh "${BOARD_USER}@${BOARD_HOST}" "mkdir -p ~/.config/systemd/user ~/.local/state/eletect-x-vision-runner"
scp "${UNIT_FILE}" "${BOARD_USER}@${BOARD_HOST}:~/.config/systemd/user/eletect-x-vision-runner.service"

echo "==> 3. Reload, enable, start"
ssh "${BOARD_USER}@${BOARD_HOST}" "systemctl --user daemon-reload && systemctl --user enable --now eletect-x-vision-runner.service"

echo "==> 4. Confirm linger is on (required for the unit to survive SSH logout)"
ssh "${BOARD_USER}@${BOARD_HOST}" "loginctl show-user \"\$(whoami)\" 2>/dev/null | grep -i linger || echo '   could not read linger state'"

echo "==> 5. Verify the runner answers"
sleep 6
ssh "${BOARD_USER}@${BOARD_HOST}" "curl -s -m 5 -o /dev/null -w 'http_status=%{http_code}\n' 127.0.0.1:1337/api/info"

echo "==> Done. This installs process-death supervision only — confirm scripts/eletect-x-watchdog.sh"
echo "    on the board also carries the 1337 liveness probe (added separately, same commit series)."
