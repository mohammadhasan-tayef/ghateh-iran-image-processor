"""Auxiliary pixel zones derived from locked alpha. Never writes FINAL_ALPHA."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .lock import FinalAlpha


def adaptive_edge_width(
    alpha_hw: tuple[int, int],
    product_bbox: tuple[int, int, int, int],
    *,
    canvas_size: int = 2000,
    product_fill: float = 0.84,
) -> int:
    """
    Protection width in *working* pixels so the band is ~3–5 px at 2000 output.

    Scales with product size and working resolution; never a blind 5px.
    """
    h, w = alpha_hw
    x0, y0, x1, y1 = product_bbox
    prod_side = max(1, x1 - x0, y1 - y0)
    out_prod = float(canvas_size) * float(np.clip(product_fill, 0.5, 0.95))
    scale_to_output = out_prod / float(prod_side)
    # Target ~4 output pixels; clamp working width.
    working_px = 4.0 / max(scale_to_output, 1e-6)
    # Very small products: slightly wider relative band.
    prod_frac = (prod_side / float(max(h, w, 1)))
    if prod_frac < 0.18:
        working_px *= 1.2
    lo = 1 if scale_to_output > 2.5 else 2
    hi = max(8, int(round(0.006 * max(h, w))))
    return int(np.clip(round(working_px), lo, min(hi, 12)))


def _bbox_from_alpha(a: np.ndarray, thr: float = 0.05) -> tuple[int, int, int, int]:
    ys, xs = np.where(a >= thr)
    if ys.size == 0:
        h, w = a.shape
        return (0, 0, w, h)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def product_zones(
    locked: FinalAlpha,
    *,
    canvas_size: int = 2000,
    lo: float = 0.02,
    hi: float = 0.98,
    width: int | None = None,
) -> dict[str, Any]:
    """
    Interior / edge-protection / background as boolean maps.

    Morphology runs on *copies*. FINAL_ALPHA is never written.
    """
    a = locked.data.astype(np.float32) / 255.0
    h, w = a.shape
    bbox = _bbox_from_alpha(a, thr=lo)
    band = width if width is not None else adaptive_edge_width(
        (h, w), bbox, canvas_size=canvas_size
    )
    solid = a >= 0.50
    try:
        from scipy import ndimage

        structure = np.ones((3, 3), dtype=bool)
        eroded = ndimage.binary_erosion(solid, structure=structure, iterations=max(1, band))
        dilated = ndimage.binary_dilation(solid, structure=structure, iterations=max(1, band))
    except Exception:
        # Cheap box erosion/dilation without scipy
        def _box(bin_im: np.ndarray, rad: int, erode: bool) -> np.ndarray:
            from PIL import ImageFilter

            img = Image.fromarray((bin_im.astype(np.uint8) * 255), mode="L")
            k = max(3, 2 * rad + 1)
            if k % 2 == 0:
                k += 1
            out = img.filter(ImageFilter.MinFilter(k) if erode else ImageFilter.MaxFilter(k))
            return np.asarray(out) >= 128

        eroded = _box(solid, band, True)
        dilated = _box(solid, band, False)

    interior = eroded & (a >= hi)
    background = (~dilated) & (a <= lo)
    edge = ~(interior | background)
    # Keep transitional alpha inside the protection band even if erosion missed.
    trans = (a > lo) & (a < hi)
    edge = edge | trans
    interior = interior & ~edge
    background = background & ~edge

    return {
        "interior": interior,
        "edge": edge,
        "background": background,
        "width_px": int(band),
        "bbox": bbox,
        "lo": lo,
        "hi": hi,
        "interior_frac": float(interior.mean()),
        "edge_frac": float(edge.mean()),
        "background_frac": float(background.mean()),
    }


def zone_images(zones: dict[str, Any]) -> dict[str, Image.Image]:
    def _u8(m: np.ndarray) -> Image.Image:
        return Image.fromarray((m.astype(np.uint8) * 255), mode="L")

    return {
        "interior_mask": _u8(zones["interior"]),
        "edge_protection_mask": _u8(zones["edge"]),
        "background_mask": _u8(zones["background"]),
    }
