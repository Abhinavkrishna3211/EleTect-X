"""Drive an EON Tuner architecture search against the ETX-V project.

Escalation step after the manually curated candidate sweep
(scripts/edge_impulse_train_vision.py --family {fomo,ssd,yolo-pro}) fell short of
the project's >=92%-recall-per-class bar. Where that script trains one named
architecture at a time, this one hands Edge Impulse's own Bayesian search a
bounded trial budget and a target device, and lets it explore the full
object-detection search space on its own.

Confirmed live against the real OpenAPI spec (studio.edgeimpulse.com/openapi.yml,
27 Aug): the 23 Aug finding that Tuner endpoints need an org-level key was wrong -
every /optimize/* path answers to the same project-scoped EI_API_KEY as
everything else. No prior session has actually launched a run; this is the
first.

Each TunerTrial's own metrics (KerasModelMetadataMetrics.report) already carry
real per-class precision/recall/F1 from a held-out split, computed by Edge
Impulse itself for every completed trial - not just the Tuner's own scalar
objective. Ranking here is done directly against that per-class recall, per the
plan's own rule: never trust a single blended objective as a stand-in for
"did we miss detections."

Usage:

    set EI_API_KEY=ei_...
    set EI_PROJECT_ID=1097972
    python scripts\\edge_impulse_tuner_vision.py --launch
    python scripts\\edge_impulse_tuner_vision.py --poll

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

# Resolved live from GET /{project}/deployment/targets (Phase 0 of the vision
# rebuild plan): "Arduino UNO Q" in the Studio device selector maps to
# latencyDevice identifier "arduino-unoq" - the same identifier the Tuner's own
# on-device performance profiling keys against. Not guessed from the display
# name; if this is wrong, updateConfig will come back success:false rather than
# silently profiling the wrong board.
TARGET_DEVICE_NAME = "arduino-unoq"
# Not hard real-time (a camera-trap firing on a multi-second cadence is fine) -
# loose enough not to prune real candidates, tight enough to keep the search off
# anything that would visibly lag a UNO Q. A stated choice, not inherited.
TARGET_LATENCY_MS = 300
# Bounded so a Bayesian search can't run past what's reasonable unattended
# overnight. 5 initial + 3 rounds x 3/round = 14, one under the cap - matches
# EI's own documented defaults (OptimizeConfig examples: initialTrials 5,
# optimizationRounds 3, trialsPerOptimizationRound 3) rather than inventing a
# bigger number with no evidence it converges faster.
TUNING_MAX_TRIALS = 15
INITIAL_TRIALS = 5
OPTIMIZATION_ROUNDS = 3
TRIALS_PER_ROUND = 3
# Safety cap, not a target - if the search is still running past this, report
# whatever's completed rather than let it run unbounded while unattended.
MAX_TOTAL_TRAINING_TIME_S = 4 * 3600
# Confirmed live (27 Aug) by actually POSTing this and reading back GET
# optimize/config's resolved `space` field: "object_detection_bounding_boxes"
# sounds broadest but resolves to a search space containing ONLY
# object_ssd_mobilenet_v2_fpnlite_320x320 - our weakest, OOM-prone candidate,
# not a broader net. "object_detection_yolo_pro" is the deliberate choice: the
# manual sweep already showed YOLO-Pro-nano attn_silu clearly ahead of both
# FOMO (0.751/0.495 recall) and SSD, so this spends the trial budget refining
# the architecture the evidence already favors. It requires the project's
# *current* impulse to reference a real YOLO-Pro learn block ("YOLO-Pro block
# not found" otherwise) - the orchestrator runs
# `edge_impulse_train_vision.py --family yolo-pro --configure-only` immediately
# before this to guarantee that.
SEARCH_SPACE_TEMPLATE = "object_detection_yolo_pro"
POLL_INTERVAL_S = 60


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
    if isinstance(result, dict) and result.get("success") is False:
        raise RuntimeError(f"{method} {path} -> {result.get('error', result)}")
    return result


def configure_tuner(project_id, api_key):
    config = {
        "targetDevice": {"name": TARGET_DEVICE_NAME},
        "targetLatency": TARGET_LATENCY_MS,
        "tuningMaxTrials": TUNING_MAX_TRIALS,
        "initialTrials": INITIAL_TRIALS,
        "optimizationRounds": OPTIMIZATION_ROUNDS,
        "trialsPerOptimizationRound": TRIALS_PER_ROUND,
        "tuningAlgorithm": "bayesian",
        "optimizationPrecision": "int8",
        "maxTotalTrainingTime": MAX_TOTAL_TRAINING_TIME_S,
        "searchSpaceTemplate": {"identifier": SEARCH_SPACE_TEMPLATE},
        # Both classes' held-out recall matter more than blended accuracy - see
        # the module docstring on why this script re-ranks by trial.report
        # instead of trusting this as the sole ranking signal regardless.
        "optimizationObjectives": [
            {"objective": "recall", "label": "recall", "weight": 1.0},
        ],
    }
    print(f"POST optimize/config: {json.dumps(config)}")
    try:
        request(f"/{project_id}/optimize/config", api_key, method="POST", body=config)
        print("  accepted")
    except RuntimeError as err:
        # "recall" is not confirmed as a valid optimizationObjective string (the
        # OpenAPI schema leaves it free-form) - if the API rejects it, fall back
        # to the field Edge Impulse's own UI default uses and re-rank ourselves
        # from each trial's real per-class report either way.
        print(f"  rejected with optimizationObjectives=[recall]: {err}")
        print("  retrying with default objective (accuracy) - ranking still done from trial.report")
        config.pop("optimizationObjectives")
        request(f"/{project_id}/optimize/config", api_key, method="POST", body=config)
        print("  accepted (default objective)")
    return config


def launch_tuner(project_id, api_key):
    result = request(f"/{project_id}/jobs/optimize", api_key, method="POST", body={})
    job_id = result.get("id")
    print(f"Tuner job launched: id {job_id}")
    return job_id


def get_state(project_id, api_key):
    return request(f"/{project_id}/optimize/state", api_key)


def _class_recall(report, label):
    """report is KerasModelMetadataMetrics.report - schema-documented only as
    'precision, recall, F1 and support scores', no fixed key shape guaranteed.
    Match case-insensitively against our two real class names rather than
    assume a specific casing/nesting Edge Impulse hasn't documented.
    """
    if not isinstance(report, dict):
        return None
    for key, value in report.items():
        if key.strip().lower() == label.lower() and isinstance(value, dict):
            recall = value.get("recall")
            if recall is not None:
                return float(recall)
    return None


def rank_trials(trials):
    """Rank completed trials by the worse of the two per-class recalls - a
    trial that aces Elephant but misses Boar is not what '>=92% on each class
    individually' asked for. Prefers int8 metrics (the actual deploy precision)
    and falls back to float32 only if int8 is missing.
    """
    ranked = []
    for trial in trials:
        if trial.get("status") != "completed":
            continue
        metrics = ((trial.get("metrics") or {}).get("test") or {})
        report = (metrics.get("int8") or {}).get("report") or (metrics.get("float32") or {}).get("report")
        if report is None:
            continue
        elephant_r = _class_recall(report, "Elephant")
        boar_r = _class_recall(report, "Boar")
        if elephant_r is None or boar_r is None:
            continue
        ranked.append(
            {
                "trial_id": trial.get("id"),
                "name": trial.get("name"),
                "elephant_recall": elephant_r,
                "boar_recall": boar_r,
                "worst_recall": min(elephant_r, boar_r),
                "impulse": trial.get("impulse"),
            }
        )
    ranked.sort(key=lambda r: r["worst_recall"], reverse=True)
    return ranked


def print_leaderboard(ranked):
    print("\n--- Tuner trial leaderboard (ranked by worse-of-two-classes recall) ---")
    if not ranked:
        print("  no completed trials with a readable per-class report yet")
        return
    for row in ranked:
        meets_bar = "MEETS >=92% BOTH" if row["worst_recall"] >= 0.92 else ""
        print(
            f"  {row['name'] or row['trial_id']}: Elephant R={row['elephant_recall']:.3f}, "
            f"Boar R={row['boar_recall']:.3f} {meets_bar}"
        )


def poll(project_id, api_key, out_path, max_wait_s=MAX_TOTAL_TRAINING_TIME_S + 1800):
    started = time.time()
    while time.time() - started < max_wait_s:
        state = get_state(project_id, api_key)
        status = state.get("status", {})
        running = state.get("tunerJobIsRunning")
        print(
            f"[{(time.time() - started) / 60:.1f} min] completed={status.get('numCompletedTrials')} "
            f"failed={status.get('numFailedTrials')} running={status.get('numRunningTrials')} "
            f"pending={status.get('numPendingTrials')} tunerJobIsRunning={running}"
        )
        ranked = rank_trials(state.get("trials", []))
        print_leaderboard(ranked)
        with open(out_path, "w") as f:
            json.dump({"state_status": status, "ranked": ranked}, f, indent=2)
        if not running:
            print("\nTuner run finished.")
            return ranked
        time.sleep(POLL_INTERVAL_S)
    print(f"\nGave up polling after {max_wait_s / 60:.0f} min - run may still be going in Studio.")
    return rank_trials(get_state(project_id, api_key).get("trials", []))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--launch", action="store_true", help="configure and start a new Tuner run")
    ap.add_argument("--poll", action="store_true", help="poll the current/most recent run to completion")
    ap.add_argument(
        "--out",
        default="tuner_results.json",
        help="where to write the ranked leaderboard as it updates (default: tuner_results.json)",
    )
    args = ap.parse_args()
    if not args.launch and not args.poll:
        print("pass --launch, --poll, or both", file=sys.stderr)
        sys.exit(1)

    api_key = os.environ.get("EI_API_KEY")
    project_id = os.environ.get("EI_PROJECT_ID")
    if not api_key or not project_id:
        print("Set EI_API_KEY and EI_PROJECT_ID environment variables first.", file=sys.stderr)
        sys.exit(1)

    if args.launch:
        configure_tuner(project_id, api_key)
        launch_tuner(project_id, api_key)

    if args.poll:
        ranked = poll(project_id, api_key, args.out)
        print(f"\nFinal leaderboard written to {args.out}")
        if ranked and ranked[0]["worst_recall"] >= 0.92:
            print(f"BAR MET: {ranked[0]['name'] or ranked[0]['trial_id']} clears >=92% recall on both classes.")
        elif ranked:
            print(
                f"Bar not met. Best trial worst-class recall: {ranked[0]['worst_recall']:.3f} "
                f"({ranked[0]['name'] or ranked[0]['trial_id']})."
            )


if __name__ == "__main__":
    main()
