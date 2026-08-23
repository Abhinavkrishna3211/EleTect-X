"""Configure and train the two-class FOMO impulse in the EleTect-X-Vision project.

Companion to scripts/edge_impulse_upload_vision.py, which must have run first -
this script only configures and trains against whatever data is already in the
project. It builds the impulse (image input -> image DSP -> object detection),
selects a FOMO model variant, generates features, trains, and then runs a model
test over the held-out set, printing the per-class numbers Edge Impulse actually
returns.

Nothing here is hardcoded from documentation that might have drifted. The
available blocks and the available object-detection model variants are read back
from the live API (/impulse/blocks, /training/keras/{learnId}/metadata) and the
FOMO variant is picked from what that call reports, so a renamed model shows up
as a clear failure rather than a silent fallback to a non-FOMO architecture.

Two things worth knowing before reading the output:

  - FOMO is a centroid detector, not a classifier. Edge Impulse's model-testing
    job reports per-class F1 with precision/recall and a confusion matrix, not
    "accuracy". Report what it returns, and report Elephant and Boar separately -
    the two classes have different dataset sizes (3,280 vs 1,901 images) and a
    per-class gap is expected.
  - The reported number is a held-out result on general daytime/colour wildlife
    photography. It says nothing about night IR field performance. See
    ml/vision/README.md for the full caveat list before quoting it anywhere.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1094260
    python scripts\\edge_impulse_train_vision.py

Requires only the standard library - no pip install needed.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

STUDIO = "https://studio.edgeimpulse.com/v1/api"

# Three controlled trials at 96/128/160px (everything else held constant) showed
# resolution increase alone monotonically REGRESSES both classes - Boar F1
# 0.567 -> 0.313 -> 0.165, Elephant 0.670 -> 0.593 -> 0.639. Reverted to 96px (the
# best real result) rather than keep guessing single hyperparameters against a
# capped compute budget; see ml/vision/README.md's iteration narrative for the full
# comparison. "squash" matches how Roboflow already stretch-resized both source
# sets (elephant to 640x640, boar to 416x416), so no new aspect-ratio distortion.
IMAGE_SIZE = 96
RESIZE_MODE = "squash"
# Edge Impulse documents 0.001 as the learning rate FOMO needs; its stock 0.0005 for
# other object-detection heads underfits here. Chosen, not inherited.
LEARNING_RATE = 0.001
# EON Tuner (the systematic search Edge Impulse offers) turned out to need an
# organization-level API key - every plausible /tuner/* endpoint 404'd against this
# project-scoped key, and there is no org key for this account. Cycle count is the
# next cheapest untested variable instead: all three resolution trials above left
# cycles at EI's own default (60), so undertraining at a finer grid is still an
# unruled-out explanation for those regressions, and it's untested even at the
# 96px baseline itself. 100 cycles fits the 1h job cap at 96px's ~0.52 min/cycle
# (~52 min estimated) with headroom to spare.
TRAINING_CYCLES = 100
JOB_POLL_S = 20
JOB_TIMEOUT_S = 7200


def request(path, api_key, method="GET", body=None, timeout=180):
    headers = {"x-api-key": api_key}
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    req = urllib.request.Request(f"{STUDIO}{path}", data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"{method} {path} -> HTTP {err.code}: {err.read().decode()[:400]}") from err
    # Edge Impulse returns HTTP 200 with {"success": false, "error": "..."} for
    # application-level rejections (e.g. an empty settable-config body) - catch that
    # here rather than let every call site guess at a missing field.
    if isinstance(result, dict) and result.get("success") is False:
        raise RuntimeError(f"{method} {path} -> {result.get('error', result)}")
    return result


def wait_for_job(project_id, api_key, job_id, what):
    """Block until an Edge Impulse job finishes, printing progress as it goes."""
    print(f"  job {job_id} ({what}) started")
    started = time.time()
    while time.time() - started < JOB_TIMEOUT_S:
        time.sleep(JOB_POLL_S)
        status = request(f"/{project_id}/jobs/{job_id}/status", api_key).get("job", {})
        if status.get("finished"):
            ok = status.get("finishedSuccessful")
            mins = (time.time() - started) / 60
            print(f"  job {job_id} finished after {mins:.1f} min, successful={ok}")
            if not ok:
                tail = request(f"/{project_id}/jobs/{job_id}/stdout", api_key).get("stdout", [])
                for line in tail[:20]:
                    print("    |", line.get("data", "").rstrip())
                raise RuntimeError(f"{what} job {job_id} failed")
            return
        print(f"    still running ({(time.time() - started) / 60:.1f} min elapsed)")
    raise RuntimeError(f"{what} job {job_id} did not finish within {JOB_TIMEOUT_S}s")


def check_data(project_id, api_key):
    counts = {}
    for category in ("training", "testing"):
        counts[category] = request(
            f"/{project_id}/raw-data/count?category={category}", api_key
        ).get("count", 0)
    print(f"Project {project_id} data: {counts['training']} training / {counts['testing']} testing")
    if not counts["training"] or not counts["testing"]:
        print(
            "Both categories must hold data - run scripts/edge_impulse_upload_vision.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    return counts


def build_impulse(project_id, api_key):
    """Create the image -> image -> object-detection impulse.

    Block types are taken from /impulse/blocks rather than hardcoded, so this fails
    loudly if Edge Impulse renames one instead of silently building a wrong impulse.
    """
    blocks = request(f"/{project_id}/impulse/blocks", api_key)
    types = {
        group: {b["type"] for b in blocks.get(group, [])}
        for group in ("inputBlocks", "dspBlocks", "learnBlocks")
    }
    for group, wanted in (
        ("inputBlocks", "image"),
        ("dspBlocks", "image"),
        ("learnBlocks", "keras-object-detection"),
    ):
        if wanted not in types[group]:
            raise RuntimeError(f"{group}: no {wanted!r} block available, found {sorted(types[group])}")

    existing = request(f"/{project_id}/impulse", api_key).get("impulse")
    if existing:
        print(f"  impulse already exists (id {existing.get('id')}) - deleting and rebuilding")
        request(f"/{project_id}/impulse", api_key, method="DELETE")

    impulse = {
        "inputBlocks": [
            {
                "id": 1,
                "type": "image",
                "name": "Image",
                "title": "Image data",
                "imageWidth": IMAGE_SIZE,
                "imageHeight": IMAGE_SIZE,
                "resizeMode": RESIZE_MODE,
                "resizeMethod": "lanczos3",
            }
        ],
        "dspBlocks": [
            {"id": 2, "type": "image", "name": "Image", "title": "Image", "axes": ["image"], "input": 1}
        ],
        "learnBlocks": [
            {
                "id": 3,
                "type": "keras-object-detection",
                "name": "Object detection",
                "title": "Object detection",
                "dsp": [2],
            }
        ],
    }
    request(f"/{project_id}/impulse", api_key, method="POST", body=impulse)
    print(f"  impulse created: image {IMAGE_SIZE}x{IMAGE_SIZE} ({RESIZE_MODE}) -> object detection")
    return 2, 3


def configure_dsp(project_id, api_key, dsp_id):
    """Set the image DSP block to RGB (FOMO's colour input) - already the block default, set

    explicitly anyway so it is a documented choice rather than an inherited one.
    """
    request(
        f"/{project_id}/dsp/{dsp_id}",
        api_key,
        method="POST",
        body={"config": {"channels": "RGB"}},
    )
    print("  DSP block set to RGB")


def select_fomo_model(project_id, api_key):
    """Pick a FOMO visual-layer type from the project's live transfer-learning-model list.

    FOMO's architecture is chosen via a "visualLayers" entry
    (KerasVisualLayerType, e.g. "fomo_mobilenet_v2_a35"), not via "selectedModelType"
    (which is KerasModelTypeEnum: int8/float32/akida/requiresRetrain - a post-training
    quantization variant, a different axis entirely). Read from
    /transfer-learning-models rather than hardcoding, so a renamed variant fails loudly.
    """
    models = request(f"/{project_id}/transfer-learning-models", api_key).get(
        "transferLearningModels", []
    )
    fomo = [
        m
        for m in models
        if m.get("learnBlockType") == "keras-object-detection" and "fomo" in m.get("type", "")
    ]
    print(f"  FOMO variants offered for this block: {[m['type'] for m in fomo] or '(none)'}")
    if not fomo:
        raise RuntimeError("no fomo_* transfer-learning model reported for keras-object-detection")
    # Prefer the larger alpha-0.35 backbone; it is still tiny and reads better than a01.
    choice = next((m for m in fomo if "a35" in m["type"]), fomo[0])
    print(
        f"  selected: {choice['type']} (default lr {choice['defaultLearningRate']}, "
        f"default cycles {choice['defaultTrainingCycles']})"
    )
    return choice["type"]


def training_params(model_type):
    return {
        "mode": "visual",
        "visualLayers": [{"type": model_type, "enabled": True}],
        "trainingCycles": TRAINING_CYCLES,
        "learningRate": LEARNING_RATE,
        "augmentationPolicyImage": "all",
        # 1.7:1 Elephant:Boar image ratio (ml/vision/README.md's Dataset section) -
        # balance it rather than let the majority class dominate the loss.
        "autoClassWeights": True,
        # Profile the int8 model: CONTEXT.md's deployment target is an INT8 detector.
        "profileInt8": True,
    }


def configure_training(project_id, api_key, learn_id, params, model_type):
    request(f"/{project_id}/training/keras/{learn_id}", api_key, method="POST", body=params)
    print(
        f"  training params set: {model_type}, {TRAINING_CYCLES} cycles, lr {LEARNING_RATE}, "
        f"auto class weights on, int8 profiling on"
    )


def report_results(project_id, api_key, learn_id):
    """Print the real per-class numbers Edge Impulse returns - no derived figures."""
    meta = request(f"/{project_id}/training/keras/{learn_id}/metadata", api_key)
    print("\n--- Validation (training job, from model metadata) ---")
    for key in ("objectDetectionLastLayer", "imageInputScaling", "mode"):
        if meta.get(key) is not None:
            print(f"  {key}: {meta[key]}")
    for variant in meta.get("modelValidationMetrics", []) or []:
        print(f"\n  variant {variant.get('type')}: loss={variant.get('loss')}")
        print(f"    confusion matrix: {variant.get('confusionMatrix')}")
        print(f"    report (precision/recall/F1/support): {json.dumps(variant.get('report'))}")

    print("\n--- Held-out model test (classify job over the real testing split) ---")
    job = request(f"/{project_id}/jobs/classify", api_key, method="POST", body={})
    wait_for_job(project_id, api_key, job["id"], "model testing")
    result = request(f"/{project_id}/classify/all/result", api_key)
    accuracy = result.get("accuracy") or {}
    print(f"  total: {accuracy.get('totalSummary')}")
    print("  per class (good/bad counts, reported separately - not averaged):")
    for label, counts in (accuracy.get("summaryPerClass") or {}).items():
        good, bad = counts.get("good", 0), counts.get("bad", 0)
        total = good + bad
        rate = f"{good / total * 100:.1f}%" if total else "n/a"
        print(f"    {label}: {good}/{total} correct ({rate})")
    print(f"  confusion matrix: {json.dumps(accuracy.get('confusionMatrixValues'))}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-impulse", action="store_true", help="reuse the existing impulse")
    args = ap.parse_args()

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    if not api_key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID environment variables first.", file=sys.stderr)
        sys.exit(1)

    check_data(project_id, api_key)

    print("\nBuilding impulse...")
    if args.skip_impulse:
        impulse = request(f"/{project_id}/impulse", api_key).get("impulse") or {}
        dsp_id = impulse["dspBlocks"][0]["id"]
        learn_id = impulse["learnBlocks"][0]["id"]
        print(f"  reusing impulse: dsp {dsp_id}, learn {learn_id}")
    else:
        dsp_id, learn_id = build_impulse(project_id, api_key)
        configure_dsp(project_id, api_key, dsp_id)

    print("\nGenerating features...")
    job = request(
        f"/{project_id}/jobs/generate-features",
        api_key,
        method="POST",
        body={"dspId": dsp_id, "calculateFeatureImportance": False, "skipFeatureExplorer": True},
    )
    wait_for_job(project_id, api_key, job["id"], "feature generation")

    print("\nConfiguring training...")
    model_type = select_fomo_model(project_id, api_key)
    params = training_params(model_type)
    configure_training(project_id, api_key, learn_id, params, model_type)

    print("\nTraining...")
    # jobs/train/keras/{learnId} both sets and starts: it rejects a body with no
    # settable property ({"success": false, "error": "Not updated configuration..."}),
    # so the same params used to configure the block above have to ride along here too.
    job = request(f"/{project_id}/jobs/train/keras/{learn_id}", api_key, method="POST", body=params)
    wait_for_job(project_id, api_key, job["id"], "training")

    report_results(project_id, api_key, learn_id)
    print(f"\nFull results at https://studio.edgeimpulse.com/studio/{project_id}/testing")


if __name__ == "__main__":
    main()
