"""Configure and train the five-class acoustic impulse in the EleTect-X-Acoustic project.

Companion to scripts/edge_impulse_upload_acoustic.py, which must have run first -
this script only configures and trains against whatever data is already in the
project. It builds the impulse (time-series audio input -> MFE -> Keras
classification), generates features, trains, and then runs a real model-testing
job over the held-out set, printing the per-class numbers Edge Impulse actually
returns - never averaged into one headline figure, since gunshot / chainsaw /
vehicle / animal_call / ambient come from four different recording contexts and
four different sets of equipment (see ml/acoustic/README.md's Dataset section)
and have no reason to perform evenly.

Block types and DSP config are read back from the live /impulse/blocks and
/dsp/{id} endpoints rather than hardcoded, same discipline as
scripts/edge_impulse_train_vision.py - a renamed block type fails loudly here
instead of silently building the wrong impulse.

DSP block: MFE (mel-filterbank energy), not MFCC. MFCC's cepstral truncation is
built for speech, where the discarded fine spectral detail is formant
structure a listener doesn't need. Here it would discard exactly the detail
that separates a gunshot's broadband transient shape from a chainsaw's
harmonic engine whine - both classes need the full mel-band energy profile MFE
keeps. Spectrogram was the fallback if MFE underperformed; it did not need to
be used (see ml/acoustic/README.md's Impulse section for the real result).
This script does not override the block's own default frame length / stride /
filter count - they are printed after configuration so the actual values used
are visible, rather than assumed from documentation that may have drifted.

One window per clip: window size and window increase are both set to
CLIP_SECONDS (matching scripts/edge_impulse_upload_acoustic.py's fixed 4.0 s
clip length), so no window can span two clips or be labelled with one class
while partly covering silence padded in from a shorter source clip.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1094275
    python scripts\\edge_impulse_train_acoustic.py

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

# Must match scripts/edge_impulse_upload_acoustic.py's SAMPLE_RATE_HZ / CLIP_SECONDS exactly -
# a mismatch here would silently misalign every uploaded window.
SAMPLE_RATE_HZ = 8000
CLIP_SECONDS = 4.0
WINDOW_SIZE_MS = int(CLIP_SECONDS * 1000)
WINDOW_INCREASE_MS = WINDOW_SIZE_MS  # one window per clip, no overlap

# In order of preference: MFE first (see module docstring), spectrogram as the fallback if a
# project has no MFE block for some reason, MFCC last since it's tuned for speech.
DSP_TYPE_PREFERENCE = ("mfe", "spectrogram", "mfcc")

LEARNING_RATE = 0.001
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
    # application-level rejections - catch that here rather than let every call site
    # guess at a missing field.
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
            "Both categories must hold data - run scripts/edge_impulse_upload_acoustic.py first.",
            file=sys.stderr,
        )
        sys.exit(1)
    labels = request(f"/{project_id}/raw-data/labels", api_key).get("labels", [])
    print(f"  labels present: {sorted(labels)}")
    expected = {"gunshot", "chainsaw", "vehicle", "animal_call", "ambient"}
    missing = expected - set(labels)
    if missing:
        print(f"  WARNING: expected labels missing from the project: {sorted(missing)}")
    return counts


def pick_dsp_type(project_id, api_key):
    blocks = request(f"/{project_id}/impulse/blocks", api_key)
    dsp_types = {b["type"] for b in blocks.get("dspBlocks", [])}
    input_types = {b["type"] for b in blocks.get("inputBlocks", [])}
    learn_types = {b["type"] for b in blocks.get("learnBlocks", [])}
    print(f"  available input block types: {sorted(input_types)}")
    print(f"  available dsp block types: {sorted(dsp_types)}")
    print(f"  available learn block types: {sorted(learn_types)}")

    dsp_type = next(
        (t for pref in DSP_TYPE_PREFERENCE for t in dsp_types if pref in t.lower()), None
    )
    if dsp_type is None:
        raise RuntimeError(f"none of {DSP_TYPE_PREFERENCE} found among dsp blocks {sorted(dsp_types)}")

    input_type = next((t for t in input_types if "time" in t.lower() or "series" in t.lower()), None)
    if input_type is None:
        raise RuntimeError(f"no time-series input block found among {sorted(input_types)}")

    learn_type = next((t for t in learn_types if t == "keras"), None)
    if learn_type is None:
        raise RuntimeError(f"no plain 'keras' classification learn block found among {sorted(learn_types)}")

    print(f"  selected: input={input_type!r} dsp={dsp_type!r} learn={learn_type!r}")
    return input_type, dsp_type, learn_type


def build_impulse(project_id, api_key, input_type, dsp_type, learn_type):
    existing = request(f"/{project_id}/impulse", api_key).get("impulse")
    if existing:
        print(f"  impulse already exists (id {existing.get('id')}) - deleting and rebuilding")
        request(f"/{project_id}/impulse", api_key, method="DELETE")

    impulse = {
        "inputBlocks": [
            {
                "id": 1,
                "type": input_type,
                "name": "Time series",
                "title": "Time series data",
                "windowSizeMs": WINDOW_SIZE_MS,
                "windowIncreaseMs": WINDOW_INCREASE_MS,
                "frequencyHz": SAMPLE_RATE_HZ,
                "padZeros": True,
            }
        ],
        "dspBlocks": [
            {
                "id": 2,
                "type": dsp_type,
                "name": dsp_type.upper(),
                "title": dsp_type.upper(),
                "axes": ["audio"],
                "input": 1,
            }
        ],
        "learnBlocks": [
            {
                "id": 3,
                "type": learn_type,
                "name": "Classifier",
                "title": "Classification",
                "dsp": [2],
            }
        ],
    }
    request(f"/{project_id}/impulse", api_key, method="POST", body=impulse)
    print(
        f"  impulse created: {WINDOW_SIZE_MS}ms window @ {SAMPLE_RATE_HZ}Hz -> {dsp_type} -> "
        f"{learn_type} classification"
    )
    return 2, 3


def report_dsp_config(project_id, api_key, dsp_id):
    """Print the DSP block's actual live config - not asserted from documentation.

    No parameters are overridden here; this only makes the values Edge Impulse is
    really using visible, since none of the block's own defaults were changed.
    """
    cfg = request(f"/{project_id}/dsp/{dsp_id}/config", api_key)
    items = cfg.get("config") if isinstance(cfg, dict) else None
    print(f"  DSP block {dsp_id} live config: {json.dumps(items) if items else cfg}")


def training_params():
    return {
        "trainingCycles": TRAINING_CYCLES,
        "learningRate": LEARNING_RATE,
        # Gunshot (747) vs chainsaw (40) is a real, reported imbalance (see
        # ml/acoustic/README.md's Dataset section) - balance it rather than let the
        # majority classes dominate the loss.
        "autoClassWeights": True,
        # Profile the int8 model: CONTEXT.md's deployment target is an INT8 classifier.
        "profileInt8": True,
    }


def configure_training(project_id, api_key, learn_id, params):
    request(f"/{project_id}/training/keras/{learn_id}", api_key, method="POST", body=params)
    print(
        f"  training params set: {TRAINING_CYCLES} cycles, lr {LEARNING_RATE}, "
        f"auto class weights on, int8 profiling on"
    )


def report_results(project_id, api_key, learn_id):
    """Print the real per-class numbers Edge Impulse returns - no derived figures.

    Five classes from four different recording contexts (Mendeley forest AudioMoth,
    ESC-50 field-recorded environmental sound, Freesound hobbyist uploads x2) are
    reported separately, never averaged into one number - see the module docstring.
    """
    meta = request(f"/{project_id}/training/keras/{learn_id}/metadata", api_key)
    print("\n--- Validation (training job, from model metadata) ---")
    for key in ("mode",):
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
        input_type, dsp_type, learn_type = pick_dsp_type(project_id, api_key)
        dsp_id, learn_id = build_impulse(project_id, api_key, input_type, dsp_type, learn_type)
        report_dsp_config(project_id, api_key, dsp_id)

    print("\nGenerating features...")
    job = request(
        f"/{project_id}/jobs/generate-features",
        api_key,
        method="POST",
        body={"dspId": dsp_id, "calculateFeatureImportance": False, "skipFeatureExplorer": True},
    )
    wait_for_job(project_id, api_key, job["id"], "feature generation")

    print("\nConfiguring training...")
    params = training_params()
    configure_training(project_id, api_key, learn_id, params)

    print("\nTraining...")
    # jobs/train/keras/{learnId} both sets and starts: it rejects a body with no
    # settable property, so the same params used to configure the block above have
    # to ride along here too (same convention as edge_impulse_train_vision.py).
    job = request(f"/{project_id}/jobs/train/keras/{learn_id}", api_key, method="POST", body=params)
    wait_for_job(project_id, api_key, job["id"], "training")

    report_results(project_id, api_key, learn_id)
    print(f"\nFull results at https://studio.edgeimpulse.com/studio/{project_id}/testing")


if __name__ == "__main__":
    main()
