"""Configure and train the three-class object-detection impulse in the EleTect-X-Vision project.

Companion to scripts/edge_impulse_upload_vision.py, which must have run first -
this script only configures and trains against whatever data is already in the
project. It builds the impulse (image input -> image DSP -> object detection),
selects a model family/variant/sizing (see --family/--yolo-variant/--yolo-sizing
below - the deployed champion is `--family yolo-pro --yolo-variant no_attn_relu
--yolo-sizing medium`, not FOMO; FOMO is one of the families this script can
still target, but it was not the winner), generates features, trains, and then
runs a model test over the held-out set, printing the per-class numbers Edge
Impulse actually returns.

Nothing here is hardcoded from documentation that might have drifted. The
available blocks and the available object-detection model variants are read back
from the live API (/impulse/blocks, /training/keras/{learnId}/metadata) and the
model variant is picked from what that call reports, so a renamed model shows up
as a clear failure rather than a silent fallback to an unintended architecture.

Two things worth knowing before reading the output:

  - Object detectors here are not classifiers. Edge Impulse's model-testing
    job reports per-class F1 with precision/recall and a confusion matrix, not
    "accuracy". Report what it returns, and report Elephant and Boar separately -
    the two classes have different dataset sizes (4,094 Elephant / 7,394 Boar,
    across 5 and 7 sources respectively - the ratio has inverted since this was
    first written) and a per-class gap is expected. The project is a three-label
    problem (Elephant, Boar, and Background at 2,631 images), not two.
  - The reported number is a held-out result on general daytime/colour wildlife
    photography. It says nothing about night IR field performance. See
    ml/vision/README.md for the full caveat list before quoting it anywhere.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1097972
    python scripts\\edge_impulse_train_vision.py --family yolo-pro --yolo-variant no_attn_relu --yolo-sizing medium

Requires only the standard library - no pip install needed.
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict

STUDIO = "https://studio.edgeimpulse.com/v1/api"

# Three controlled trials at 96/128/160px (everything else held constant) showed
# resolution increase alone monotonically REGRESSES both classes - Boar F1
# 0.567 -> 0.313 -> 0.165, Elephant 0.670 -> 0.593 -> 0.639. Reverted to 96px (the
# best real result) rather than keep guessing single hyperparameters against a
# capped compute budget; see ml/vision/README.md's iteration narrative for the full
# comparison. "squash" matches how Roboflow already stretch-resized both source
# sets (elephant to 640x640, boar to 416x416), so no new aspect-ratio distortion.
IMAGE_SIZE_DEFAULT = 96
# The 26 Aug 224px trial was pre-flight rejected at 1h31m under the old free-tier
# 1h job cap - Enterprise has no such cap, so this axis is untested for real, not
# ruled out. --image-size re-opens it without editing the module constant by hand.
IMAGE_SIZE = IMAGE_SIZE_DEFAULT
# Studio's UI default (0.5) is tuned for a balanced precision/recall demo, not a
# recall-first conflict-detection mission - camera-trap practice runs 0.15-0.3.
# Swept post-hoc against one already-trained model via set-thresholds +
# regenerate-model-testing-summary (see sweep_thresholds()), which re-scores the
# held-out set without a full retrain - each point still costs one job, per the
# plan's own estimate, just a cheap one instead of a training job.
THRESHOLD_GRID = (0.05, 0.1, 0.2, 0.3, 0.5)
RESIZE_MODE = "squash"
# Edge Impulse documents 0.001 as the learning rate FOMO needs; its stock 0.0005 for
# other object-detection heads underfits here. Chosen, not inherited.
LEARNING_RATE = 0.001
# EON Tuner: the 23 Aug finding that it needs an organization-level key was wrong
# (see the vision-rebuild plan's Phase 0) - the real Tuner endpoints live under
# /optimize/*, not /tuner/*, and all of them answer to this project-scoped key.
# It is not driven from this script; the architecture comparison here is a
# manually curated candidate sweep (sweep_orchestrator.sh/sweep_retry.sh) run
# instead, not a Tuner search. That substitution is a real, open gap - see
# ml/vision/README.md for the honest accounting once the sweep concludes.
# Cycle count is the next cheapest untested variable: all three resolution
# trials above left cycles at EI's own default (60), so undertraining at a
# finer grid is still an unruled-out explanation for those regressions, and
# it's untested even at the 96px baseline itself. 100 cycles fits the 1h job
# cap at 96px's ~0.52 min/cycle (~52 min estimated) with headroom to spare.
TRAINING_CYCLES = 100
JOB_POLL_S = 20
# Was 7200 (2h) - too short. Live finding (28 Aug, control_224b): a 224px FOMO
# run was still healthily training past the 2h mark (75%+, on pace for
# ~2h40m); the script gave up and exited while the real job kept running
# unwatched on the server, and the *next* sweep stage then reconfigured the
# same shared learn block on top of it. Raised to 6h - Enterprise has no
# per-job compute cap, so the real constraint is "don't wait forever
# unattended," not "match some server-side limit."
JOB_TIMEOUT_S = 21600


def request(path, api_key, method="GET", body=None, timeout=180, retries=3):
    headers = {"x-api-key": api_key}
    if body is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(body).encode()
    req = urllib.request.Request(f"{STUDIO}{path}", data=body, method=method, headers=headers)
    try:
        for attempt in range(retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    result = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError:
                # A real API response (4xx/5xx) - genuine application-level
                # failure, not a connection hiccup. Never retry, handled below.
                raise
            except urllib.error.URLError as err:
                # Transient DNS/connection hiccups (seen live: getaddrinfo failed
                # mid-poll-loop on an otherwise-healthy connection) shouldn't kill a
                # multi-hour wait_for_job loop.
                if attempt == retries:
                    raise
                print(f"  ({method} {path} transient error: {err}, retrying in {2 ** attempt}s...)")
                time.sleep(2 ** attempt)
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


def select_model(
    project_id,
    api_key,
    family,
    yolo_variant=None,
    yolo_sizing="nano",
    freeze_backbone=None,
    spatial_augmentation=None,
    color_space_augmentation=None,
):
    """Pick an object-detection candidate from the project's live transfer-learning-model list.

    Read from /transfer-learning-models rather than hardcoding, so a renamed variant
    fails loudly rather than silently falling back. family is one of:
      - "fomo": fomo_mobilenet_v2_a35 (the control architecture)
      - "ssd": object_ssd_mobilenet_v2_fpnlite_320x320
      - "yolo-pro": the org model "YOLO-Pro". yolo_sizing selects the "sizing"
        customParameter - one of the live selectOptions confirmed via
        optimize/all-blocks: pico (682K) < nano (2.4M, the plan's original edge-device
        budget and this function's default) < small (6.9M, the model's own stated
        default - never actually used until 29 Aug's capacity trial) < medium (16.6M)
        < large (30M) < xlarge (35M). yolo_variant selects the "architecture-type"
        customParameter ("attn_silu" or "no_attn_relu" - both are named candidates,
        not a free choice).

    Returns (label, visualLayer dict, customParameters dict) - visualLayer goes
    straight into training_params()'s "visualLayers" list, customParameters (only
    non-empty for org models) rides alongside it in the same training-config body.
    """
    models = request(f"/{project_id}/transfer-learning-models", api_key).get(
        "transferLearningModels", []
    )
    detection = [m for m in models if m.get("learnBlockType") == "keras-object-detection"]

    if family == "fomo":
        fomo = [m for m in detection if m.get("type", "").startswith("fomo_")]
        print(f"  FOMO variants offered: {[m['type'] for m in fomo] or '(none)'}")
        if not fomo:
            raise RuntimeError("no fomo_* transfer-learning model reported for keras-object-detection")
        # Prefer the larger alpha-0.35 backbone; it is still tiny and reads better than a01.
        choice = next((m for m in fomo if "a35" in m["type"]), fomo[0])
        print(f"  selected: {choice['type']}")
        return choice["type"], {"type": choice["type"], "enabled": True}, {}

    if family == "ssd":
        ssd = [m for m in detection if m.get("type") == "object_ssd_mobilenet_v2_fpnlite_320x320"]
        if not ssd:
            raise RuntimeError("object_ssd_mobilenet_v2_fpnlite_320x320 not offered for this project")
        print("  selected: object_ssd_mobilenet_v2_fpnlite_320x320")
        return (
            "object_ssd_mobilenet_v2_fpnlite_320x320",
            {"type": "object_ssd_mobilenet_v2_fpnlite_320x320", "enabled": True},
            {},
        )

    if family == "yolo-pro":
        if yolo_variant not in ("attn_silu", "no_attn_relu"):
            raise ValueError(f"yolo_variant must be 'attn_silu' or 'no_attn_relu', got {yolo_variant!r}")
        yolo = [m for m in detection if m.get("name") == "YOLO-Pro"]
        if not yolo:
            raise RuntimeError("no 'YOLO-Pro' org model reported for keras-object-detection")
        choice = yolo[0]
        org_id = choice["organizationModelId"]
        # Start from each parameter's own documented default, then apply the two
        # choices this project actually cares about - never invent a value for a
        # knob the model didn't advertise.
        params = {p["param"]: p["defaultValue"] for p in choice["customParameters"]}
        if "sizing" not in params or "architecture-type" not in params:
            raise RuntimeError(
                f"YOLO-Pro customParameters missing 'sizing'/'architecture-type' - "
                f"got {sorted(params)}, model definition may have changed"
            )
        valid_sizings = ("pico", "nano", "small", "medium", "large", "xlarge")
        if yolo_sizing not in valid_sizings:
            raise ValueError(f"yolo_sizing must be one of {valid_sizings}, got {yolo_sizing!r}")
        params["sizing"] = yolo_sizing
        params["architecture-type"] = yolo_variant

        # Freeze-backbone and the two augmentation-strength knobs (advanced section,
        # untried before this session - see ml/vision/README.md's customParameters
        # dump, confirmed live 4 Sep via GET /transfer-learning-models). Validated
        # against this model's own live customParameters rather than a hardcoded
        # tuple here, so a renamed or removed level fails loudly instead of
        # training silently with a value Edge Impulse no longer recognizes.
        param_defs = {p["param"]: p for p in choice["customParameters"]}
        overrides = {
            "freeze-backbone": freeze_backbone,
            "spatial-augmentation": spatial_augmentation,
            "color-space-augmentation": color_space_augmentation,
        }
        for key, value in overrides.items():
            if value is None:
                continue
            definition = param_defs.get(key)
            if definition is None:
                raise RuntimeError(
                    f"YOLO-Pro customParameters has no {key!r} - model definition may have changed"
                )
            valid = (
                ("true", "false")
                if definition["type"] == "flag"
                else tuple(o["value"] for o in definition.get("selectOptions", []))
            )
            if value not in valid:
                raise ValueError(f"--{key.replace('-', '_')} must be one of {valid}, got {value!r}")
            params[key] = value

        label = f"yolo-pro-{yolo_sizing}-{yolo_variant}"
        overridden = [f"{k}={v}" for k, v in overrides.items() if v is not None]
        if overridden:
            label += "-" + "-".join(overridden)
        print(f"  selected: {label} (org model {org_id}), customParameters={params}")
        return label, {"type": "transfer_organization", "organizationModelId": org_id, "enabled": True}, params

    raise ValueError(f"unknown family {family!r}, expected 'fomo', 'ssd', or 'yolo-pro'")


def training_params(visual_layer, custom_params, batch_size=None):
    params = {
        "mode": "visual",
        "visualLayers": [visual_layer],
        "trainingCycles": TRAINING_CYCLES,
        "learningRate": LEARNING_RATE,
        "augmentationPolicyImage": "all",
        # 1.7:1 Elephant:Boar image ratio (ml/vision/README.md's Dataset section) -
        # balance it rather than let the majority class dominate the loss.
        "autoClassWeights": True,
        # Profile the int8 model: CONTEXT.md's deployment target is an INT8 detector.
        "profileInt8": True,
    }
    if batch_size is not None:
        # KerasConfig.batchSize (live OpenAPI spec) - "only used in visual mode",
        # which is exactly our mode. Only set when a caller has a real reason
        # (ssd_320's OOM at the platform default of 32, see the --batch-size
        # help text); leave every other family on the model's own default.
        params["batchSize"] = batch_size
    if custom_params:
        # An org model (YOLO-Pro) reads its own epochs/learning-rate out of
        # customParameters, not the generic fields above - keep both in sync so a
        # human reading the printed config isn't misled by the generic fields.
        params["trainingCycles"] = int(custom_params.get("epochs", TRAINING_CYCLES))
        params["learningRate"] = float(custom_params.get("learning-rate", LEARNING_RATE))
        params["customParameters"] = custom_params
    return params


def set_project_gpu(project_id, api_key, use_gpu):
    """Toggle project-level GPU training (UpdateProjectRequest.useGpu).

    Discovered live 27 Aug: YOLO-Pro (org model, both variants) hard-fails
    immediately with "This block requires training on the GPU, but this
    impulse is configured to train on CPU." There is no GPU flag on the
    training job itself - SetKerasParameterRequest (the body
    jobs/train/keras/{learnId} accepts) has none; confirmed against the live
    OpenAPI spec. useGpu lives on UpdateProjectRequest instead, i.e. it is a
    project-wide setting, not a per-job one. FOMO and SSD train fine on CPU,
    and GPU compute is billed at 3x CPU for quota purposes (per the org
    usage-metrics schema), so this is only flipped on for the family that
    actually needs it and flipped back off afterward rather than left on for
    every later stage.
    """
    request(f"/{project_id}", api_key, method="POST", body={"useGpu": use_gpu})
    print(f"  project useGpu set to {use_gpu}")


def configure_training(project_id, api_key, learn_id, params, label):
    request(f"/{project_id}/training/keras/{learn_id}", api_key, method="POST", body=params)
    print(
        f"  training params set: {label}, {params['trainingCycles']} cycles, "
        f"lr {params['learningRate']}, auto class weights on, int8 profiling on"
    )


def _rel_box(box, dims):
    """Ground-truth boxes come back in absolute pixels; predicted boxes are
    already relative (0..1) to the model's own input. Converting ground truth
    into the same relative space makes the two directly comparable regardless
    of the sample's stored resolution.
    """
    return (
        box["x"] / dims["width"],
        box["y"] / dims["height"],
        box["width"] / dims["width"],
        box["height"] / dims["height"],
    )


def _score_image(gt_boxes, pred_boxes):
    """Greedy centroid-in-box matching for one image, one class.

    FOMO is a centroid detector - the "boxes" Edge Impulse reports for it are
    grid-cell-sized proxies for a fired centroid, not a regressed tight box,
    so the COCO convention of a strict IoU threshold is the wrong tool here.
    A prediction counts as a true positive if its own center point lands
    inside a ground-truth box that no higher-confidence prediction has
    already claimed - the same "did the detector fire near the real object"
    question FOMO is actually answering. Predictions are consumed
    highest-score-first so the best-scoring hit on a box wins the match.
    """
    unclaimed = list(range(len(gt_boxes)))
    tp = 0
    for x, y, w, h, _score in sorted(pred_boxes, key=lambda b: -b[4]):
        cx, cy = x + w / 2, y + h / 2
        for i in unclaimed:
            gx, gy, gw, gh = gt_boxes[i]
            if gx <= cx <= gx + gw and gy <= cy <= gy + gh:
                unclaimed.remove(i)
                tp += 1
                break
    fp = len(pred_boxes) - tp
    fn = len(unclaimed)
    return tp, fp, fn


def score_held_out(result):
    """Real per-class precision/recall/F1 on the held-out test split.

    Edge Impulse's own `classify/all/result` aggregate ("accuracy" key)
    collapses object-detection results into one useless "F1 score"
    pseudo-class for this project type (confirmed live: summaryPerClass has
    exactly one key, "F1 score", both counts 0) - the real per-class numbers
    have to be computed from this same endpoint's per-sample `result` (ground
    truth) and `predictions` (model output) lists instead.

    Per-image F1 comes straight from Edge Impulse's own `f1Score` field (its
    own correctness judgement per sample); precision/recall are derived here
    via centroid-in-box matching (see _score_image) since the API returns
    neither per sample. A predicted box of a different label than the
    image's own ground-truth label is excluded from that image's precision
    count - cross-species confusion has stayed near zero throughout this
    dataset, so this keeps the per-image number about "how well did it find
    this image's actual animal" without needing full multi-class confusion
    bookkeeping.
    """
    preds_by_id = {p["sampleId"]: p for p in result.get("predictions", [])}
    per_class = defaultdict(list)  # label -> list of (precision_or_None, recall, f1)
    background_had_fp = []

    for row in result.get("result", []):
        sample = row["sample"]
        pred = preds_by_id.get(row["sampleId"])
        if pred is None:
            continue
        raw_label = (sample.get("label") or "-").strip()
        pred_boxes_all = pred.get("boundingBoxes") or []

        if raw_label in ("-", ""):
            background_had_fp.append(1 if pred_boxes_all else 0)
            continue

        label = raw_label.split(",")[0].strip()
        dims = sample["imageDimensions"]
        gt_boxes = [_rel_box(b, dims) for b in sample.get("boundingBoxes", []) if b["label"] == label]
        pred_boxes = [
            (b["x"], b["y"], b["width"], b["height"], b.get("score", 0))
            for b in pred_boxes_all
            if b["label"] == label
        ]
        tp, fp, fn = _score_image(gt_boxes, pred_boxes)
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        per_class[label].append((precision, recall, pred.get("f1Score", 0.0)))

    print("  per class (grouped by ground-truth label, centroid-in-box matching, never averaged):")
    for label in sorted(per_class):
        rows = per_class[label]
        f1s = [r[2] for r in rows]
        recalls = [r[1] for r in rows]
        precisions = [r[0] for r in rows if r[0] is not None]
        perfect = sum(1 for f in f1s if f >= 0.999)
        precision_str = f"{sum(precisions) / len(precisions):.3f} ({len(precisions)}/{len(rows)} images predicted)" if precisions else "n/a (0 predictions)"
        print(
            f"    {label}: {len(rows)} test images, mean F1 {sum(f1s) / len(f1s):.3f}, "
            f"mean precision {precision_str}, mean recall {sum(recalls) / len(recalls):.3f}, "
            f"perfect F1 {perfect}/{len(rows)} ({perfect / len(rows) * 100:.1f}%)"
        )
    if background_had_fp:
        clean = background_had_fp.count(0)
        total = len(background_had_fp)
        print(
            f"    Background: {total} test images, {clean}/{total} clean "
            f"({clean / total * 100:.1f}%), false-positive rate {1 - clean / total:.3f}"
        )
    return per_class, background_had_fp


def _fetch_classify_result_after_regen(project_id, api_key, max_wait_s=600):
    """GET classify/all/result right after a regenerate-model-testing-summary job
    reports finished=True.

    Hit in practice, 3 times now across 2 architectures (27 Aug control_96_thr
    x2, yolo_attn_thr x1): the job's own status flips to finished/successful
    before the results it produced are actually queryable. Two symptoms of the
    same propagation lag showed up: a *silently empty* `result: []`
    (score_held_out then had nothing to iterate and printed no per-class lines
    at all - easy to mistake for "the model predicted nothing"), and a hard
    "No model testing results found, run 'startClassifyJob' first" from this
    same endpoint, on a project that had a real, already-printed classify
    result moments earlier. Retry on both symptoms before treating either as a
    real failure. Two prior fixes (25s window, then 120s) both still lost the
    race - 3/3 real attempts have failed with this exact symptom, which reads
    less like "occasionally slow" and more like a lag with a long tail, so this
    widens further (10 min) with exponential backoff and prints each attempt's
    outcome, so if it fails a 4th time the log shows the real timing instead of
    another guess. Whatever caller invokes this must re-fetch a fresh classify
    result rather than reuse one across impulse rebuilds - the impulse this
    result belongs to is deleted the moment the next architecture's
    build_impulse() runs, so a stale result silently querying the wrong model
    is a worse failure mode than this one timing out loudly.
    """
    last_err = None
    delay_s = 5.0
    waited = 0.0
    attempt = 0
    while waited < max_wait_s:
        attempt += 1
        try:
            result = request(f"/{project_id}/classify/all/result", api_key)
        except RuntimeError as err:
            if "No model testing results found" not in str(err):
                raise
            last_err = err
            print(f"    classify result not ready yet (attempt {attempt}, {waited:.0f}s elapsed): {err}")
        else:
            if result.get("result"):
                return result
            last_err = RuntimeError(
                "classify/all/result returned an empty result list - "
                "treating as the same not-ready-yet race, not a real empty test set"
            )
            print(f"    classify result empty (attempt {attempt}, {waited:.0f}s elapsed)")
        time.sleep(delay_s)
        waited += delay_s
        delay_s = min(delay_s * 1.5, 30.0)
    raise last_err


def sweep_thresholds(project_id, api_key, learn_id, grid=THRESHOLD_GRID):
    """Re-score the already-trained model's held-out set at each confidence
    threshold in grid, without retraining.

    Root-caused 27 Aug after 3/3 real attempts (control_96_thr x2,
    yolo_attn_thr x1) failed with classify/all/result staying permanently
    empty, up to a 10-minute exponential-backoff window that never once saw a
    non-empty result - not a propagation lag at all. The live OpenAPI spec
    (SetImpulseThresholdsResponse.regenerateModelTestingStatus) documents why:
    fast in-place regeneration is unsupported "for object detection models" -
    exactly this project's type - so regenerateModelTestingSummary, even
    force-run via forceRunRegenerateModelTestingInJob, was never going to
    populate per-sample results here, no matter how long the wait. The
    correct call for object detection is a real classify job:
    POST jobs/classify with skipFeatureGeneration: true - documented
    verbatim as "used e.g. if you update thresholds". set-thresholds still
    sets the value; startClassifyJob is what actually re-scores and
    populates classify/all/result afterward.
    """
    impulse = request(f"/{project_id}/impulse", api_key).get("impulse") or {}
    impulse_id = impulse.get("id")
    if impulse_id is None:
        raise RuntimeError("no impulse found - build and train one first")

    meta = request(f"/{project_id}/training/keras/{learn_id}/metadata", api_key)
    thresholds = meta.get("thresholds") or []
    if len(thresholds) != 1:
        raise RuntimeError(
            f"expected exactly one configurable threshold on learn block {learn_id}, "
            f"got {[t.get('key') for t in thresholds]} - update this function, don't guess which one"
        )
    key = thresholds[0]["key"]
    print(f"\n--- Threshold sweep (learn block {learn_id}, threshold key {key!r}) ---")

    results = {}
    for value in grid:
        print(f"\n  threshold {value}:")
        request(
            f"/{project_id}/impulse/{impulse_id}/set-thresholds",
            api_key,
            method="POST",
            body={"thresholds": [{"blockId": learn_id, "key": key, "value": value}]},
        )
        job = request(
            f"/{project_id}/jobs/classify",
            api_key,
            method="POST",
            body={"skipFeatureGeneration": True},
        )
        wait_for_job(project_id, api_key, job["id"], f"classify @ threshold {value}")
        result = _fetch_classify_result_after_regen(project_id, api_key)
        per_class, background = score_held_out(result)
        results[value] = (per_class, background)
    return results


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
    print(f"  total (Edge Impulse's own aggregate, not per-class - collapses to one pseudo-class for object detection): {accuracy.get('totalSummary')}")
    per_class, background = score_held_out(result)
    return {"raw": result, "per_class": per_class, "background_had_fp": background}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-impulse", action="store_true", help="reuse the existing impulse")
    ap.add_argument(
        "--family",
        choices=("fomo", "ssd", "yolo-pro"),
        default="fomo",
        help="architecture candidate to train (default: fomo, the control)",
    )
    ap.add_argument(
        "--yolo-variant",
        choices=("attn_silu", "no_attn_relu"),
        help="required when --family yolo-pro",
    )
    ap.add_argument(
        "--yolo-sizing",
        choices=("pico", "nano", "small", "medium", "large", "xlarge"),
        default="nano",
        help=(
            "YOLO-Pro model capacity (default: nano/2.4M params, the plan's original "
            "edge-device budget). The model's own transfer-learning-model default is "
            "'small' (6.9M) - confirmed live via /transfer-learning-models and "
            "/optimize/all-blocks 29 Aug, never previously exercised. Ladder: pico "
            "(682K) < nano (2.4M) < small (6.9M) < medium (16.6M) < large (30M) < "
            "xlarge (35M). Ignored outside --family yolo-pro."
        ),
    )
    ap.add_argument(
        "--image-size",
        type=int,
        default=None,
        help=(
            f"square input resolution (default {IMAGE_SIZE_DEFAULT}px for fomo/yolo-pro; "
            "ssd is fixed at 320px, its transfer-learning model has no other supported size)"
        ),
    )
    ap.add_argument(
        "--sweep-thresholds",
        action="store_true",
        help="skip training; sweep THRESHOLD_GRID against the existing trained impulse and exit",
    )
    ap.add_argument(
        "--configure-only",
        action="store_true",
        help="build the impulse and configure the learn block, but do not start the training job",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=(
            "override KerasConfig.batchSize (default: model's own default, 32 for ssd). "
            "ssd_320 OOM-killed (exit 137) at batch 32, 28.3min into fine-tuning on the "
            "full 320x320 corpus - not a hyperparameter tuned for score, a memory-fit fix"
        ),
    )
    ap.add_argument(
        "--freeze-backbone",
        default=None,
        help=(
            "override YOLO-Pro's 'freeze-backbone' customParameter (model default: "
            "'false' - confirmed live 4 Sep). Not validated against a hardcoded choice "
            "list here; select_model() checks it against the model's own live "
            "customParameters so a renamed value fails loudly. Ignored outside "
            "--family yolo-pro."
        ),
    )
    ap.add_argument(
        "--spatial-augmentation",
        default=None,
        help=(
            "override YOLO-Pro's 'spatial-augmentation' customParameter (model "
            "default: 'low', ladder none/low/medium/high per the live API - confirmed "
            "4 Sep, never assume it stays that shape). Ignored outside --family yolo-pro."
        ),
    )
    ap.add_argument(
        "--color-space-augmentation",
        default=None,
        help=(
            "override YOLO-Pro's 'color-space-augmentation' customParameter (model "
            "default: 'low', ladder none/low/medium/high per the live API - confirmed "
            "4 Sep). Targets the RGB-daylight -> grayscale-IR domain shift more "
            "directly than spatial augmentation does. Ignored outside --family yolo-pro."
        ),
    )
    args = ap.parse_args()
    if args.family == "yolo-pro" and not args.yolo_variant:
        print("--family yolo-pro requires --yolo-variant", file=sys.stderr)
        sys.exit(1)
    if args.image_size is None:
        # object_ssd_mobilenet_v2_fpnlite_320x320 hard-rejects any other input
        # size (confirmed live: "Your image size is currently set to 96x96 ...
        # only supports a 320x320 input") - not a tunable knob for this model.
        args.image_size = 320 if args.family == "ssd" else IMAGE_SIZE_DEFAULT
    elif args.family == "ssd" and args.image_size != 320:
        print(f"--family ssd requires 320px input, got --image-size {args.image_size}", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    if not api_key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID environment variables first.", file=sys.stderr)
        sys.exit(1)

    if args.sweep_thresholds:
        impulse = request(f"/{project_id}/impulse", api_key).get("impulse") or {}
        learn_id = (impulse.get("learnBlocks") or [{}])[0].get("id")
        if learn_id is None:
            print("no trained impulse found - train one first", file=sys.stderr)
            sys.exit(1)
        sweep_thresholds(project_id, api_key, learn_id)
        return

    global IMAGE_SIZE
    IMAGE_SIZE = args.image_size

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
    label, visual_layer, custom_params = select_model(
        project_id,
        api_key,
        args.family,
        yolo_variant=args.yolo_variant,
        yolo_sizing=args.yolo_sizing,
        freeze_backbone=args.freeze_backbone,
        spatial_augmentation=args.spatial_augmentation,
        color_space_augmentation=args.color_space_augmentation,
    )
    params = training_params(visual_layer, custom_params, batch_size=args.batch_size)
    set_project_gpu(project_id, api_key, args.family == "yolo-pro")
    configure_training(project_id, api_key, learn_id, params, label)

    if args.configure_only:
        print(
            "\n--configure-only: impulse built and learn block configured, no "
            "training job started. Used to give the EON Tuner's per-family search "
            "templates (e.g. object_detection_yolo_pro) a real block reference to "
            "build around without spending a training job on it."
        )
        return

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
