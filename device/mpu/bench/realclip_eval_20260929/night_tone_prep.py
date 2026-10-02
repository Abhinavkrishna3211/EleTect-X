"""Prepare a night-tone A/B set from the realclip bench frames.

Picks the IR night frames (near-zero saturation) out of frames/, learns the
luma mapping the camera applies when switching from the default tone to the
proposed night tone (from a same-scene pair captured seconds apart on the
board), and writes each night frame twice: as recorded, and remapped to the
night tone. score_night_tone.py then runs both copies through the live F
runner so the model's scores can be compared frame for frame.

The remap is a histogram quantile mapping between the two paired captures,
applied as a monotone lookup table on luma. It is an approximation of what
the camera's ISP does, good enough to tell whether the model is sensitive to
the change; it cannot reproduce noise or sharpening differences.

Usage: python night_tone_prep.py <base.jpg> <tone.jpg> <out_dir>
"""

import glob
import os
import sys
from itertools import accumulate

from PIL import Image, ImageStat


def cdf(img):
    """Normalised cumulative histogram of an L-mode image."""
    h = img.histogram()
    total = sum(h)
    return [c / total for c in accumulate(h)]


def quantile_lut(base, tone):
    """Monotone LUT mapping base luma levels onto the tone capture's levels."""
    cb, ct = cdf(base), cdf(tone)
    lut, j = [], 0
    for i in range(256):
        while j < 255 and ct[j] < cb[i]:
            j += 1
        lut.append(j)
    return lut


def main():
    """Write orig and tone-mapped copies of every night frame under frames/."""
    base_path, tone_path, out_dir = sys.argv[1:4]
    lut = quantile_lut(Image.open(base_path).convert("L"), Image.open(tone_path).convert("L"))
    os.makedirs(os.path.join(out_dir, "orig"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "tone"), exist_ok=True)
    kept = 0
    for path in sorted(glob.glob("frames/*.jpg")):
        im = Image.open(path)
        small = im.copy()
        small.draft("RGB", (320, 180))
        # IR frames carry a faint tint (mean saturation ~9-11); daylight is ~100.
        if ImageStat.Stat(small.convert("HSV")).mean[1] >= 30:
            continue  # colour frame - daytime, not what the night tone touches
        name = os.path.basename(path)
        if name.startswith("human-"):
            continue  # person frames stay out of any derived set
        rgb = im.convert("RGB")
        rgb.save(os.path.join(out_dir, "orig", name), quality=92)
        rgb.point(lut * 3).save(os.path.join(out_dir, "tone", name), quality=92)
        kept += 1
    print(
        f"{kept} night frames written; lut[0,64,128,192,255] =",
        [lut[i] for i in (0, 64, 128, 192, 255)],
    )


if __name__ == "__main__":
    main()
