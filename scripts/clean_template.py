"""
Convert the reference card `mochibo.png` from a baked-in checkerboard background
to a real alpha channel.

The source file is RGB (no alpha). What looks like transparency is actually an
8-px checkerboard painted into the pixels, alternating ~#E6E7E6 / ~#FDFDFD.
Feeding that to an image model as a style reference teaches it to paint a
checkerboard, so we strip it once, here, and commit the cleaned result.

Method: mark every near-neutral light pixel, keep only the connected region that
touches the image border (so identical colours *inside* the artwork survive),
then clean up the edge with a small dilation + alpha feather.

Usage:  python scripts/clean_template.py <in.png> <out.png>
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage


def checkerboard_mask(rgb: np.ndarray) -> np.ndarray:
    """Near-neutral, light pixels — the two checkerboard greys and nothing else."""
    r, g, b = rgb[..., 0].astype(int), rgb[..., 1].astype(int), rgb[..., 2].astype(int)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    neutral = (mx - mn) <= 6          # almost no saturation
    light = mn >= 218                 # both checker greys sit well above this
    return neutral & light


def border_connected(mask: np.ndarray) -> np.ndarray:
    """Keep only mask regions reachable from the image border."""
    labels, n = ndimage.label(mask)
    if n == 0:
        return np.zeros_like(mask, dtype=bool)
    edge = np.concatenate([labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]])
    keep = [int(v) for v in np.unique(edge) if v != 0]
    return np.isin(labels, keep)


def main(src: Path, dst: Path) -> None:
    im = Image.open(src).convert("RGB")
    rgb = np.asarray(im)

    outside = border_connected(checkerboard_mask(rgb))

    # Pull the cut one pixel *into* the background so no checker fringe survives.
    outside = ndimage.binary_dilation(outside, iterations=1)

    alpha = np.where(outside, 0, 255).astype(np.uint8)
    a_img = Image.fromarray(alpha, mode="L").filter(ImageFilter.GaussianBlur(0.6))

    out = im.convert("RGBA")
    out.putalpha(a_img)
    out.save(dst, "PNG", optimize=True)

    transparent = int((np.asarray(a_img) < 8).sum())
    total = alpha.size
    print(f"source      : {src}  {im.size}  mode=RGB (no alpha)")
    print(f"written     : {dst}  mode=RGBA")
    print(f"transparent : {transparent:,} / {total:,} px  ({transparent / total:.1%})")
    corners = [(2, 2), (im.width - 3, 2), (2, im.height - 3), (im.width - 3, im.height - 3)]
    print(f"corner alpha: {[out.getpixel(c)[3] for c in corners]}  (expect all 0)")
    print(f"centre alpha: {out.getpixel((im.width // 2, im.height // 2))[3]}  (expect 255)")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
