"""Configure and train the acoustic impulse for the EleTect-X acoustic project.

Companion to scripts/edge_impulse_upload_acoustic.py, which must have run first -
this script only configures and trains against whatever data is already in the
project. It builds the impulse (time-series audio input -> MFE -> Keras
classification), generates features, trains, and then runs a real model-testing
job over the held-out set, printing the per-class numbers Edge Impulse actually
returns - never averaged into one headline figure, since the classes come from
many different recording contexts and sets of equipment (see ml/acoustic/
README.md's Dataset section) and have no reason to perform evenly.

The class set is a four-member scheme - gunshot, chainsaw, elephant_call,
ambient. The original ADR 0024 amendment scoped a seven-member scheme also
including boar_call and predator_call; both were dropped after the full
exploration (DSP A/B, EON Tuner, transfer learning, and the {3,4,6,8,10}s
window-length sweep) never lifted either above the 14.3% (1/7) chance floor
in any configuration. `vehicle` was added 2026-09-13 and then dropped
2026-09-14: real field recordings exposed a chainsaw/vehicle acoustic
collision that had already been flagged as a risk (see ml/acoustic/README.md's
"Reading these numbers honestly") - chainsaw held-out recall collapsed to
0.0%, confirmed by the training-validation confusion matrix (not just the
held-out split) showing most chainsaw examples predicted vehicle. Removing
vehicle recovered chainsaw to its best score yet (55.7%); see the README's
Result section for the full before/after. Only the classes the upload
script's data floor left trainable (floor_status "trained" or
"trained_below_floor") are actually expected in the project; check_data()
reads dataset_manifest.json for that list rather than hard-coding it.

Block types and DSP config are read back from the live /impulse/blocks and
/dsp/{id} endpoints rather than hardcoded, same discipline as
scripts/edge_impulse_train_vision.py - a renamed block type fails loudly here
instead of silently building the wrong impulse.

DSP block: MFE (mel-filterbank energy) by default, not MFCC. MFCC's cepstral
truncation is built for speech, where the discarded fine spectral detail is
formant structure a listener doesn't need. Here it would discard exactly the
detail that separates a gunshot's broadband transient shape from a chainsaw's
harmonic engine whine, or an elephant trumpet from a big-cat growl - every
class needs the full mel-band energy profile MFE keeps. This was measured, not
just asserted: --dsp mfcc gives a real head-to-head against the locked MFE
config on the identical dataset (see DSP_VARIANTS). Each variant's own config
overrides (mel filter count for MFE, cepstral coefficient count for MFCC) are
applied; frame length / stride keep the block default. The block's live config
is printed after configuration so the actual values are visible.

Learn block: plain "keras" (the locked from-scratch 2-conv net) by default. --learn
selects a keras-transfer-kws pretrained backbone instead, for step 2.5c's A/B against
that from-scratch net - see TRANSFER_MODELS for the confirmed-live options and why
Syntiant NDP10x is excluded.

One window per clip: window size and window increase are both set to
--clip-seconds (default 10.0, the window-length sweep's winner - matching
scripts/edge_impulse_upload_acoustic.py's default clip length), so no window
can span two clips or be labelled with one class while partly covering
silence padded in from a shorter source clip. Pass the same --clip-seconds to
both scripts when running the window-length sweep.

Usage (run from a machine with normal internet access, not a sandboxed one):

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1110036
    python scripts\\edge_impulse_train_acoustic.py

    python scripts\\edge_impulse_train_acoustic.py --clip-seconds 8.0

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

_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
MANIFEST = os.path.join(_ROOT, "ml", "acoustic", "dataset_manifest.json")

# Must match scripts/edge_impulse_upload_acoustic.py's SAMPLE_RATE_HZ exactly -
# a mismatch here would silently misalign every uploaded window.
SAMPLE_RATE_HZ = 8000
DEFAULT_CLIP_SECONDS = 10.0  # window-sweep winner (priority_avg 50.9%)

# In order of preference: MFE first (see module docstring), spectrogram as the fallback if a
# project has no MFE block for some reason, MFCC last since it's tuned for speech.
DSP_TYPE_PREFERENCE = ("mfe", "spectrogram", "mfcc")

# --dsp A/B variants (step 2.5a of the exploration plan). "mfe" is the locked default -
# see the module docstring for why (full mel-band energy vs MFCC's speech-tuned cepstral
# truncation). "mfcc" is measured here as a real head-to-head on the identical uploaded
# dataset, not asserted. Spectrogram is deliberately NOT added as a variant: EI's
# spectrogram block's output bin count (fft_length/2 vs fft_length/2+1, and whether the
# DC/Nyquist bins are dropped) is not something this script verifies against the live
# API, and a wrong "reshape columns" guess either crashes training or silently
# misconfigures it - not a risk worth taking for a block the docstring already expected
# to lose to MFE. reshape_columns is the exact classifier-input width for each variant:
# MFE = num_filters (one energy value per mel band per frame), MFCC = num_cepstral (one
# cepstral coefficient per frame, by definition of what MFCC computes) - both are fixed,
# well-documented facts about each transform, not guesses.
DSP_VARIANTS = {
    "mfe": {
        "config": {"num_filters": 40, "fft_length": 256},
        "reshape_columns": 40,
    },
    "mfcc": {
        "config": {"num_cepstral": 13, "num_filters": 32, "fft_length": 256},
        "reshape_columns": 13,
    },
}

# Both blocks' un-overridden defaults (frame_length 0.02s, frame_stride 0.01s - see
# configure_dsp's docstring). Edge Impulse hard-caps num_frames at 500: confirmed live
# on 11 Sep during the window-length sweep (step 3), where the 6000ms candidate's
# feature-generation job failed with "Number of frames is larger than 500 (598),
# increase your frame stride or decrease your window size." At the locked 10ms stride,
# num_frames = (window - frame_length) / frame_stride + 1, which clears 500 for windows
# up to ~5.0s (3s and 4s candidates are unaffected) but not 6/8/10s.
DEFAULT_FRAME_LENGTH_S = 0.02
DEFAULT_FRAME_STRIDE_S = 0.01
MAX_DSP_FRAMES = 500


def frame_stride_for_window(window_ms, frame_length_s=DEFAULT_FRAME_LENGTH_S,
                             default_stride_s=DEFAULT_FRAME_STRIDE_S, max_frames=MAX_DSP_FRAMES):
    """Widen frame_stride only as much as needed to keep this window under Edge Impulse's
    500-frame cap - not an arbitrary round number, and not touched at all for windows
    where the locked 10ms stride already fits (3s, 4s). This keeps every sweep candidate
    as close to the DSP-A/B-locked config as physically possible, so the sweep still
    compares "the locked config at different window lengths", not five different DSP
    configs. A wider stride does lower temporal resolution for the longer candidates -
    an unavoidable, documented trade-off, not a hidden one (see README's window-sweep
    section once it's written).
    """
    window_s = window_ms / 1000.0
    default_frames = int((window_s - frame_length_s) / default_stride_s) + 1
    if default_frames <= max_frames:
        return default_stride_s
    # Solve for stride so frame count lands comfortably (20 frames) under the cap - not
    # frame-for-frame at the boundary, since EI's own frame-count math may round
    # differently than this estimate (the 6s failure was already off by one: this
    # formula predicts 599, EI reported 598).
    safety_margin_frames = 20
    return (window_s - frame_length_s) / (max_frames - safety_margin_frames - 1)

# --learn A/B variants (step 2.5c). "scratch" is the locked from-scratch 2-conv net
# (classifier_layers() below). The rest are keras-transfer-kws pretrained backbones -
# confirmed live via GET /{project}/transfer-learning-models on 11 Sep 2026 against
# this project. Syntiant NDP10x is deliberately excluded: it targets Syntiant's own
# NDP10x chip, which this project has no hardware for and never will (deployment
# target is the QRB2210 A53 Linux MPU). Per the KerasVisualLayer schema, a transfer
# layer is a single visualLayers entry - "neurons"/"dropoutRate" configure only the
# final head EI attaches on top of the frozen pretrained backbone, not a manually
# built conv/dense stack - so these defaults come straight from the live
# TransferLearningModel response, not guessed.
TRANSFER_MODELS = {
    "transfer_kws_mobilenetv1_a1_d100": {"neurons": 128, "dropoutRate": 0.1},
    "transfer_kws_mobilenetv2_a35_d100": {"neurons": 128, "dropoutRate": 0.1},
    "transfer_kws_conv2d_tiny": {"neurons": 0, "dropoutRate": 0.5},
}

# Discovered live, 11 Sep 2026 (POST /training/keras/{id} rejected every keras-transfer-kws
# arm with "Incompatible input config, transfer learning for keyword spotting currently
# only works with a window size of 1000ms"): this is a hard, block-level EI platform
# constraint, not per-backbone - all three TRANSFER_MODELS entries hit it identically.
# The locked window (now 10000ms - see DEFAULT_CLIP_SECONDS / the module docstring) is
# well above 1000ms because several classes need more than one second of context to
# identify (a sustained
# chainsaw/engine whine or an elephant call is not a single-word "keyword" utterance the
# way KWS transfer models assume). Forcing --clip-seconds 1.0 just for this A/B would
# confound the architecture comparison with an unrelated window-length change - 1s isn't
# even a window-sweep candidate (step 2.5's own list is {3,4,6,8,10}s) - so this path is
# ruled out rather than worked around. Kept here (not deleted) as the record of why.
TRANSFER_REQUIRED_WINDOW_MS = 1000

LEARNING_RATE = 0.001
# 120 was enough for the two-conv net to plateau; 250 on the larger net gained
# nothing (see classifier_layers()). Held here for the smaller net.
TRAINING_CYCLES = 120
# Default OFF per the documented Phase 2c/2bc A/B in training_params() below - but that
# A/B included boar_call/predator_call, since dropped from the wire scheme. --class-weights
# lets a re-test against today's roster override this without touching the default.
# Re-tested 2026-09-13 on the current 5-class roster (widened chainsaw/vehicle data,
# project 1109511, held-out classify job): weights ON dropped chainsaw 23.7%->17.1% and
# vehicle 55.6%->48.5% (both this amendment's target classes), gained gunshot 60.8%->64.1%
# and lost ambient 63.4%->55.4%, elephant_call unchanged at 50.6%. Confirms OFF is still
# the right call even with boar_call/predator_call gone - kept OFF.
AUTO_CLASS_WEIGHTS = False
JOB_POLL_S = 20
JOB_TIMEOUT_S = 7200

# The held-out classify job tags any prediction under this softmax score
# "uncertain". EI's 0.6 default (and even 0.35) buckets most of a 7-class model's
# genuine argmax predictions there, so the reported per-class numbers stop
# reflecting what the model actually decides. Drop it to 0.1 so the held-out
# figure is the model's real argmax accuracy, directly comparable to the
# training-time confusion matrix; the confusion matrix keeps a separate
# "uncertain" column so anything genuinely low-confidence is still visible.
MIN_CONFIDENCE_RATING = 0.1

# MFE 40 filters / 256-point FFT is EI's stock, known-good default for 8 kHz audio
# (see DSP_VARIANTS above). Raising the filter count (48, 64) needs a longer FFT to
# match or the low-frequency mel filters come out all-zero and feature generation
# aborts; the aggressive 64/512 variant built, but combined with heavy augmentation
# it trained to near-random (see ml/acoustic/README.md's tuning notes). Frame length
# / stride stay at each variant's block default (0.02 / 0.01 s).

# Classifier. EI's stock conv1d(8)->conv1d(16)->flatten audio block underfits;
# the opposite extreme - a four-stack CNN with a dense-64 head, heavy dropout and
# aggressive spectrogram augmentation - trained to near-random (26% argmax) on
# ~2000 clips across 7 heterogeneous classes. Two intermediate points were then
# tested head to head on the scratch project at 4.0s:
#   - two-conv 16->32 + dense-24, 120 cycles:   46.4% held-out (252/543)
#   - three-conv 24->48->64 + dense-32, 250 cyc: 45.2% held-out (252/558)
# The extra stack, wider head and 2x cycles bought nothing - the two curves sit
# on top of each other and the train/held-out gap stayed ~4-5 points either way.
# That is a data ceiling, not a capacity ceiling, so the smaller net wins: fewer
# int8 parameters to profile and deploy on the CONTEXT.md target for identical
# accuracy. Further gains have to come from the data (see the gunshot/ambient
# single-rig confound in edge_impulse_upload_acoustic.py), not the architecture.
# reshape_columns is threaded in per --dsp variant (DSP_VARIANTS[<variant>]
# ["reshape_columns"]) so the conv stack always matches the DSP block's real output
# width; the conv/dense shape itself is unchanged across variants - only the DSP
# front-end is what step 2.5a is measuring.
def classifier_layers(reshape_columns):
    return [
        {"type": "reshape", "columns": reshape_columns},
        {"type": "conv1d", "kernelSize": 3, "neurons": 16, "stack": 1, "dropoutRate": 0.25},
        {"type": "conv1d", "kernelSize": 3, "neurons": 32, "stack": 1, "dropoutRate": 0.25},
        {"type": "flatten"},
        {"type": "dense", "neurons": 24, "dropoutRate": 0.4},
    ]


def transfer_layers(model_type):
    """visualLayers for a keras-transfer-kws A/B arm (step 2.5c) - see TRANSFER_MODELS.

    A single layer: the pretrained backbone plus EI's own trainable head, sized by
    that model's own live defaultNeurons/defaultDropout. No reshape/flatten/dense
    stacked on top - the transfer block owns its whole architecture end to end.
    """
    cfg = TRANSFER_MODELS[model_type]
    return [{"type": model_type, "neurons": cfg["neurons"], "dropoutRate": cfg["dropoutRate"]}]

# Spectrogram-domain augmentation OFF. The species classes are small (100-300
# train clips each); on a set this size the high-noise + time/frequency-masking +
# warping policy destroyed more signal than it regularised - training argmax fell
# from ~43% (augmentation off) to 26% (this policy on). A gentler policy can be
# revisited once the base model is solid, but the default here is off.
AUGMENTATION_POLICY = {"enabled": False}


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


def expected_trained_labels():
    """Classes the upload script's data floor left trainable, read from the manifest.

    Returns (labels, note). `labels` is the set of class strings whose manifest
    floor_status is "trained" or "trained_below_floor" - i.e. every class that was
    uploaded and trained, whether or not it cleared CLIP_FLOOR. `note` is a short
    human summary of the data-floor outcome for the log. Falls back to an empty
    set + a warning if the manifest is missing, so this script can still be
    pointed at a hand-populated project.
    """
    try:
        with open(MANIFEST) as fh:
            doc = json.load(fh)
    except FileNotFoundError:
        return set(), f"no manifest at {MANIFEST} - skipping the expected-label check"

    classes = doc.get("classes", {})
    trained = {
        label
        for label, meta in classes.items()
        if meta.get("floor_status") in ("trained", "trained_below_floor")
    }
    below_floor = {
        label
        for label, meta in classes.items()
        if meta.get("floor_status") == "trained_below_floor"
    }
    reserved = {
        label: meta.get("floor_status")
        for label, meta in classes.items()
        if str(meta.get("floor_status", "")).startswith("reserved")
    }
    bits = [f"manifest schema {doc.get('schema')}, window {doc.get('window_seconds')}s"]
    if below_floor:
        bits.append("trained below the 150 floor: " + ", ".join(sorted(below_floor)))
    if reserved:
        bits.append(
            "reserved (not trained): "
            + ", ".join(f"{k} ({v})" for k, v in sorted(reserved.items()))
        )
    if not doc.get("elephant_merge_ready", True):
        bits.append("elephant_call did NOT clear the floor - per-species track is not merge-ready")
    return trained, "; ".join(bits)


def _distinct_labels(project_id, api_key):
    """Distinct raw-data labels in the project.

    Edge Impulse has no single "list the labels" endpoint (`/raw-data/labels`
    collides with the `/raw-data/{sampleId}` route), so page the sample listing
    and collect the distinct `label` fields across both categories.
    """
    labels = set()
    for category in ("training", "testing"):
        offset, page = 0, 1000
        while True:
            resp = request(
                f"/{project_id}/raw-data?category={category}&limit={page}&offset={offset}",
                api_key,
            )
            samples = resp.get("samples", [])
            labels.update(s.get("label") for s in samples if s.get("label"))
            if len(samples) < page:
                break
            offset += page
    return labels


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
    labels = _distinct_labels(project_id, api_key)
    print(f"  labels present: {sorted(labels)}")

    expected, note = expected_trained_labels()
    print(f"  manifest: {note}")
    if expected:
        missing = expected - set(labels)
        if missing:
            print(f"  WARNING: manifest expects these trained labels, absent from the project: {sorted(missing)}")
        unexpected = set(labels) - expected
        if unexpected:
            print(f"  NOTE: project has labels the manifest does not mark trained: {sorted(unexpected)}")
    return counts


def pick_dsp_type(project_id, api_key, variant="mfe", learn="scratch"):
    """Pick the live dsp+learn blocks matching --dsp <variant> and --learn <arch>.

    variant selects from DSP_VARIANTS' keys, not the old fixed DSP_TYPE_PREFENCE
    order, so `--dsp mfcc` reliably gets the MFCC block even though mfe is
    preferred when no variant is given. learn="scratch" (default) wants the plain
    "keras" block (classifier_layers()); any TRANSFER_MODELS key wants the
    "keras-transfer-kws" block (transfer_layers()) - step 2.5c's A/B.
    """
    blocks = request(f"/{project_id}/impulse/blocks", api_key)
    dsp_types = {b["type"] for b in blocks.get("dspBlocks", [])}
    input_types = {b["type"] for b in blocks.get("inputBlocks", [])}
    learn_types = {b["type"] for b in blocks.get("learnBlocks", [])}
    print(f"  available input block types: {sorted(input_types)}")
    print(f"  available dsp block types: {sorted(dsp_types)}")
    print(f"  available learn block types: {sorted(learn_types)}")

    pref_order = (variant,) if variant in DSP_VARIANTS else DSP_TYPE_PREFERENCE
    dsp_type = next(
        (t for pref in pref_order for t in dsp_types if pref in t.lower()), None
    )
    if dsp_type is None:
        raise RuntimeError(f"none of {pref_order} found among dsp blocks {sorted(dsp_types)}")

    input_type = next((t for t in input_types if "time" in t.lower() or "series" in t.lower()), None)
    if input_type is None:
        raise RuntimeError(f"no time-series input block found among {sorted(input_types)}")

    wanted_learn_type = "keras" if learn == "scratch" else "keras-transfer-kws"
    learn_type = next((t for t in learn_types if t == wanted_learn_type), None)
    if learn_type is None:
        raise RuntimeError(f"no {wanted_learn_type!r} learn block found among {sorted(learn_types)}")

    print(f"  selected: input={input_type!r} dsp={dsp_type!r} learn={learn_type!r}")
    return input_type, dsp_type, learn_type


def build_impulse(project_id, api_key, input_type, dsp_type, learn_type, window_ms):
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
                "windowSizeMs": window_ms,
                "windowIncreaseMs": window_ms,  # one window per clip, no overlap
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
        f"  impulse created: {window_ms}ms window @ {SAMPLE_RATE_HZ}Hz -> {dsp_type} -> "
        f"{learn_type} classification"
    )
    return 2, 3


def configure_dsp(project_id, api_key, dsp_id, config):
    """Apply the variant's config overrides to the freshly built DSP block.

    Everything not named here keeps the block's own default (frame length 0.02 s,
    frame stride 0.01 s, local-normalization window 101, noise floor -52 dB).
    """
    request(
        f"/{project_id}/dsp/{dsp_id}",
        api_key,
        method="POST",
        body={"config": config},
    )
    print(f"  DSP block {dsp_id} config set: {config}")


def report_dsp_config(project_id, api_key, dsp_id):
    """Print the DSP block's actual live config - not asserted from documentation.

    No parameters are overridden here; this only makes the values Edge Impulse is
    really using visible, since none of the block's own defaults were changed.
    """
    try:
        cfg = request(f"/{project_id}/dsp/{dsp_id}", api_key)
    except RuntimeError as err:
        print(f"  DSP block {dsp_id} live config: unavailable ({err})")
        return
    items = cfg.get("config") if isinstance(cfg, dict) else None
    print(f"  DSP block {dsp_id} live config: {json.dumps(items) if items else cfg}")


def training_params(visual_layers, auto_class_weights=AUTO_CLASS_WEIGHTS):
    # TRAINING_CYCLES/LEARNING_RATE are shared across every --learn arm, including the
    # transfer-kws ones, deliberately - a controlled A/B holds cycles fixed rather than
    # each model's own recommended default, so a win is attributable to the
    # architecture, not to giving one arm more training time.
    return {
        "mode": "visual",
        "visualLayers": visual_layers,
        "trainingCycles": TRAINING_CYCLES,
        "learningRate": LEARNING_RATE,
        "batchSize": 32,
        # autoClassWeights OFF - measured both ways on the Phase 2c/2bc balanced set
        # (train=158-412 per class, XIAO folded in) and kept this one. Weights OFF:
        # elephant_call 63.3%, gunshot 55.8%, chainsaw 29.4% held-out recall, but
        # boar_call 2.6% / predator_call 3.6% (both below the 14.3% chance floor).
        # Weights ON: boar_call/predator_call recover to 18.4%/28.6% (above chance) but
        # elephant_call drops to 46.8%, gunshot to 45.3%, chainsaw to 25.5% - a real
        # precision/recall transfer, not a wash. elephant_call and gunshot are this
        # project's two highest-stakes classes (P3 alert+fusion core conflict-prevention
        # use case; P1 anti-poaching alert) while boar_call is fusion-only (feeds the
        # deterrence bandit, never a ranger alert) and predator_call is already below the
        # 150-clip floor and caveated as such regardless of this number. Trading ~17 and
        # ~10 recall points off the two highest-priority classes to lift a fusion-only
        # class and an already-asterisked one is the wrong trade for the deployed
        # product, even though macro-averaged-across-7-classes it looks more "balanced".
        # boar_call's 197-clip real yield (well under its 600 cap - not our bottleneck,
        # the source material's) is a genuine data-scarcity problem; the fix is more real
        # boar_call audio, not reweighting the loss on what little exists. (Historical
        # record: boar_call and predator_call were later dropped from the wire scheme
        # entirely after the full exploration never lifted either above chance - see the
        # module docstring. This decision predates that drop and is kept as the record of
        # why autoClassWeights is OFF even independent of it.)
        "autoClassWeights": auto_class_weights,
        # Spectrogram-domain augmentation - see AUGMENTATION_POLICY (currently off).
        "augmentationPolicySpectrogram": AUGMENTATION_POLICY,
        # Report the model's real argmax behaviour, not a 0.6-threshold-gated view.
        "minimumConfidenceRating": MIN_CONFIDENCE_RATING,
        # Profile the int8 model: CONTEXT.md's deployment target is an INT8 classifier.
        "profileInt8": True,
    }


def configure_training(project_id, api_key, learn_id, params):
    request(f"/{project_id}/training/keras/{learn_id}", api_key, method="POST", body=params)
    aug = params.get("augmentationPolicySpectrogram") or {}
    print(
        f"  training params set: {params['trainingCycles']} cycles, lr {params['learningRate']}, "
        f"batch {params.get('batchSize')}, "
        f"auto class weights {'on' if params.get('autoClassWeights') else 'off'}, "
        f"spectrogram augmentation {'on' if aug.get('enabled') else 'off'}, "
        f"min confidence {params.get('minimumConfidenceRating')}, int8 profiling on"
    )


def report_results(project_id, api_key, learn_id):
    """Print the real per-class numbers Edge Impulse returns - no derived figures.

    Classes drawn from many different recording contexts (Mendeley forest AudioMoth,
    ESC-50 field recordings, Freesound hobbyist uploads across a dozen queries, a
    GitHub elephant set) are reported separately, never averaged into one number -
    see the module docstring. Each per-class line is tagged with the manifest's
    floor_status so a class trained below the 150-clip floor is not read as a
    clean, well-supported per-species result.
    """
    try:
        with open(MANIFEST) as fh:
            floor_status = {
                label: meta.get("floor_status", "unknown")
                for label, meta in json.load(fh).get("classes", {}).items()
            }
    except FileNotFoundError:
        floor_status = {}

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
        status = floor_status.get(label, "unknown")
        print(f"    {label}: {good}/{total} correct ({rate})  [floor_status: {status}]")
    print(f"  confusion matrix: {json.dumps(accuracy.get('confusionMatrixValues'))}")
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--skip-impulse", action="store_true", help="reuse the existing impulse")
    ap.add_argument(
        "--clip-seconds",
        type=float,
        default=DEFAULT_CLIP_SECONDS,
        help="window size / increase in seconds (default 10.0, the window-sweep winner). "
        "Match the upload script's value.",
    )
    ap.add_argument(
        "--class-weights",
        action="store_true",
        help="override AUTO_CLASS_WEIGHTS default (off) to re-test EI's automatic class "
        "weighting against the current class roster - see the AUTO_CLASS_WEIGHTS comment.",
    )
    ap.add_argument(
        "--dsp",
        choices=sorted(DSP_VARIANTS),
        default="mfe",
        help="DSP block variant for the step-2.5a A/B (default mfe, the locked config; "
        "mfcc is the measured alternative - see DSP_VARIANTS).",
    )
    ap.add_argument(
        "--learn",
        choices=["scratch", *sorted(TRANSFER_MODELS)],
        default="scratch",
        help="Learn block for the step-2.5c A/B (default scratch, the locked from-scratch "
        "2-conv net; the rest are keras-transfer-kws pretrained backbones - see "
        "TRANSFER_MODELS).",
    )
    args = ap.parse_args()
    window_ms = int(args.clip_seconds * 1000)
    variant = DSP_VARIANTS[args.dsp]
    if args.learn != "scratch" and window_ms != TRANSFER_REQUIRED_WINDOW_MS:
        print(
            f"keras-transfer-kws only works with a {TRANSFER_REQUIRED_WINDOW_MS}ms window "
            f"(EI platform constraint, confirmed live - see TRANSFER_REQUIRED_WINDOW_MS); "
            f"got {window_ms}ms. Not attempting - this would waste a feature-generation job.",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    if not api_key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID environment variables first.", file=sys.stderr)
        sys.exit(1)

    check_data(project_id, api_key)

    print(f"\nBuilding impulse ({args.clip_seconds:g}s window)...")
    if args.skip_impulse:
        impulse = request(f"/{project_id}/impulse", api_key).get("impulse") or {}
        dsp_id = impulse["dspBlocks"][0]["id"]
        learn_id = impulse["learnBlocks"][0]["id"]
        print(f"  reusing impulse: dsp {dsp_id}, learn {learn_id}")
    else:
        input_type, dsp_type, learn_type = pick_dsp_type(project_id, api_key, args.dsp, args.learn)
        dsp_id, learn_id = build_impulse(
            project_id, api_key, input_type, dsp_type, learn_type, window_ms
        )
        dsp_config = dict(variant["config"])
        stride = frame_stride_for_window(window_ms)
        if stride != DEFAULT_FRAME_STRIDE_S:
            dsp_config["frame_stride"] = round(stride, 6)
            print(
                f"  frame_stride widened to {dsp_config['frame_stride']}s for the "
                f"{window_ms}ms window (locked 0.01s default would exceed Edge Impulse's "
                f"{MAX_DSP_FRAMES}-frame cap - see frame_stride_for_window)"
            )
        configure_dsp(project_id, api_key, dsp_id, dsp_config)
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
    visual_layers = (
        classifier_layers(variant["reshape_columns"])
        if args.learn == "scratch"
        else transfer_layers(args.learn)
    )
    print(f"  visual layers ({args.learn}): {json.dumps(visual_layers)}")
    params = training_params(visual_layers, auto_class_weights=args.class_weights)
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
