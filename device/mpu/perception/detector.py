"""Vision inference client for the on-device Edge Impulse detector.

perception/camera.py is capture-only (its own docstring: no pixel ->
log-odds model lives there) - this module is that model's client, not the
model itself. The trained artifact runs out-of-process, as a standing
`edge-impulse-linux-runner --run-http-server <port>` HTTP server
(services/config.py's VISION_INFERENCE_URL, docs/KNOWN_GAPS.md), not
embedded via the `edge_impulse_linux` Python SDK - confirmed 28 Aug on the
real board that neither pip nor ensurepip exists on its Python 3.13.5
image, and no sudo credential is available to install either. The runner
that IS already on the board is a Node-backed CLI (npm package
`edge-impulse-linux`, confirmed via `npm ls -g` - a different package from
the same-named Python SDK) that already loads the trained .eim artifact;
its `--run-http-server` flag turns that into a plain HTTP endpoint reachable
from stdlib `urllib.request` alone. Confirmed live 28 Aug against the real
board: `GET /api/info` returns model metadata (labels ["Boar", "Elephant"],
96x96x3 input, squash resize, deployed threshold min_score 0.05 - re-confirmed
3 Sept 2026 against the current champion no_attn_relu/medium deploy; was 0.5
when this docstring was first written, before the 30 Aug retrain), and
`POST /api/image` with a multipart JPEG correctly classified a held-out
Boar image at confidence 0.777 in ~20ms.

Deliberate departure from the stdlib-only script convention (matching
scripts/make_pseudo_ir_vision.py's own noted departure): JPEG-encoding a
BGR ndarray needs cv2, which perception/camera.py already makes an
unavoidable, function-local-only dependency of this codebase - no new
dependency is introduced here, just a second caller of the same one.
Everything downstream of that encode - the multipart body, the HTTP POST,
the JSON parse - is stdlib only (urllib.request, uuid, json); no `requests`,
no `edge_impulse_linux` SDK.

Production supervision of the runner process itself (start on boot, restart
on crash) is not this module's job and is not yet built - see
docs/KNOWN_GAPS.md. This module only ever calls an endpoint that is already
listening; if nothing is listening, detect() raises DetectionError and the
caller (services/reflex_loop.py) treats that exactly like a
perception.camera.CameraError - logged, and the VISION modality reported
unavailable to fuse(), never allowed to block or suppress actuation.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class DetectionError(RuntimeError):
    """Raised when a detect call cannot be completed end-to-end.

    Covers connection failure, timeout, a non-2xx HTTP status, and a
    response body that does not parse as the expected JSON shape - all
    treated identically by the caller (services/reflex_loop.py): logged,
    and the VISION modality reported unavailable to fuse(), the same
    "degrade loudly, never block" discipline perception.camera.CameraError
    already gets there.
    """


@dataclass(frozen=True)
class Detection:
    """One bounding box the model reported, in original-image pixel space.

    Attributes:
        label: One of the deployed model's classes ("Boar" or "Elephant"
            for ETX-V) - not validated against a fixed set here, so a
            future retrain with different classes needs no change to this
            module.
        confidence: The model's reported score for this box, in (0, 1].
            Edge Impulse only reports boxes that already clear the
            deployed threshold (min_score 0.05 for ETX-V, per its own
            /api/info, re-confirmed 3 Sept 2026) - a confidence below that never produces a
            Detection at all. See services/reflex_loop.py's
            _vision_check() for what "no Detection at all" means for
            the fused log-odds it feeds.
        x, y, width, height: Bounding box in the *original* uploaded
            image's pixel coordinates, not the model's internal 96x96
            input space - confirmed 28 Aug against a live 416x416 test
            image (the response's own "resized" field states the remap).
            Unused by fusion today; carried through for a future
            evidence-overlay or crop feature.
    """

    label: str
    confidence: float
    x: float
    y: float
    width: float
    height: float


class VisionDetectFn(Protocol):
    """Callable shape services/reflex_loop.py injects for one detection pass.

    Structural, not HttpVisionDetector itself, matching every other
    injected dependency in that module (CameraProtocol, DriveHornFn, ...) -
    a test fake needs no real HTTP server.
    """

    def __call__(self, images: list[Any]) -> list[list[Detection]]:
        """Run detection across a burst of already-captured frame images.

        Args:
            images: Frame.image ndarrays (BGR), typically a short burst
                from CameraProtocol.capture_burst().

        Returns:
            One list per input image, same length and order as `images` -
            per-frame attribution the caller needs to do its own per-label
            within-burst gate (services/reflex_loop.py's _vision_check(),
            which requires a majority-gated label - Boar, per
            services/config.py's VISION_SPECIES_BURST_MAJORITY_LABELS - to
            appear on more than half the burst's frames before it counts
            for anything; every other label, Elephant included, still only
            needs one frame). Until 3 Sept 2026 this returned every
            Detection flattened into one list with no frame boundary,
            which meant a single spurious box on one frame of a burst
            looked identical to the same box appearing on every frame -
            that OR-shaped aggregation measured a 43.64% Boar
            false-positive rate at the poll level in a real 2-hour board
            run, worse than the 31.53% raw-frame rate it started from
            (docs/qa/boar-gap-session-notes.md); this per-frame return is
            what makes the per-label gate possible. A single image that
            fails to encode/POST/parse contributes an empty list at its
            own index rather than being dropped, so the per-label frame
            count downstream stays accurate; DetectionError is raised only
            when every image in a non-empty burst failed, meaning nothing
            at all could be checked this event.
        """
        ...


class HttpVisionDetector:
    """Client for one edge-impulse-linux-runner --run-http-server endpoint.

    One instance per process is enough - it holds no per-call state beyond
    the base URL and timeout, and the runner is a standing local service
    (module docstring), not something this class starts or stops.
    """

    def __init__(self, base_url: str, timeout_s: float) -> None:
        """Store the endpoint and per-call timeout; performs no I/O itself.

        Args:
            base_url: e.g. "http://127.0.0.1:1337" - trailing slash is
                stripped if present. services/config.py's
                VISION_INFERENCE_URL is the real default; a test can point
                this at nothing and expect DetectionError.
            timeout_s: Per-image socket timeout. services/config.py's
                VISION_INFERENCE_TIMEOUT_S is the real default, bounded
                deliberately short - the same reasoning as
                services/config.py's own BRIDGE_CALL_TIMEOUT_S: this call
                sits between a seismic trigger and the alert decision, so a
                hung detector must not hang the whole event.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def __call__(self, images: list[Any]) -> list[list[Detection]]:
        """Implements VisionDetectFn - see that Protocol's own docstring."""
        per_frame: list[list[Detection]] = []
        failures = 0
        for image in images:
            try:
                per_frame.append(self._detect_one(image))
            except DetectionError as exc:
                failures += 1
                logger.warning("vision detect failed for one frame: %s", exc)
                per_frame.append([])
        if images and failures == len(images):
            raise DetectionError(
                f"all {len(images)} frame(s) in this burst failed detection"
            )
        return per_frame

    def _detect_one(self, image: Any) -> list[Detection]:
        # Function-local, matching perception/camera.py's own discipline -
        # this module stays importable with no OpenCV attached, only the
        # actual detect call needs it.
        import cv2

        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            raise DetectionError("cv2.imencode failed to produce a JPEG")

        # Hand-built multipart/form-data body - the deployed runner's own
        # documented usage is `curl -F 'file=@path-to-an-image.jpg'`
        # (confirmed 28 Aug against the live dashboard's own usage text),
        # and stdlib urllib has no multipart encoder of its own.
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="frame.jpg"\r\n'
            "Content-Type: image/jpeg\r\n\r\n"
        ).encode("ascii") + encoded.tobytes() + f"\r\n--{boundary}--\r\n".encode("ascii")

        request = urllib.request.Request(
            f"{self._base_url}/api/image",
            data=body,
            method="POST",
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise DetectionError(f"vision inference request failed: {exc}") from exc

        try:
            payload = json.loads(raw)
            boxes = payload["result"]["bounding_boxes"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise DetectionError(f"unexpected vision inference response shape: {exc}") from exc

        try:
            return [
                Detection(
                    label=box["label"],
                    confidence=float(box["value"]),
                    x=float(box["x"]),
                    y=float(box["y"]),
                    width=float(box["width"]),
                    height=float(box["height"]),
                )
                for box in boxes
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise DetectionError(f"unexpected bounding_boxes entry shape: {exc}") from exc
