"""Measure the node camera's focal length, so ranges stop being a specification.

Every absolute range in the seismic corpus divides a box height by a focal
length, and until this script has run that focal length comes from the lens
listing's nominal 95 degree field of view. The records say so - each one
carries `calibrated: false` - but a specification is not a measurement, and a
wide lens behind an enclosure window is exactly where the two part company.

What makes this worth doing rather than living with the nominal figure:

- **The window is part of the lens.** The enclosure's acrylic sits in the
  optical path and shifts the effective focal length. Calibrating the bare
  camera on a bench measures the wrong system; the chessboard images must be
  shot through the window the node will actually deploy with.
- **A 95 degree lens has real barrel distortion.** Near the frame edges a
  straight line bows, and a bowed box is a mis-measured height. The
  distortion coefficients are written out so a later pass can undistort the
  stored boxes - which is possible precisely because the boxes are stored.
- **It is retroactive.** Running this after a season in the field does not
  invalidate the corpus collected before it. The export script's
  `--recalibrate` re-derives every range from the stored box heights. That is
  the whole reason the raw halves are kept and the derived ones are
  recomputable.

Shooting the images:

1. Print a chessboard - the usual 9x6 inner-corner board is the default here -
   on something rigid. Paper taped to a wall bows and biases the fit.
2. Mount the camera as it will deploy, window and all, and take 15-25 stills
   at the node's full capture resolution. Vary the board's distance and angle
   across the whole frame, and get it into each corner. A set shot only in the
   middle fits the centre well and the edges, where the distortion lives, not
   at all.
3. Keep the board flat and fully visible in every shot. A partly visible board
   is silently dropped.

Then:

    python scripts/calibrate_camera.py --images calib/ --out device/mpu/data/camera_calibration.json
    python scripts/calibrate_camera.py --check device/mpu/data/camera_calibration.json

Needs OpenCV, which is an off-device dependency: this runs on a laptop.
device/mpu stays dependency-free and only ever reads the JSON this writes.
"""

import argparse
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

# The nominal figures the device assumes until this file exists. Duplicated as
# plain numbers rather than imported, so the script runs on a machine that
# does not have device/mpu checked out beside it.
NOMINAL_FOV_DEG = 95.0
NOMINAL_WIDTH_PX = 1920
NOMINAL_HEIGHT_PX = 1080

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp")

# An rms reprojection error above this means the fit did not converge on
# anything trustworthy - usually a bowed board, too few views, or views that
# are all from the same angle. A bad calibration is worse than none, because
# the records would be stamped `calibrated: true`.
RMS_WARN_PX = 1.0

# Fewest usable views. Below this the fit is underdetermined in the
# distortion terms and will happily report a small rms anyway.
MIN_VIEWS = 8


def horizontal_fov_deg(fx, width_px):
    """The field of view the measured focal length implies, in degrees."""
    return 2.0 * math.degrees(math.atan((width_px / 2.0) / fx))


def nominal_focal_px(width_px=NOMINAL_WIDTH_PX, fov_deg=NOMINAL_FOV_DEG):
    """What the device is using today - (w/2) / tan(fov/2)."""
    return (width_px / 2.0) / math.tan(math.radians(fov_deg) / 2.0)


def find_images(directory):
    """Every image in `directory`, sorted, case-insensitively matched."""
    found = []
    for entry in sorted(glob.glob(os.path.join(directory, "*"))):
        if entry.lower().endswith(IMAGE_EXTENSIONS):
            found.append(entry)
    return found


def calibrate(args):
    """Find the board in every image, fit the camera, write the JSON."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        print("this script needs opencv-python and numpy: pip install opencv-python")
        return 2

    paths = find_images(args.images)
    if not paths:
        print(f"no images in {args.images}")
        return 1

    pattern = (args.cols, args.rows)
    # The board's own coordinate system, in squares. Scaling by the real
    # square size would put the extrinsics in millimetres; the focal length
    # in pixels - the only thing the device reads - is unaffected either way,
    # so the unit is left as one square and not asked for.
    objp = np.zeros((pattern[0] * pattern[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:pattern[0], 0:pattern[1]].T.reshape(-1, 2)

    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
    object_points = []
    image_points = []
    size = None
    used = []
    skipped = []

    for path in paths:
        image = cv2.imread(path)
        if image is None:
            skipped.append((path, "unreadable"))
            continue
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        if size is None:
            size = gray.shape[::-1]
        elif gray.shape[::-1] != size:
            # Mixing resolutions would fit one focal length to two pixel
            # scales, which is a silently wrong answer rather than an error.
            skipped.append((path, f"size {gray.shape[::-1]} != {size}"))
            continue
        ok, corners = cv2.findChessboardCorners(gray, pattern, None)
        if not ok:
            skipped.append((path, "board not found"))
            continue
        refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
        object_points.append(objp)
        image_points.append(refined)
        used.append(path)

    for path, why in skipped:
        print(f"skip {os.path.basename(path)}: {why}")
    print(f"{len(used)} of {len(paths)} image(s) usable")
    if len(used) < MIN_VIEWS:
        print(f"need at least {MIN_VIEWS} usable views; the distortion terms are "
              f"underdetermined below that and the fit will look better than it is")
        return 1

    rms, matrix, distortion, _rvecs, _tvecs = cv2.calibrateCamera(
        object_points, image_points, size, None, None
    )
    fx, fy = float(matrix[0][0]), float(matrix[1][1])
    cx, cy = float(matrix[0][2]), float(matrix[1][2])
    width, height = int(size[0]), int(size[1])

    payload = {
        "fx": fx,
        "fy": fy,
        "cx": cx,
        "cy": cy,
        "image_width": width,
        "image_height": height,
        "distortion": [float(v) for v in distortion.ravel()],
        "rms_reprojection_px": float(rms),
        "image_count": len(used),
        "pattern": {"cols": pattern[0], "rows": pattern[1]},
        "calibrated_utc": datetime.now(timezone.utc).isoformat(),
        "note": args.note or "",
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"wrote {args.out}")
    report(payload)

    if rms > RMS_WARN_PX:
        print(f"\nWARNING: rms {rms:.2f} px is above {RMS_WARN_PX} px. A bad "
              f"calibration is worse than none, because every record would be "
              f"stamped calibrated. Reshoot with the board flatter and at more "
              f"angles before putting this on a node.")
    return 0


def report(payload):
    """Say what the measurement means for the ranges the node will produce."""
    fx = payload["fx"]
    width = payload.get("image_width", NOMINAL_WIDTH_PX)
    nominal = nominal_focal_px(width)
    measured_fov = horizontal_fov_deg(fx, width)
    # Range is proportional to focal length, so this ratio is exactly the
    # factor every stored range moves by when the corpus is re-derived.
    factor = fx / nominal if nominal else float("nan")

    print()
    print(f"  focal length   {fx:.1f} px  (fy {payload['fy']:.1f} px)")
    print(f"  principal pt   {payload['cx']:.1f}, {payload['cy']:.1f}  "
          f"(frame centre {width / 2:.1f}, {payload.get('image_height', 0) / 2:.1f})")
    print(f"  measured FOV   {measured_fov:.1f} deg horizontal")
    print(f"  nominal FOV    {NOMINAL_FOV_DEG:.1f} deg  -> {nominal:.1f} px")
    print(f"  rms error      {payload['rms_reprojection_px']:.3f} px over "
          f"{payload['image_count']} view(s)")
    print(f"  range factor   x{factor:.3f}  (every nominal range moves by this "
          f"when re-derived)")
    distortion = payload.get("distortion") or []
    if distortion:
        print(f"  distortion     k1={distortion[0]:.4f}" +
              (f" k2={distortion[1]:.4f}" if len(distortion) > 1 else ""))
    if abs(factor - 1.0) > 0.15:
        print(f"\n  The lens is {abs(1 - factor) * 100:.0f}% off its nominal "
              f"figure, so the corpus collected before this calibration has "
              f"ranges that far out. Re-derive it:")
        print("    python scripts/export_seismic_dataset.py --root <dir> --out <dir> "
              "--recalibrate <this file>")


def check(path):
    """Print what an existing calibration file says, without touching it."""
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"cannot read {path}: {exc}")
        return 1
    if "fx" not in payload:
        print(f"{path} has no fx - the device would ignore it and stay nominal")
        return 1
    print(f"{path}")
    report(payload)
    return 0


def main(argv=None):
    """Parse arguments and either calibrate or report."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--images", help="directory of chessboard stills")
    parser.add_argument("--out", default=os.path.join("device", "mpu", "data",
                                                      "camera_calibration.json"),
                        help="where to write the calibration (default: the path "
                             "config.CAMERA_CALIBRATION_PATH reads)")
    parser.add_argument("--cols", type=int, default=9,
                        help="inner corners across the board (default 9)")
    parser.add_argument("--rows", type=int, default=6,
                        help="inner corners down the board (default 6)")
    parser.add_argument("--note", default="",
                        help="free text stored in the file, e.g. which enclosure "
                             "and window this was shot through")
    parser.add_argument("--check", metavar="FILE",
                        help="report on an existing calibration and exit")
    args = parser.parse_args(argv)

    if args.check:
        return check(args.check)
    if not args.images:
        parser.error("--images is required unless --check is given")
    return calibrate(args)


if __name__ == "__main__":
    sys.exit(main())
