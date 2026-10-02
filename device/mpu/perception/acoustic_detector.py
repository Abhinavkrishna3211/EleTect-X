"""Acoustic inference client for the on-device Edge Impulse classifier.

perception/microphone.py is capture-only - this module is the trained
model's client, not the model itself, exactly the split
perception/detector.py keeps against perception/camera.py on the vision
side. The artifact runs out-of-process as a standing
`edge-impulse-linux-runner --run-http-server <port>` and is driven over
plain HTTP with stdlib `urllib`, for the reason perception/detector.py
documents at length: the board's Python 3.13.5 image has no pip, no
ensurepip and no sudo, so the `edge_impulse_linux` Python SDK cannot be
installed and will not become installable. The Node-backed runner is
already on the box and already loads .eim artifacts.

The wire contract, read off the runner's own source rather than inferred
(edge-impulse-linux-cli, cli/linux/runner-utils.ts, startApiServer):

    GET  /api/info      -> {"project": {...}, "modelParameters": {...}}
    POST /api/features  <- {"features": [<numbers>]}
                        -> {"result": {"classification": {label: score}}}

Two properties of that endpoint drive this module's whole design:

- **The feature count is checked exactly.** runner-utils.ts rejects with a
  400 when `body.features.length !== input_features_count`. There is no
  padding and no truncation on the server side. So the window this client
  sends has to be the length the deployed impulse declares, and the only
  safe way to know that is to ask - hence model_info() and the derived
  `window_s`, rather than a duration constant that would silently start
  400ing the day the impulse window changes.
- **For a non-camera impulse the features are the raw signal**, not the
  DSP output. The runner executes the full impulse, log-mel front end
  included. So this client sends PCM sample values and never computes a
  spectrogram - which matters, because the front end is a custom DSP block
  (ml/acoustic/ei_blocks/dsp-panns-logmel) and reimplementing it here in
  Python would be a second, drifting copy of something that already has
  exactly one authoritative implementation.

Sample scale: raw int16 values are sent as-is, not normalised to +/-1.
dsp.py's own front end scales on evidence (`if max(abs(y)) > 1.0: y /=
32768`), which is how Edge Impulse stores and feeds audio throughout, so
int16-range integers are what the deployed block expects to receive.

Latency is not incidental here. Studio's own performance estimate for this
impulse on the QRB2210, float32 unoptimised, is **4,134 ms for the
classifier block alone**, with the custom DSP block unestimated (Studio
cannot profile a custom block, so it shows a blank) - meaning the real
per-window cost is over four seconds plus the front end. That is roughly
thirty times a vision frame's 138 ms, and it is why
services/config.py's ACOUSTIC_INFERENCE_TIMEOUT_S is sized in tens of
seconds rather than the 2.0 s vision gets, and why the caller must not
run this inside the vision watch loop.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from bridge.rpc import AcousticClass
from perception.microphone import AudioClip

logger = logging.getLogger(__name__)


class AcousticDetectionError(RuntimeError):
    """Raised when a classify call cannot be completed end-to-end.

    Covers connection failure, timeout, a non-2xx status (including the
    runner's own 400 for a feature-count mismatch), and a response body
    that does not parse as the expected shape. All are treated identically
    by the caller: logged, and the ACOUSTIC modality reported unavailable
    to fuse() - the same "degrade loudly, never block" discipline
    perception.detector.DetectionError and perception.camera.CameraError
    already get in services/reflex_loop.py.
    """


@dataclass(frozen=True)
class AcousticModelInfo:
    """What the deployed .eim says about itself.

    Fetched once and cached - the runner is a standing process serving one
    fixed artifact, so this cannot change underneath us without the runner
    restarting, and re-fetching it before every classify would add a round
    trip to a path that is already the slowest thing in the system.

    Attributes:
        labels: The classes the deployed model can emit, in the order the
            model reports them. Validated against AcousticClass by
            `unknown_labels` rather than assumed to match - a retrain that
            adds or renames a class must be caught loudly here, not
            silently routed as ambient downstream.
        frequency: Sample rate in Hz the impulse was built for. Must match
            what perception/microphone.py captures at; mismatch_reason()
            is what checks it.
        input_features_count: Exact number of values POST /api/features
            demands. Not negotiable server-side.
        axis_count: 1 for the mono audio impulse. Carried because
            window_s's arithmetic needs it and a future multi-axis model
            would otherwise compute a silently wrong window.
    """

    labels: list[str]
    frequency: float
    input_features_count: int
    axis_count: int

    @property
    def window_s(self) -> float:
        """Seconds of audio one inference window covers.

        The same arithmetic the runner prints at startup
        (runner-utils.ts: input_features_count / frequency / axis_count).
        """
        divisor = self.frequency * self.axis_count
        if divisor <= 0:
            return 0.0
        return self.input_features_count / divisor

    @property
    def unknown_labels(self) -> list[str]:
        """Deployed labels that no AcousticClass member covers.

        Non-empty means the deployed artifact and bridge/rpc.py's enum have
        diverged. bridge/rpc.py's own docstring records why that matters:
        enum members nothing can emit were carried for weeks while
        reflex_loop routed them as elephant evidence - dead branches that
        read like working detection. The inverse (a label the enum does not
        know) is worse, because it reaches the router as an unroutable
        string.
        """
        known = {member.value for member in AcousticClass}
        return [label for label in self.labels if label not in known]

    def mismatch_reason(self, clip: AudioClip) -> str | None:
        """Why `clip` cannot be sent to this model, or None if it can.

        Checked before the POST rather than left to the runner's 400, so
        the log line names the actual physical problem (a capture rate that
        does not match the impulse) instead of a feature-count arithmetic
        error two layers removed from its cause.
        """
        if abs(clip.sample_rate - self.frequency) > 0.5:
            return (
                f"clip captured at {clip.sample_rate} Hz but the deployed "
                f"impulse expects {self.frequency:g} Hz - nothing on-device "
                "resamples (librosa is not installable on the board), so this "
                "would be classified as the wrong pitch and tempo"
            )
        if len(clip.samples) < self.input_features_count:
            return (
                f"clip is {len(clip.samples)} samples, shorter than the "
                f"{self.input_features_count}-sample window the impulse "
                f"requires ({self.window_s:.2f}s)"
            )
        return None


@dataclass(frozen=True)
class AcousticClassification:
    """One inference window's result.

    Attributes:
        label: Highest-scoring class name as the model reported it.
        confidence: That class's score, 0-1.
        scores: Every class the runner returned, label -> score. The runner
            filters out anything below the .eim's baked-in min_score
            before responding, so an absent label means "below threshold",
            not "scored zero".
        offset_samples: Where in the source clip this window started. Kept
            so bench tooling can point at the exact audio a detection came
            from, and so a caller can order windows without re-deriving it.
    """

    label: str
    confidence: float
    scores: dict[str, float]
    offset_samples: int

    def to_acoustic_class(self) -> AcousticClass | None:
        """Map `label` onto the wire enum, or None if it is not a member.

        None is returned rather than raising, and rather than defaulting to
        AMBIENT, because the two failure modes need different handling: an
        unroutable label is a deploy/enum divergence the operator has to
        fix, whereas ambient is a real, common, benign result. Quietly
        collapsing the former into the latter would hide a broken deploy
        behind a plausible-looking quiet forest.
        """
        try:
            return AcousticClass(self.label)
        except ValueError:
            return None


@dataclass(frozen=True)
class AcousticResult:
    """Every window classified from one clip, plus the one that matters.

    Attributes:
        windows: Per-window results in time order. More than one because a
            capture is deliberately longer than the impulse window - see
            HttpAcousticClassifier.__call__ for why.
        selected: The window this clip should be judged on. See
            _select() for the rule; None only when `windows` is empty,
            which __call__ never returns (it raises instead).
    """

    windows: list[AcousticClassification]
    selected: AcousticClassification | None


class AcousticClassifyFn(Protocol):
    """Callable shape services/reflex_loop.py injects for one classify pass.

    Structural rather than HttpAcousticClassifier itself, matching every
    other injected dependency in that module (VisionDetectFn,
    CameraProtocol, DriveHornFn) - a test fake needs no HTTP server and no
    .eim.
    """

    def __call__(self, clip: AudioClip) -> AcousticResult:
        """Classify every window of `clip` and pick one.

        Raises:
            AcousticDetectionError: when no window could be classified at
                all, meaning nothing about this clip could be established.
        """
        ...


# Anything in this set is a positive acoustic event; everything else is the
# background class. Derived from AcousticClass rather than written out, so
# adding a class to the wire enum cannot leave a stale literal here.
_NON_AMBIENT = frozenset(
    member.value for member in AcousticClass if member is not AcousticClass.AMBIENT
)


def _select(windows: list[AcousticClassification]) -> AcousticClassification | None:
    """Pick the window a clip should be judged on.

    Rule: the highest-confidence non-ambient window if any window is
    non-ambient, otherwise the highest-confidence ambient window.

    This is max-pooling over time, and it is the right shape for what is
    being detected. A gunshot is roughly 200 ms inside a window of several
    seconds; averaging its window against the silent ones either side would
    dilute exactly the evidence the system exists to catch. The cost is the
    matching asymmetry - a single spurious window carries the whole clip -
    and that cost is paid deliberately here rather than hidden: the vision
    path learned the same lesson the expensive way (an OR-shaped
    aggregation across a burst measured a 43.64% Boar false-positive rate
    at poll level, docs/qa/boar-gap-session-notes.md) and answered it with a
    majority gate. Acoustic cannot use a majority gate for the same purpose,
    because a transient genuinely does only appear in one window. What
    guards it instead is downstream: services/reflex_loop.py's
    handle_acoustic_event routes elephant_call/chainsaw into fuse() as
    corroborating evidence that cannot alert on its own, and confidence
    survives into the log-odds rather than being flattened to a boolean.
    Gunshot is the exception that does alert alone, by ADR 0007 5, which is
    a deliberate anti-poaching tradeoff of false alarms against misses.
    """
    if not windows:
        return None
    non_ambient = [w for w in windows if w.label in _NON_AMBIENT]
    pool = non_ambient or windows
    return max(pool, key=lambda w: w.confidence)


class HttpAcousticClassifier:
    """Client for one edge-impulse-linux-runner --run-http-server endpoint.

    One instance per process. Holds the base URL, the timeout, and the
    cached model info; the runner itself is a standing local service this
    class neither starts nor supervises (that gap is tracked in
    docs/KNOWN_GAPS.md alongside the identical one for vision).
    """

    def __init__(
        self,
        base_url: str,
        timeout_s: float,
        *,
        window_hop_fraction: float = 0.5,
        max_windows: int = 4,
    ) -> None:
        """Store the endpoint and windowing policy; performs no I/O.

        Args:
            base_url: e.g. "http://127.0.0.1:1338" - trailing slash
                stripped. services/config.py's ACOUSTIC_INFERENCE_URL is
                the real default. It must be a *different port* from the
                vision runner: one runner process serves exactly one .eim,
                so the two models are two processes.
            timeout_s: Per-window socket timeout. Sized in tens of seconds,
                not the 2.0 s vision uses - see the module docstring's
                latency note.
            window_hop_fraction: Hop between consecutive windows as a
                fraction of the window length. 0.5 means 50% overlap, so a
                transient falling on a window boundary still lands whole
                inside the neighbouring window. 1.0 gives contiguous
                non-overlapping windows.
            max_windows: Hard ceiling on windows per clip. At four-plus
                seconds of inference each, an unbounded window count over a
                long clip would block the caller for minutes. Windows past
                the cap are dropped from the *end* of the clip, so the
                earliest audio - closest to whatever triggered the capture
                - is always the audio that gets classified.
        """
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._window_hop_fraction = window_hop_fraction
        self._max_windows = max_windows
        self._model_info: AcousticModelInfo | None = None

    def model_info(self) -> AcousticModelInfo:
        """Fetch and cache the deployed model's parameters.

        Raises:
            AcousticDetectionError: if the runner is unreachable or returns
                something that is not the documented shape.
        """
        if self._model_info is not None:
            return self._model_info

        request = urllib.request.Request(f"{self._base_url}/api/info", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AcousticDetectionError(
                f"could not reach the acoustic runner at {self._base_url}: {exc}"
            ) from exc

        try:
            payload = json.loads(raw)
            params = payload["modelParameters"]
            info = AcousticModelInfo(
                labels=list(params["labels"]),
                frequency=float(params["frequency"]),
                input_features_count=int(params["input_features_count"]),
                axis_count=int(params.get("axis_count", 1)),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AcousticDetectionError(
                f"unexpected /api/info response shape: {exc}"
            ) from exc

        if info.input_features_count <= 0:
            raise AcousticDetectionError(
                f"deployed model reports input_features_count="
                f"{info.input_features_count}, which cannot be windowed"
            )

        unknown = info.unknown_labels
        if unknown:
            # Loud, and not fatal: an extra class the enum does not know
            # will be dropped by to_acoustic_class() at routing time, so
            # the system degrades to "cannot route that" rather than
            # misrouting. Refusing to start would take the whole acoustic
            # modality down over a label rename.
            logger.error(
                "deployed acoustic model emits label(s) %s that bridge/rpc.py's "
                "AcousticClass does not define - those detections cannot be "
                "routed and will be discarded; reconcile the enum with the "
                "deployed impulse",
                unknown,
            )

        logger.info(
            "acoustic model: labels=%s freq=%gHz window=%.2fs (%d features)",
            info.labels,
            info.frequency,
            info.window_s,
            info.input_features_count,
        )
        self._model_info = info
        return info

    def required_capture_s(self, *, windows: int = 2) -> float:
        """How long a capture should be to yield `windows` inference windows.

        main.py uses this to size perception/microphone.py's capture
        instead of carrying a duration constant that could drift out of
        agreement with the deployed impulse. Asking the model is the only
        way to be right about this across a retrain.
        """
        info = self.model_info()
        if windows <= 1:
            return info.window_s
        hop = info.window_s * self._window_hop_fraction
        return info.window_s + hop * (windows - 1)

    def __call__(self, clip: AudioClip) -> AcousticResult:
        """Implements AcousticClassifyFn - see that Protocol's docstring."""
        info = self.model_info()

        reason = info.mismatch_reason(clip)
        if reason is not None:
            raise AcousticDetectionError(reason)

        offsets = self._window_offsets(len(clip.samples), info.input_features_count)
        windows: list[AcousticClassification] = []
        failures = 0
        for offset in offsets:
            try:
                windows.append(self._classify_window(clip, offset, info))
            except AcousticDetectionError as exc:
                failures += 1
                logger.warning(
                    "acoustic classify failed for window at sample %d: %s",
                    offset,
                    exc,
                )
        if failures and not windows:
            raise AcousticDetectionError(
                f"all {failures} window(s) of this clip failed classification"
            )

        selected = _select(windows)
        if selected is not None:
            logger.info(
                "acoustic clip: %d/%d window(s) classified, selected %s at %.3f "
                "(offset %d samples, %.2fs)",
                len(windows),
                len(offsets),
                selected.label,
                selected.confidence,
                selected.offset_samples,
                selected.offset_samples / float(clip.sample_rate or 1),
            )
        return AcousticResult(windows=windows, selected=selected)

    def _window_offsets(self, total_samples: int, window_samples: int) -> list[int]:
        """Start offsets for every window that fits inside the clip.

        A clip shorter than one window never reaches here - mismatch_reason
        rejects it first - so this always returns at least [0].
        """
        hop = max(1, int(window_samples * self._window_hop_fraction))
        offsets: list[int] = []
        offset = 0
        while offset + window_samples <= total_samples:
            offsets.append(offset)
            if len(offsets) >= self._max_windows:
                break
            offset += hop
        return offsets or [0]

    def _classify_window(
        self,
        clip: AudioClip,
        offset: int,
        info: AcousticModelInfo,
    ) -> AcousticClassification:
        """POST one window to /api/features and parse the classification."""
        window = clip.samples[offset : offset + info.input_features_count]
        if len(window) != info.input_features_count:
            # Defensive: _window_offsets should make this unreachable. The
            # runner would answer with a 400 whose message is about counts,
            # not about the slicing bug that caused it.
            raise AcousticDetectionError(
                f"window at offset {offset} is {len(window)} samples, expected "
                f"{info.input_features_count}"
            )

        # Raw int16 sample values, not normalised - see the module
        # docstring. tolist() gives plain Python ints, which json can
        # serialise; array.array cannot be serialised directly.
        body = json.dumps({"features": window.tolist()}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/api/features",
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            # The runner returns its validation failures as text/plain with
            # a useful message ("Expected N features, but received M"), and
            # losing that to a bare status code would make a window-size
            # bug much harder to find than it needs to be.
            detail = exc.read().decode("utf-8", "replace").strip()
            raise AcousticDetectionError(
                f"acoustic inference returned HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AcousticDetectionError(
                f"acoustic inference request failed: {exc}"
            ) from exc

        try:
            payload: Any = json.loads(raw)
            scores_raw = payload["result"]["classification"]
            scores = {str(k): float(v) for k, v in scores_raw.items()}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise AcousticDetectionError(
                f"unexpected /api/features response shape: {exc}"
            ) from exc

        if not scores:
            # The runner strips every class below the .eim's baked-in
            # min_score before responding, so an empty map is a real
            # outcome: nothing cleared threshold. Ambient at zero
            # confidence is the honest representation - it keeps the
            # window in the result set (so the caller can see it was
            # classified) without inventing evidence for any class.
            return AcousticClassification(
                label=AcousticClass.AMBIENT.value,
                confidence=0.0,
                scores={},
                offset_samples=offset,
            )

        label, confidence = max(scores.items(), key=lambda kv: kv[1])
        return AcousticClassification(
            label=label,
            confidence=confidence,
            scores=scores,
            offset_samples=offset,
        )
