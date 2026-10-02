"""Disposable microphone bench check: is the BY-M1 alive, and where is the floor?

Not an App Lab app - needs no Bridge, no app.yaml, nothing schema-shaped
(same discipline as bench/ping and bench/camera_check/capture_check.py,
ENGINEERING_CONVENTIONS.md 1). It drives the real
perception.microphone.Microphone rather than reimplementing capture, so
what it measures is exactly what the reflex path will measure.

This script exists because three constants in services/config.py -
ACOUSTIC_MIN_RMS, ACOUSTIC_MAX_CLIPPED_FRACTION and
ACOUSTIC_MAX_DC_OFFSET - are currently INVENTED, and ACOUSTIC_ENABLED is
False until they are not. `calibrate` is the subcommand that replaces
them with measured numbers.

Why a calibration step is needed at all
---------------------------------------
The field microphone is a BOYA BY-M1: an electret lavalier powered by one
LR44 cell. Its failure mode is the dangerous kind. A dead cell does not
unplug the USB adapter, does not stop the card enumerating and does not
stop frames arriving - it just makes them near-silent. Near-silence
classifies as confident `ambient`, which is indistinguishable from a
quiet forest. So the system has to know, numerically, what "this
microphone is not working" looks like on this specific hardware, and the
only way to know that is to measure it switched on and switched off.

Subcommands
-----------
  devices    List capture cards and show which one discovery picks.
  levels     Capture once and print RMS / peak / clipped / DC offset.
  calibrate  Capture with the mic on, then off, and recommend a floor.
  classify   Capture once and send it to the standing runner end to end.

Runs on the board over SSH (needs alsa-utils for arecord; no pip, no
sudo, stdlib only - `wave` and `array` are both stdlib, which is why WAV
is the save format rather than anything that would need soundfile).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import wave
from pathlib import Path

# Puts device/mpu on sys.path so `from perception.microphone import ...`
# resolves the same way it does under pytest (pyproject.toml's
# pythonpath = ["."]), whether this runs in place or is copied to a board
# folder mirroring this tree.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from perception.microphone import (  # noqa: E402
    AudioClip,
    Microphone,
    MicrophoneError,
    assess_health,
    discover_capture_device,
)
from services import config  # noqa: E402

_DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "output"

# Floor below which dBFS is reported as -inf rather than a huge negative
# number. 1e-9 is roughly -180 dBFS, far below a 16-bit LSB, so anything
# under it is exactly zero in practice.
_DBFS_FLOOR = 1e-9


def _dbfs(value: float) -> str:
    """Format a normalised 0-1 level as dBFS, which is how levels read.

    Audio levels span several orders of magnitude and the interesting
    comparison here - a live microphone against a dead one - is a ratio,
    not a difference. 0.0003 and 0.03 look adjacent in decimal and are 40
    dB apart.

    Args:
        value: A normalised amplitude, 0-1 relative to full scale.

    Returns:
        A short display string such as "-70.5 dBFS", or "-inf dBFS".
    """
    if value <= _DBFS_FLOOR:
        return "  -inf dBFS"
    return f"{20 * math.log10(value):6.1f} dBFS"


def _print_clip(clip: AudioClip, *, label: str = "") -> None:
    """Print the four statistics the config floors are set from.

    Deliberately prints all four every time, including the ones that
    passed, because the numbers are only useful relative to each other -
    a DC offset inflates RMS, so an RMS reading is not interpretable
    without the offset beside it.

    Args:
        clip: The captured audio to describe.
        label: Optional prefix, used by `calibrate` to tag on/off runs.
    """
    head = f"{label} " if label else ""
    print(f"  {head}device            {clip.device}")
    print(f"  {head}duration          {clip.duration_s:.2f} s "
          f"({len(clip.samples)} samples @ {clip.sample_rate} Hz)")
    print(f"  {head}RMS               {clip.rms:.6f}   {_dbfs(clip.rms)}")
    print(f"  {head}peak              {clip.peak:.6f}   {_dbfs(clip.peak)}")
    print(f"  {head}clipped fraction  {clip.clipped_fraction:.6f}  "
          f"({round(clip.clipped_fraction * len(clip.samples))} samples at full scale)")
    print(f"  {head}DC offset         {clip.dc_offset:.6f}   {_dbfs(clip.dc_offset)}")


def _print_segments(clip: AudioClip, *, seconds: float = 0.5) -> None:
    """Print per-segment RMS so a level can be watched changing over time.

    A single whole-clip RMS cannot distinguish a microphone that works
    from one that worked for the first second and then dropped out, and
    it averages away the tap-test that is the quickest way to confirm a
    live capture by hand.

    Args:
        clip: The captured audio.
        seconds: Segment length. Half a second is short enough to see a
            hand clap and long enough to be a stable RMS.
    """
    width = max(1, int(clip.sample_rate * seconds))
    samples = clip.samples
    print(f"  per-{seconds:g}s RMS:")
    for start in range(0, len(samples) - width + 1, width):
        chunk = samples[start : start + width]
        rms = math.sqrt(sum(float(s) * s for s in chunk) / len(chunk)) / 32768.0
        # A 40-character bar spanning -80 dBFS to 0 dBFS. Visual only -
        # the number beside it is the measurement.
        db = 20 * math.log10(rms) if rms > _DBFS_FLOOR else -99.0
        bars = max(0, min(40, int((db + 80) / 2)))
        print(f"    t={start / clip.sample_rate:5.1f}s  {rms:.6f}  "
              f"{_dbfs(rms)}  {'#' * bars}")


def _save_wav(clip: AudioClip, path: Path) -> None:
    """Write the clip as a 16-bit mono WAV so a human can listen to it.

    Listening is not a redundant check. Every statistic here is
    level-based and a level cannot tell mains hum, a loose connector or
    the adapter's own noise floor apart from real ambience - all of which
    read as "some signal is present".

    Args:
        clip: The captured audio.
        path: Destination file; parent directories are created.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(clip.sample_rate)
        out.writeframes(clip.to_bytes())
    print(f"  saved             {path}")


def _report_health(clip: AudioClip) -> bool:
    """Run the production health gate and explain the verdict.

    Uses services.config's live values rather than arguments, because the
    question this answers is "would the real reflex path accept this
    clip", not "would some hypothetical threshold accept it".

    Args:
        clip: The captured audio.

    Returns:
        True if the clip would be classified, False if it would be
        reported as ACOUSTIC unavailable.
    """
    health = assess_health(
        clip,
        min_rms=config.ACOUSTIC_MIN_RMS,
        max_clipped_fraction=config.ACOUSTIC_MAX_CLIPPED_FRACTION,
        max_dc_offset=config.ACOUSTIC_MAX_DC_OFFSET,
    )
    print()
    print("  against the CURRENT config floors "
          f"(min_rms={config.ACOUSTIC_MIN_RMS}, "
          f"max_clipped={config.ACOUSTIC_MAX_CLIPPED_FRACTION}, "
          f"max_dc={config.ACOUSTIC_MAX_DC_OFFSET}):")
    if health.ok:
        print("    PASS - this clip would be classified")
    else:
        print(f"    FAIL - {health.reason}")
        print("    (reported to fuse() as ACOUSTIC unavailable, never classified)")
    return health.ok


def _resolve_device(requested: str | None) -> str:
    """Pick the ALSA device string, preferring discovery over a constant.

    Args:
        requested: An explicit --device, or None to discover.

    Returns:
        An ALSA device string such as "plughw:1,0".

    Raises:
        MicrophoneError: If discovery finds no USB capture device.
    """
    if requested:
        return requested
    if config.ACOUSTIC_CAPTURE_DEVICE:
        return config.ACOUSTIC_CAPTURE_DEVICE
    return discover_capture_device()


def _capture(args: argparse.Namespace) -> AudioClip:
    """Open a Microphone at the impulse's rate and record one clip.

    Args:
        args: Parsed CLI arguments; uses .device, .rate and .seconds.

    Returns:
        The captured clip.
    """
    device = _resolve_device(args.device)
    mic = Microphone(device, sample_rate=args.rate)
    print(f"recording {args.seconds:.1f}s from {device} at {args.rate} Hz ...")
    return mic.capture(args.seconds)


# --------------------------------------------------------------------------
# Subcommands
# --------------------------------------------------------------------------


def cmd_devices(args: argparse.Namespace) -> int:
    """List capture hardware and show which device discovery would choose.

    Worth its own subcommand because a wrong card is the failure that
    looks most like a dead microphone: an on-die codec with nothing
    attached records perfectly well-formed silence.

    Args:
        args: Parsed CLI arguments (unused).

    Returns:
        A process exit code.
    """
    del args
    import subprocess

    try:
        listing = subprocess.run(
            ["arecord", "-l"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"could not run arecord -l: {exc}", file=sys.stderr)
        return 1

    print(listing.stdout.decode("utf-8", "replace").strip() or "(no output)")
    print()
    try:
        print(f"discovery would use: {discover_capture_device()}")
    except MicrophoneError as exc:
        print(f"discovery failed: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_levels(args: argparse.Namespace) -> int:
    """Capture once and print every statistic the health gate uses.

    Args:
        args: Parsed CLI arguments.

    Returns:
        A process exit code; 1 if the clip would fail the current floors,
        so this is usable as a scripted go/no-go before a field run.
    """
    try:
        clip = _capture(args)
    except MicrophoneError as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1

    print()
    _print_clip(clip)
    if args.segments:
        print()
        _print_segments(clip)
    if args.save:
        print()
        _save_wav(clip, Path(args.save))
    return 0 if _report_health(clip) else 1


def cmd_calibrate(args: argparse.Namespace) -> int:
    """Measure the mic switched on, then off, and recommend a floor.

    This is the subcommand services/config.py's comments refer to. The
    recommendation is the geometric mean of the two RMS readings - the
    midpoint on a log scale, which is the right midpoint for a quantity
    measured in dB - so the floor sits equally far from "working" and
    "dead" in the units the difference actually lives in.

    It refuses to recommend anything when the two readings are within 12
    dB of each other. That is not an arbitrary cutoff: below roughly that
    separation there is no threshold that reliably distinguishes the two
    states, and a number printed anyway would look like a measurement
    while being a coin toss on a deployment real forest officers depend
    on. The likely causes are a mic left switched on for the "off" run, a
    capture gain high enough that the adapter's own noise floor dominates,
    or the wrong card.

    Args:
        args: Parsed CLI arguments.

    Returns:
        A process exit code; 1 if separation was insufficient.
    """
    print("This measures the microphone working, then not working.")
    print("Both runs must be in the SAME acoustic environment - do not")
    print("move the mic, and keep the room as quiet for one as the other.")
    print()

    try:
        input(f"1/2  Switch the BY-M1 ON (fresh LR44). Press Enter to record "
              f"{args.seconds:.0f}s ...")
        on = _capture(args)
        print()
        _print_clip(on, label="ON ")

        print()
        input("2/2  Switch the BY-M1 OFF, leaving it plugged in. Press Enter ...")
        off = _capture(args)
        print()
        _print_clip(off, label="OFF")
    except MicrophoneError as exc:
        print(f"\ncapture failed: {exc}", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("\naborted", file=sys.stderr)
        return 1

    if args.save_dir:
        print()
        _save_wav(on, Path(args.save_dir) / "mic_on.wav")
        _save_wav(off, Path(args.save_dir) / "mic_off.wav")

    print()
    print("-" * 68)
    if off.rms <= _DBFS_FLOOR:
        separation_db = float("inf")
    else:
        separation_db = 20 * math.log10(on.rms / off.rms) if on.rms > 0 else 0.0
    print(f"  separation        {separation_db:.1f} dB "
          f"(ON {_dbfs(on.rms).strip()} vs OFF {_dbfs(off.rms).strip()})")

    if separation_db < 12.0:
        print()
        print("  INSUFFICIENT SEPARATION - no floor recommended.")
        print("  There is no threshold that tells these two states apart.")
        print("  Check: was the mic really switched off? Is the adapter's")
        print("  capture gain so high that its own noise floor dominates?")
        print("  Is this the USB card and not the on-die codec?")
        print(f"  (run `{Path(__file__).name} devices` to confirm the card)")
        return 1

    if off.rms <= _DBFS_FLOOR:
        # A digitally silent OFF run - the adapter muted the input rather
        # than passing its own noise floor. The geometric mean is zero
        # here, and a floor of zero rejects nothing, which is the exact
        # inverse of what this calibration is for. Fall back to a fixed
        # 30 dB below the working level: far enough under a live mic to
        # clear a quiet night, far enough above digital silence to still
        # catch a dead cell.
        recommended = on.rms * 10 ** (-30 / 20)
        basis = "30 dB below the ON reading (OFF was digitally silent)"
    else:
        recommended = math.sqrt(on.rms * off.rms)
        basis = "geometric mean of the ON and OFF readings"
    print()
    print(f"  basis             {basis}")
    print("  Recommended services/config.py value:")
    print(f"      ACOUSTIC_MIN_RMS = {recommended:.6f}    # {_dbfs(recommended).strip()}")
    print()
    print("  Also replace the INVENTED markers on these, measured above:")
    print(f"      ACOUSTIC_MAX_CLIPPED_FRACTION  - ON run measured "
          f"{on.clipped_fraction:.6f}")
    print(f"      ACOUSTIC_MAX_DC_OFFSET         - ON run measured "
          f"{on.dc_offset:.6f}")
    print()
    print("  Caveat worth carrying into the commit message: one quiet indoor")
    print("  pair is not a forest. The ON reading here is a room, and a real")
    print("  night in Kothamangalam may sit closer to the OFF reading than")
    print("  this pair suggests. Re-run on site before ACOUSTIC_ENABLED goes")
    print("  True for a deployment.")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    """Capture once and push it through the standing runner, end to end.

    Proves the whole chain in one command - arecord, the health gate, the
    HTTP contract, the deployed labels - which is the only way to catch
    the mismatches that no unit test can see, such as a deployed impulse
    whose window no longer matches what capture produces.

    Args:
        args: Parsed CLI arguments.

    Returns:
        A process exit code.
    """
    from perception.acoustic_detector import (
        AcousticDetectionError,
        HttpAcousticClassifier,
    )

    clf = HttpAcousticClassifier(
        args.url,
        config.ACOUSTIC_INFERENCE_TIMEOUT_S,
        window_hop_fraction=config.ACOUSTIC_WINDOW_HOP_FRACTION,
        max_windows=config.ACOUSTIC_MAX_WINDOWS,
    )

    try:
        info = clf.model_info()
    except AcousticDetectionError as exc:
        print(f"could not reach the runner at {args.url}: {exc}", file=sys.stderr)
        print("start it with: edge-impulse-linux-runner --model-file "
              "<acoustic.eim> --run-http-server <port>", file=sys.stderr)
        return 1

    print(f"model: {len(info.labels)} labels {info.labels}")
    print(f"       window {info.window_s:.3f}s "
          f"({info.input_features_count} features @ {info.frequency:g} Hz)")
    if info.unknown_labels:
        print(f"       UNROUTABLE LABELS: {info.unknown_labels} - "
              "bridge/rpc.py's AcousticClass does not define these")
    print()

    # Capture length comes from the model, not from --seconds: the runner
    # rejects any feature count other than input_features_count outright.
    args.seconds = clf.required_capture_s(windows=config.ACOUSTIC_CAPTURE_WINDOWS)
    args.rate = int(info.frequency)

    try:
        clip = _capture(args)
    except MicrophoneError as exc:
        print(f"capture failed: {exc}", file=sys.stderr)
        return 1

    print()
    _print_clip(clip)
    if not _report_health(clip) and not args.force:
        print()
        print("  not classifying a clip that fails the gate - this is the "
              "production behaviour, not a bug.")
        print("  pass --force to classify anyway and see what a dead "
              "microphone scores as.")
        return 1

    print()
    try:
        result = clf(clip)
    except AcousticDetectionError as exc:
        print(f"classification failed: {exc}", file=sys.stderr)
        return 1

    for window in result.windows:
        top = json.dumps(
            {k: round(v, 4) for k, v in sorted(
                window.scores.items(), key=lambda kv: -kv[1])}
        )
        print(f"  t={window.offset_samples / clip.sample_rate:5.2f}s  {top}")

    selected = result.selected
    print()
    if selected is None:
        print("  no window could be classified")
        return 1
    routed = selected.to_acoustic_class()
    print(f"  selected: {selected.label} @ {selected.confidence:.3f}")
    if routed is None:
        print("  routes as: UNROUTABLE - reconcile bridge/rpc.py's "
              "AcousticClass with the deployed impulse")
        return 1
    print(f"  routes as: {routed.value}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Assemble the CLI.

    Returns:
        A configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="mic_check",
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_capture_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--device", default=None,
                       help="ALSA device, e.g. plughw:1,0 (default: discover)")
        p.add_argument("--rate", type=int, default=config.ACOUSTIC_SAMPLE_RATE_HZ,
                       help="capture rate in Hz (default: the impulse's own rate)")

    p_devices = sub.add_parser("devices", help="list capture cards")
    p_devices.set_defaults(func=cmd_devices)

    p_levels = sub.add_parser("levels", help="capture once and print levels")
    add_capture_args(p_levels)
    p_levels.add_argument("--seconds", type=float, default=5.0)
    p_levels.add_argument("--segments", action="store_true",
                          help="also print per-0.5s RMS with a level bar")
    p_levels.add_argument("--save", default=None, help="write a WAV here")
    p_levels.set_defaults(func=cmd_levels)

    p_cal = sub.add_parser("calibrate", help="measure mic on vs off, recommend a floor")
    add_capture_args(p_cal)
    p_cal.add_argument("--seconds", type=float, default=10.0)
    p_cal.add_argument("--save-dir", default=str(_DEFAULT_OUT_DIR),
                       help="write mic_on.wav/mic_off.wav here (default: ./output)")
    p_cal.set_defaults(func=cmd_calibrate)

    p_cls = sub.add_parser("classify", help="capture and run the full chain")
    add_capture_args(p_cls)
    p_cls.add_argument("--url", default=config.ACOUSTIC_INFERENCE_URL)
    p_cls.add_argument("--force", action="store_true",
                       help="classify even a clip that fails the health gate")
    p_cls.set_defaults(seconds=0.0, func=cmd_classify)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Argument list, or None to read sys.argv.

    Returns:
        A process exit code.
    """
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
