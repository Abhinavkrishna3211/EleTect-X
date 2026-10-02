"""HTTP wrapper Edge Impulse calls to run this processing block.

The Studio does not import `dsp.py`; it POSTs windows to a block and reads the
features back, so every custom processing block ships one of these. The contract
is four endpoints:

  GET  /parameters  the block's UI definition, served straight from
                    parameters.json so the file stays the single source of truth
  POST /run         one window  -> features, graphs, output_config
  POST /batch       many windows -> a features row each, no graphs
  GET  /            a human-readable page, so hitting the URL in a browser while
                    debugging an ngrok tunnel says something useful

Run locally:  python dsp-server.py           (then `edge-impulse-blocks runner`)
In a container the Dockerfile's ENTRYPOINT does the same on $PORT.
"""

from __future__ import annotations

import json
import os
import traceback

import dsp
import numpy as np
from flask import Flask, request

app = Flask(__name__)

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "parameters.json"), encoding="utf-8") as fh:
    PARAMETERS = json.load(fh)

# The Studio sends every parameter as a string. `type` in parameters.json is the
# only record of what each one should become, so coerce from there rather than
# guessing per name - a silently-stringy `mel_bins` would reach librosa as
# "64" and fail deep inside the filterbank.
_CASTS = {"int": int, "float": float, "boolean": lambda v: str(v).lower() in ("true", "1", "yes")}
_TYPES = {
    item["param"]: item["type"]
    for group in PARAMETERS["parameters"]
    for item in group["items"]
}


def coerce(params: dict) -> dict:
    out = {}
    for key, value in params.items():
        cast = _CASTS.get(_TYPES.get(key, "string"))
        out[key] = cast(value) if cast else value
    return out


@app.errorhandler(Exception)
def on_error(exc):
    # Without this the Studio shows a bare 500 and the traceback stays in the
    # container log, which is the wrong place to look when a parameter is bad.
    traceback.print_exc()
    return json.dumps({"success": False, "error": str(exc)}), 200, {"Content-Type": "application/json"}


@app.route("/")
def home():
    info = PARAMETERS["info"]
    return f"<h1>{info['title']}</h1><p>{info['description']}</p>"


@app.route("/parameters")
def parameters():
    return app.response_class(
        json.dumps({**PARAMETERS, "success": True}), mimetype="application/json"
    )


def _require(args: dict, *keys: str) -> None:
    missing = [k for k in keys if k not in args]
    if missing:
        raise ValueError(f"missing from request body: {', '.join(missing)}")


@app.route("/run", methods=["POST"])
def run():
    args = request.get_json(force=True)
    _require(args, "features", "params", "sampling_freq")
    result = dsp.generate_features(
        args.get("implementation_version", 1),
        args.get("draw_graphs", False),
        args["features"],
        args.get("axes", ["audio"]),
        args["sampling_freq"],
        **coerce(args["params"]),
    )
    return app.response_class(json.dumps({**result, "success": True}), mimetype="application/json")


@app.route("/batch", methods=["POST"])
def batch():
    args = request.get_json(force=True)
    _require(args, "features", "params", "sampling_freq")
    params = coerce(args["params"])
    version = args.get("implementation_version", 1)
    axes = args.get("axes", ["audio"])

    rows, labels, config = [], None, None
    for window in np.asarray(args["features"], dtype=np.float32):
        result = dsp.generate_features(version, False, window, axes, args["sampling_freq"], **params)
        rows.append(result["features"])
        labels, config = result["labels"], result["output_config"]

    return app.response_class(
        json.dumps({"success": True, "features": rows, "labels": labels, "output_config": config}),
        mimetype="application/json",
    )


if __name__ == "__main__":
    # threaded=False: each request holds a whole spectrogram and the mel cache is
    # shared, and the Studio calls this serially anyway. Concurrency here buys
    # nothing and makes memory use unpredictable on a small block container.
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "4446")), threaded=False)
