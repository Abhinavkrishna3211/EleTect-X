#!/usr/bin/env bash
# Registers the locally built acoustic .eim as an App Lab *custom model*, so the
# stock `arduino:audio_classification` brick can serve it.
#
# Why this exists instead of App Lab's own Edge Impulse import:
#
#   App Lab imports Edge Impulse models with
#       PUT /v1/models/ei/projects/{projectID}   body {"impulse_id": N}
#   against the local arduino-app-cli daemon on 127.0.0.1:8800. That handler
#   (internal/orchestrator/models.go, InstallEIModel) insists on a deployment
#   whose format equals the platform's DeviceType. For BoardName "unoq" that is
#   hardcoded to {ModelType: float32, Engine: tflite, DeviceType:
#   runner-linux-aarch64}. If no such deployment exists it asks Studio to build
#   one — and Studio refuses:
#
#       Cannot build for "runner-linux-aarch64" as your project contains
#       custom DSP blocks. Use the C++ library export option and build locally.
#
#   (Verified 30 Sep 2026, build job 54315745, project 1110036 impulse 19.)
#   Our PANNs log-mel front end is an organisation DSP block, so that refusal is
#   permanent for as long as the impulse keeps it. The import route is therefore
#   closed to this model, and "build locally" is exactly what we already do.
#
# What the daemon actually needs is far less than the import path: the models
# index scans the custom-models directory for any subdirectory containing a
# `model.yaml` (internal/orchestrator/modelsindex/models_index.go) and loads the
# descriptor next to the blob. Writing those two files by hand registers the
# model just as the importer would have.
#
# Two things this buys over the bare `edge-impulse-linux-runner` we run today:
#   - Supervision and restart come from Compose rather than from our own
#     systemd unit (compare install-vision-runner.sh).
#   - The brick and the app share a Compose network, so the app can reach the
#     classifier by service name. The vision runner needed a host-side systemd
#     unit precisely because the App Lab container cannot reach host
#     127.0.0.1:1337 over the bridge network.
#
# Note the port change: the brick publishes host 127.0.0.1:1339 (container
# 1337), whereas services/config.py's ACOUSTIC_INFERENCE_URL defaults to
# :1338, which is the bare-runner port. Reconcile one or the other before
# enabling acoustic.
#
# Usage:
#   BOARD_HOST=eletect-x.local deployment/install/install-acoustic-brick.sh
# or, run directly on the board as the arduino user:
#   ./install-acoustic-brick.sh --local
set -euo pipefail

BOARD_USER="${BOARD_USER:-arduino}"
BOARD_HOST="${BOARD_HOST:-eletect-x.local}"

# The .eim already deployed by hand; see ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md.
# Note this is the *Focal* build, not the original one. The first .eim was
# cross-compiled on Ubuntu 24.04 and will not load inside the brick container;
# see ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md.
SRC_EIM="${SRC_EIM:-/home/arduino/ArduinoApps/eletect-x/python/models/acoustic/acoustic-panns-20260930-focal.eim}"
EXPECTED_SHA="ca7c895abc84b221c699fefb6797581c9dd28dbba23151a01bda1edd40db333f"

MODEL_ID="${MODEL_ID:-etx-acoustic-panns-20260930}"
# config.go falls back to $HOME/.arduino-bricks/models when
# ARDUINO_APP_BRICKS__CUSTOM_MODEL_DIR is unset.
MODELS_DIR="${ARDUINO_APP_BRICKS__CUSTOM_MODEL_DIR:-/home/arduino/.arduino-bricks/models}"
# The image arduino:audio_classification runs; keep in step with the brick.
RUNNER_IMAGE="${RUNNER_IMAGE:-ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0}"

install_local() {
  local dir="${MODELS_DIR}/${MODEL_ID}"

  echo "==> 1. Check the source .eim"
  test -f "${SRC_EIM}" || { echo "missing: ${SRC_EIM}" >&2; exit 1; }
  local got
  got="$(sha256sum "${SRC_EIM}" | cut -d' ' -f1)"
  if [ "${got}" != "${EXPECTED_SHA}" ]; then
    echo "sha256 mismatch for ${SRC_EIM}" >&2
    echo "  expected ${EXPECTED_SHA}" >&2
    echo "  got      ${got}" >&2
    echo "Refusing to register a model that is not the one that was measured." >&2
    exit 1
  fi
  echo "    sha256 ok (${EXPECTED_SHA})"

  echo "==> 2. Check the brick container can actually load it"
  # The .eim is cross-compiled, and the brick does not run it on the host: it
  # runs it inside ei-models-runner, which is Ubuntu 20.04 (glibc 2.31,
  # libstdc++ 6.0.28). A binary built against a newer glibc loads fine on the
  # host -- Debian 13, glibc 2.41 -- and fails inside the brick. Registering
  # such a model would leave a brick that starts and then dies, so check the
  # loader here rather than discover it later.
  local ldd_out
  if ldd_out="$(docker run --rm         -v "$(dirname "${SRC_EIM}")":/m:ro         --entrypoint ldd "${RUNNER_IMAGE}" "/m/$(basename "${SRC_EIM}")" 2>&1)"; then
    :
  fi
  if printf '%s' "${ldd_out}" | grep -q "not found"; then
    echo "${ldd_out}" | grep "not found" >&2
    echo "The brick container cannot load this .eim." >&2
    echo "Rebuild it with the Focal cross toolchain; see" >&2
    echo "ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md." >&2
    exit 1
  fi
  echo "    all libraries resolve inside ${RUNNER_IMAGE}"

  echo "==> 3. Lay out the custom model directory"
  mkdir -p "${dir}"
  # Copy rather than symlink: the brick bind-mounts CUSTOM_MODEL_PATH into the
  # container, and a symlink pointing outside that mount would dangle inside it.
  cp -f "${SRC_EIM}" "${dir}/model.eim"

  echo "==> 4. Write the descriptor"
  # Field names and the source=edgeimpulse validation rules come from
  # internal/orchestrator/modelsindex/custommodel/parser.go. With that source
  # set, ei-project-id / ei-impulse-id / ei-impulse-name / ei-deployment-version
  # must all be non-empty and ei-model-type must be exactly "float32".
  cat > "${dir}/model.yaml" <<YAML
id: "${MODEL_ID}"
name: "EleTect-X acoustic (PANNs Cnn10)"
description: "Four-class forest audio classifier: ambient, chainsaw, elephant_call, gunshot."
runner: "brick"
bricks:
  - id: "arduino:audio_classification"
    model_configuration:
      CUSTOM_MODEL_PATH: "${dir}"
      EI_AUDIO_CLASSIFICATION_MODEL: "${dir}/model.eim"
metadata:
  source: "edgeimpulse"
  ei-project-id: "1110036"
  ei-impulse-id: "19"
  ei-impulse-name: "Impulse #19"
  ei-deployment-version: "7"
  ei-model-type: "float32"
  ei-engine: "tflite"
YAML

  echo "==> 5. Verify the daemon picked it up"
  # The index rescans on read; no daemon restart should be needed.
  if arduino-app-cli model list --format json | grep -q "\"${MODEL_ID}\""; then
    echo "    registered: ${MODEL_ID}"
  else
    echo "    NOT registered — dumping what the daemon sees:" >&2
    arduino-app-cli model list --format json >&2
    exit 1
  fi

  cat <<'NEXT'

==> Done. Remaining manual steps (deliberately not automated):

  1. Add the brick to the app, in ~/ArduinoApps/eletect-x/app.yaml:

         bricks:
           - arduino:audio_classification:
               model: etx-acoustic-panns-20260930

     This restarts the app, and the app is the production deterrence stack.
     Do it at a time when a restart is acceptable.

  2. Point services/config.py's ACOUSTIC_INFERENCE_URL at the brick. From the
     host that is http://127.0.0.1:1339; from inside the app container use the
     Compose service name instead, since the container cannot reach host
     127.0.0.1.

  3. Step 2 above already proved the container can load this .eim. If you
     ever swap in a differently built one, that check is the gate -- it is
     the one thing the host cannot tell you, because the host runs a much
     newer glibc than the brick container does.
NEXT
}

if [ "${1:-}" = "--local" ]; then
  install_local
else
  echo "==> Copying installer to ${BOARD_USER}@${BOARD_HOST} and running it there"
  scp "${BASH_SOURCE[0]}" "${BOARD_USER}@${BOARD_HOST}:/tmp/install-acoustic-brick.sh"
  ssh "${BOARD_USER}@${BOARD_HOST}" "chmod +x /tmp/install-acoustic-brick.sh && /tmp/install-acoustic-brick.sh --local"
fi
