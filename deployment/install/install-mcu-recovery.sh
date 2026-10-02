#!/usr/bin/env bash
# Installs the STM32 boot-state recovery layer for EleTect-X.
#
# The problem it closes: on this board the STM32's BOOT0 source is the physical
# PH3 pin (option byte nSWBOOT0=1), wired to MPU gpiochip1 line 37. Line 37
# floats HIGH unless driven, and a HIGH BOOT0 at reset drops the MCU into the
# STM32 system bootloader (DFU) instead of the application sketch - the sketch
# never runs, no Bridge.provide(), every drive_led/drive_horn/pulse_ir returns
# "method not available (2)". That is the exact state that produced a full
# night of zero deterrence on field-trial run #1. arduino-router only holds
# line 37 low from an ExecStartPre, which systemd kills the moment the router's
# main process starts, so nothing survives the site's daily hard power-cut.
#
# Three pieces, matching the vision-runner two-layer pattern:
#   1. eletect-x-boot0-hold.service  (--user, Restart=always)
#        permanent low hold on gpiochip1 line 37 - prevention.
#   2. eletect-x-mcu-heal.sh + eletect-x-mcu-heal.service  (--user oneshot)
#        at boot, verify the sketch answers Bridge; if not, escalate
#        (BOOT0 low -> openocd SWD reset -> re-probe -> recompile+reflash +
#        golden-compose re-assert -> re-probe) - recovery.
#   3. check_mcu added to scripts/eletect-x-watchdog.sh (already in that file)
#        same probe on the 5-min cron tick with its own grace timer, for a
#        fault that appears after boot - ongoing cover.
#
# No sudo on this box: everything is systemctl --user + the arduino
# user's own crontab, surviving reboot via enable-linger (already 'yes').
#
# Usage:
#   BOARD_HOST=eletect-x.local deployment/install/install-mcu-recovery.sh
# or on the board itself as the arduino user:
#   ./install-mcu-recovery.sh --local
set -euo pipefail

BOARD_USER="${BOARD_USER:-arduino}"
BOARD_HOST="${BOARD_HOST:-eletect-x.local}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

HEAL_SRC="${REPO_ROOT}/scripts/eletect-x-mcu-heal.sh"
WATCHDOG_SRC="${REPO_ROOT}/scripts/eletect-x-watchdog.sh"
BOOT0_UNIT="${SCRIPT_DIR}/eletect-x-boot0-hold.service"
HEAL_UNIT="${SCRIPT_DIR}/eletect-x-mcu-heal.service"

install_local() {
  echo "==> 1. Directories"
  mkdir -p "${HOME}/bin" "${HOME}/.config/systemd/user" "${HOME}/.local/state/eletect-x-watchdog"

  echo "==> 2. Scripts into ~/bin"
  cp "${HEAL_SRC}" "${HOME}/bin/eletect-x-mcu-heal.sh"
  cp "${WATCHDOG_SRC}" "${HOME}/bin/eletect-x-watchdog.sh"
  chmod +x "${HOME}/bin/eletect-x-mcu-heal.sh" "${HOME}/bin/eletect-x-watchdog.sh"

  echo "==> 3. Unit files"
  cp "${BOOT0_UNIT}" "${HOME}/.config/systemd/user/eletect-x-boot0-hold.service"
  cp "${HEAL_UNIT}"  "${HOME}/.config/systemd/user/eletect-x-mcu-heal.service"

  echo "==> 4. Clear any stray BOOT0 holder so the unit owns line 37 cleanly"
  pkill -f 'gpioset.*gpiochip1.*37' 2>/dev/null || true
  sleep 1

  echo "==> 5. Reload, enable, start"
  systemctl --user daemon-reload
  systemctl --user enable --now eletect-x-boot0-hold.service
  systemctl --user enable eletect-x-mcu-heal.service
  # Run the heal oneshot now too, so a board that is already in DFU at install
  # time gets recovered without waiting for the next reboot.
  systemctl --user start eletect-x-mcu-heal.service || true

  echo "==> 6. Linger (survives logout; already 'yes' on this board as of 3 Sep 2026)"
  loginctl enable-linger "$(whoami)" 2>/dev/null || true

  echo "==> 7. crontab entry for the watchdog (idempotent)"
  if ! crontab -l 2>/dev/null | grep -qF 'bin/eletect-x-watchdog.sh'; then
    (crontab -l 2>/dev/null; echo '*/5 * * * * $HOME/bin/eletect-x-watchdog.sh') | crontab -
    echo "   added */5 cron entry"
  else
    echo "   cron entry already present"
  fi

  echo "==> 8. Verify"
  sleep 3
  systemctl --user is-active eletect-x-boot0-hold.service && echo "   boot0-hold active" || echo "   boot0-hold NOT active"
  if command -v gpioinfo >/dev/null 2>&1; then
    gpioinfo gpiochip1 2>/dev/null | grep -E '\bline +37:' || true
  fi
  echo "   mcu-heal probe:"
  "${HOME}/bin/eletect-x-mcu-heal.sh" --probe-only && echo "   -> sketch ANSWERS Bridge (healthy)" || echo "   -> sketch does NOT answer (heal will have run above; check ~/.local/state/eletect-x-watchdog/mcu-heal.log)"
}

if [ "${1:-}" = "--local" ]; then
  install_local
  exit 0
fi

echo "==> Reachability check: ${BOARD_USER}@${BOARD_HOST}"
if ! ssh -o BatchMode=yes -o ConnectTimeout=8 "${BOARD_USER}@${BOARD_HOST}" true 2>/dev/null; then
  echo "   Cannot reach ${BOARD_USER}@${BOARD_HOST} over SSH."
  exit 1
fi

echo "==> Copying files to the board"
ssh "${BOARD_USER}@${BOARD_HOST}" "mkdir -p ~/bin ~/.config/systemd/user ~/.local/state/eletect-x-watchdog"
scp "${HEAL_SRC}"     "${BOARD_USER}@${BOARD_HOST}:~/bin/eletect-x-mcu-heal.sh"
scp "${WATCHDOG_SRC}" "${BOARD_USER}@${BOARD_HOST}:~/bin/eletect-x-watchdog.sh"
scp "${BOOT0_UNIT}"   "${BOARD_USER}@${BOARD_HOST}:~/.config/systemd/user/eletect-x-boot0-hold.service"
scp "${HEAL_UNIT}"    "${BOARD_USER}@${BOARD_HOST}:~/.config/systemd/user/eletect-x-mcu-heal.service"

echo "==> Running the local installer on the board"
ssh "${BOARD_USER}@${BOARD_HOST}" "chmod +x ~/bin/eletect-x-mcu-heal.sh ~/bin/eletect-x-watchdog.sh && \
  pkill -f 'gpioset.*gpiochip1.*37' 2>/dev/null || true; sleep 1; \
  systemctl --user daemon-reload && \
  systemctl --user enable --now eletect-x-boot0-hold.service && \
  systemctl --user enable eletect-x-mcu-heal.service && \
  systemctl --user start eletect-x-mcu-heal.service || true; \
  loginctl enable-linger \$(whoami) 2>/dev/null || true; \
  ( crontab -l 2>/dev/null | grep -qF 'bin/eletect-x-watchdog.sh' ) || \
  ( (crontab -l 2>/dev/null; echo '*/5 * * * * \$HOME/bin/eletect-x-watchdog.sh') | crontab - )"

echo "==> Verify"
ssh "${BOARD_USER}@${BOARD_HOST}" "systemctl --user is-active eletect-x-boot0-hold.service; \
  gpioinfo gpiochip1 2>/dev/null | grep -E '\bline +37:' || true; \
  ~/bin/eletect-x-mcu-heal.sh --probe-only && echo 'sketch ANSWERS Bridge' || echo 'sketch DOES NOT answer - see mcu-heal.log'"

echo "==> Done."
