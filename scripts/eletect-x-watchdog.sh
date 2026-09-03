#!/usr/bin/env bash
# Board-side crash-recovery watchdog for the EleTect-X App Lab container.
#
# Why this exists: `docker update --restart=unless-stopped` on the running
# container closes the immediate failure mode (an unhandled exception in
# main.py exits PID 1, Docker brings it straight back up) but that fix lives
# only in the live container's HostConfig. App Lab regenerates
# ~/ArduinoApps/eletect-x/.cache/app-compose.yaml on every redeploy, and that
# generated file carries no restart policy of its own — so a future redeploy
# silently reverts to Docker's default `no` policy. This script is the
# durable layer: it runs from the arduino user's own crontab (no sudo, see
# CLAUDE.md), checks the app's status through arduino-app-cli itself rather
# than assuming a fixed container name, restarts it if it isn't running, and
# re-asserts the restart policy on whatever container is currently in place.
#
# Deliberately does not fire the instant a check finds the app down: App Lab
# reports transitional states while it rebuilds/recreates the container
# during a legitimate redeploy, and this must not race that. It waits for
# GRACE_S of continuous down-ness (tracked in STATE_FILE across cron ticks)
# before acting.
#
# Installed on the board itself, not run from the repo checkout:
#   scp scripts/eletect-x-watchdog.sh arduino@<board>:~/bin/eletect-x-watchdog.sh
#   ssh arduino@<board> chmod +x ~/bin/eletect-x-watchdog.sh
#   crontab entry: */5 * * * * $HOME/bin/eletect-x-watchdog.sh
#
# Also probes the vision runner (edge-impulse-linux-runner --run-http-server,
# host-side on port 1337 — see deployment/install/eletect-x-vision-runner.service).
# That unit's Restart=always covers process death in seconds, but it cannot see
# a process that is still running yet no longer answering HTTP requests. This
# script's own 5-minute cron tick is the right cadence to catch that
# hung-but-alive case; the two mechanisms are deliberately separate layers
# rather than one, because they cover different failure modes on different
# timescales. The container check below is unmodified from its original form.
set -u

APP_NAME="EleTect-X"
APP_PATH="user:eletect-x"
CONTAINER="eletect-x-main-1"
STATE_DIR="${HOME}/.local/state/eletect-x-watchdog"
STATE_FILE="${STATE_DIR}/down-since"
LOG_FILE="${STATE_DIR}/watchdog.log"
GRACE_S=300      # two consecutive 5-min cron ticks must both see it down
MAX_LOG_LINES=2000

# Vision runner probe state — kept alongside but separate from the container's
# own STATE_FILE so the two checks never share or clobber each other's grace
# timers.
VISION_RUNNER_PORT=1337
VISION_RUNNER_UNIT="eletect-x-vision-runner.service"
VISION_STATE_FILE="${STATE_DIR}/vision-runner-down-since"

mkdir -p "${STATE_DIR}"

log() {
  echo "$(date -Is) $*" >>"${LOG_FILE}"
  local lines
  lines=$(wc -l <"${LOG_FILE}" 2>/dev/null || echo 0)
  if [ "${lines}" -gt "${MAX_LOG_LINES}" ]; then
    tail -n "$((MAX_LOG_LINES / 2))" "${LOG_FILE}" >"${LOG_FILE}.trim" && mv "${LOG_FILE}.trim" "${LOG_FILE}"
  fi
}

check_container() {
  status=$(arduino-app-cli app list --format json 2>/dev/null | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("unknown")
    sys.exit(0)
for app in data.get("apps", []):
    if app.get("name") == "'"${APP_NAME}"'":
        print(app.get("status", "unknown"))
        sys.exit(0)
print("missing")
')

  if [ "${status}" = "running" ]; then
    policy=$(docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' "${CONTAINER}" 2>/dev/null || echo "")
    if [ -n "${policy}" ] && [ "${policy}" != "unless-stopped" ]; then
      docker update --restart=unless-stopped "${CONTAINER}" >/dev/null 2>&1
      log "restart policy had drifted to '${policy}' on ${CONTAINER}; re-applied unless-stopped"
    fi
    rm -f "${STATE_FILE}"
    return 0
  fi

  now=$(date +%s)
  if [ ! -f "${STATE_FILE}" ]; then
    echo "${now}" >"${STATE_FILE}"
    log "app status='${status}' - first tick observing it down, starting ${GRACE_S}s grace period"
    return 0
  fi

  down_since=$(cat "${STATE_FILE}" 2>/dev/null || echo "${now}")
  elapsed=$((now - down_since))
  if [ "${elapsed}" -lt "${GRACE_S}" ]; then
    log "app status='${status}' - down ${elapsed}s, still within ${GRACE_S}s grace, waiting"
    return 0
  fi

  log "app status='${status}' - down ${elapsed}s, past grace period, restarting via arduino-app-cli"
  arduino-app-cli app restart "${APP_PATH}" >>"${LOG_FILE}" 2>&1
  rc=$?
  log "arduino-app-cli app restart exit code ${rc}"
  rm -f "${STATE_FILE}"
}

check_vision_runner() {
  if curl -s -m 3 -o /dev/null -w '%{http_code}' "127.0.0.1:${VISION_RUNNER_PORT}/api/info" 2>/dev/null | grep -q '^200$'; then
    rm -f "${VISION_STATE_FILE}"
    return 0
  fi

  now=$(date +%s)
  if [ ! -f "${VISION_STATE_FILE}" ]; then
    echo "${now}" >"${VISION_STATE_FILE}"
    log "vision runner :${VISION_RUNNER_PORT}/api/info not responding - first tick, starting ${GRACE_S}s grace period"
    return 0
  fi

  down_since=$(cat "${VISION_STATE_FILE}" 2>/dev/null || echo "${now}")
  elapsed=$((now - down_since))
  if [ "${elapsed}" -lt "${GRACE_S}" ]; then
    log "vision runner :${VISION_RUNNER_PORT}/api/info not responding - down ${elapsed}s, still within ${GRACE_S}s grace, waiting"
    return 0
  fi

  # Restart via systemd rather than pkill: the unit's Restart=always already
  # respawns a dead process on its own, so reaching this branch means the
  # process is alive but wedged (hung inference, stuck accept loop) and needs
  # an explicit restart rather than a respawn it will never trigger itself.
  log "vision runner :${VISION_RUNNER_PORT}/api/info not responding - down ${elapsed}s, past grace period, restarting ${VISION_RUNNER_UNIT}"
  systemctl --user restart "${VISION_RUNNER_UNIT}" >>"${LOG_FILE}" 2>&1
  rc=$?
  log "systemctl --user restart ${VISION_RUNNER_UNIT} exit code ${rc}"
  rm -f "${VISION_STATE_FILE}"
}

check_container
check_vision_runner
