#!/usr/bin/env bash
# STM32U585 boot-state recovery for EleTect-X.
#
# Why this exists: on this board the STM32 BOOT0 source is the physical PH3
# pin (option byte nSWBOOT0=1), and PH3 is wired to MPU gpiochip1 line 37,
# which floats HIGH unless something drives it low. A HIGH BOOT0 at reset
# lands the MCU in the STM32 system bootloader (DFU) instead of the
# application sketch: the sketch never runs, Bridge.provide() never happens,
# and every drive_led / drive_horn / pulse_ir call fails. That is the exact
# failure that produced a whole night of zero deterrence on field-trial run #1.
#
# eletect-x-boot0-hold.service owns a permanent low hold on line 37 so a cold
# boot lands in the sketch. This script is the recovery arm for when the MCU
# still ends up unresponsive - it runs once at boot (eletect-x-mcu-heal.service)
# and every 5 min with its own grace timer from eletect-x-watchdog.sh.
#
# Failure shapes observed on the bench (2026-09-10):
#   * MCU in DFU (PC 0x0bf9xxxx): Bridge calls TIME OUT (no "method not
#     available" - the router forwards to an MCU that never answers). A
#     persistent timeout across retries is therefore treated as DEAD, not
#     "inconclusive".
#   * A bare openocd SRST reset does NOT reliably start the app after the MCU
#     has been in DFU, and recreating the app container alone does not help
#     either - the only thing that consistently brought registration back was
#     a full SWD reflash via `arduino-app-cli app restart` (which also bounces
#     serial-discovery and forces the router to re-handshake). With the sketch
#     compile cached that step is ~30s.
#
# Escalation (each step re-probed with retries before moving on):
#   1. ensure BOOT0 held low
#   2. openocd SRST reset (belt-and-braces: out of DFU before the flash tool
#      runs) + arduino-app-cli app restart + re-assert golden compose
#   3. same again once more, then give up loudly
#
# No sudo on this box: arduino-router is a system service and
# cannot be restarted from here, so recovery works entirely through openocd
# SWD (the arduino user has it), arduino-app-cli, and docker compose against
# the golden file.
#
#   --probe-only   run one health probe, exit 0 healthy / non-zero not
#   --boot         skip the "encounter assembly in progress" guard on the
#                  heavy steps (nothing assembles at boot; fast recovery wins)
set -u

STATE_DIR="${HOME}/.local/state/eletect-x-watchdog"
LOG_FILE="${STATE_DIR}/mcu-heal.log"
LOCK_FILE="${STATE_DIR}/mcu-heal.lock"
CONTAINER="eletect-x-main-1"
OPENOCD_RESET="/opt/openocd/bin/arduino-reset.sh"
COMPOSE_DIR="${HOME}/ArduinoApps/eletect-x/.cache"
COMPOSE_FILE="app-compose.golden.yaml"
GPIOCHIP="/dev/gpiochip1"
BOOT0_LINE=37
BOOT0_UNIT="eletect-x-boot0-hold.service"
INITIAL_ATTEMPTS=6       # ~35s: tolerate a slow-linking sketch before escalating
RECHECK_ATTEMPTS=10      # ~90s: give a reflash time to bring registration back
MAX_LOG_LINES=1500

MODE="${1:-}"

mkdir -p "${STATE_DIR}"
log() {
  echo "$(date -Is) $*" >>"${LOG_FILE}"
  local n
  n=$(wc -l <"${LOG_FILE}" 2>/dev/null || echo 0)
  if [ "${n}" -gt "${MAX_LOG_LINES}" ]; then
    tail -n "$((MAX_LOG_LINES / 2))" "${LOG_FILE}" >"${LOG_FILE}.trim" && mv "${LOG_FILE}.trim" "${LOG_FILE}"
  fi
}

# Probe registration by calling drive_led (a method the sketch registers) with
# too few parameters, from inside the app container so it uses the real Bridge
# path. Retries $1 times, 3s apart.
#   exit 0  a probe got a param/arity rejection (253) or an ack  -> sketch alive
#   exit 2  retries exhausted with only timeouts / "not available" -> DEAD
#   exit 4  container up but the app env is not importable yet     -> not ready
probe_sketch() {
  local attempts="${1:-1}"
  docker exec -i "${CONTAINER}" python3 - "${attempts}" <<'PY' 2>/dev/null
import sys, time
attempts = int(sys.argv[1]) if len(sys.argv) > 1 else 1
try:
    from arduino.app_utils import Bridge
except Exception:
    sys.exit(4)
for i in range(attempts):
    try:
        Bridge.call("drive_led", 128, timeout=6)
        sys.exit(0)
    except Exception as e:
        m = str(e).lower()
        if "param" in m or "253" in m:
            sys.exit(0)
        # "not available (2)" or a timeout -> not healthy; keep retrying
    if i < attempts - 1:
        time.sleep(3)
sys.exit(2)
PY
}

# eletect-x-boot0-hold.service should already own line 37. Only act if nothing
# holds it. Bare gpioset (no -t/-p) blocks and holds until killed; -t0 would
# toggle once and exit, which is why the router's ExecStartPre hold does not
# survive. ps renders the arg as "37 0" or "37=0" depending on how it was set,
# so the pattern tolerates both.
ensure_boot0_low() {
  if pgrep -f "gpioset.*gpiochip1.*[ =]${BOOT0_LINE}([ =]|$)" >/dev/null 2>&1; then
    return 0
  fi
  systemctl --user start "${BOOT0_UNIT}" >/dev/null 2>&1 || true
  sleep 2
  if pgrep -f "gpioset.*gpiochip1.*[ =]${BOOT0_LINE}([ =]|$)" >/dev/null 2>&1; then
    log "${BOOT0_UNIT} now holding ${GPIOCHIP} line ${BOOT0_LINE} low"
    return 0
  fi
  setsid nohup /usr/bin/gpioset -c "${GPIOCHIP}" "${BOOT0_LINE}=0" >>"${LOG_FILE}" 2>&1 &
  disown 2>/dev/null || true
  sleep 1
  if pgrep -f "gpioset.*gpiochip1.*[ =]${BOOT0_LINE}([ =]|$)" >/dev/null 2>&1; then
    log "started detached fallback BOOT0-low hold"
  else
    log "WARN could not hold BOOT0 low (line busy elsewhere, or gpioset missing)"
  fi
}

assert_golden_compose() {
  [ -d "${COMPOSE_DIR}" ] || { log "compose dir ${COMPOSE_DIR} missing"; return 1; }
  (cd "${COMPOSE_DIR}" && docker compose -f "${COMPOSE_FILE}" -p eletect-x up -d) >>"${LOG_FILE}" 2>&1
  log "golden compose re-assert rc=$?"
}

assembly_running() {
  pgrep -f assemble_encounters_onboard >/dev/null 2>&1
}

# openocd SRST reset then a full recompile+reflash+restart, then re-pin the
# golden compose (app restart regenerates a non-golden one). Returns the probe
# result.
reset_and_reflash() {
  if [ -x "${OPENOCD_RESET}" ]; then
    "${OPENOCD_RESET}" >>"${LOG_FILE}" 2>&1
    log "openocd SRST reset rc=$?"
    sleep 4
  else
    log "openocd reset skipped: ${OPENOCD_RESET} not executable"
  fi
  log "arduino-app-cli app restart user:eletect-x"
  arduino-app-cli app restart user:eletect-x >>"${LOG_FILE}" 2>&1
  log "app restart rc=$?"
  assert_golden_compose
  probe_sketch "${RECHECK_ATTEMPTS}"
}

# --------------------------------------------------------------------------

if [ "${MODE}" = "--probe-only" ]; then
  probe_sketch 1
  exit $?
fi

exec 9>"${LOCK_FILE}" || exit 0
if ! flock -n 9; then
  log "another mcu-heal instance holds the lock - skipping"
  exit 0
fi

ensure_boot0_low

probe_sketch "${INITIAL_ATTEMPTS}"; st=$?
if [ "${st}" -eq 0 ]; then
  log "sketch healthy (drive_led registered) - no action"
  exit 0
fi
if [ "${st}" -eq 4 ]; then
  log "app container not ready (rc=4) - deferring to next tick"
  exit 0
fi

log "sketch NOT answering Bridge (rc=${st}) - escalating recovery"

if assembly_running && [ "${MODE}" != "--boot" ]; then
  log "encounter assembly in progress - deferring heavy recovery to next watchdog tick"
  exit 1
fi

for pass in 1 2; do
  log "recovery pass ${pass}: reset + reflash"
  reset_and_reflash; st=$?
  if [ "${st}" -eq 0 ]; then
    log "RECOVERED after pass ${pass}"
    exit 0
  fi
  log "still not answering after pass ${pass} (rc=${st})"
done

log "FAILED to recover MCU (rc=${st}) after 2 reset+reflash passes - manual help needed"
exit 1
