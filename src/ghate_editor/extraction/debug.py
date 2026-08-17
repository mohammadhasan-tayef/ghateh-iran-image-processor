"""Debug dumps for locked-alpha inspection. Not used in the hot path unless opted in."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .lock import FinalAlpha
from .zones import zone_images


def _zoom_edge(
    rgb: Image.Image,
    alpha: Image.Image,
    *,
    factor: int,
    band_px: int = 48,
) -> Image.Image:
    a = np.asarray(alpha.convert("L"), dtype=np.uint8)
    trans = (a > 8) & (a < 248)
    if not trans.any():
        crop = rgb.convert("RGB").resize(
            (rgb.width * factor, rgb.height * factor), Image.Resampling.NEAREST
        )
        return crop
    ys, xs = np.where(trans)
    y0 = max(0, int(ys.min()) - band_px)
    y1 = min(a.shape[0], int(ys.max()) + 1 + band_px)
    x0 = max(0, int(xs.min()) - band_px)
    x1 = min(a.shape[1], int(xs.max()) + 1 + band_px)
    crop = rgb.convert("RGB").crop((x0, y0, x1, y1))
    return crop.resize(
        (max(1, crop.width * factor), max(1, crop.height * factor)),
        Image.Resampling.NEAREST,
    )


def save_alpha_lock_debug(
    out_dir: Path | str,
    *,
    original: Image.Image,
    locked: FinalAlpha,
    product_rgba: Image.Image,
    white_composite: Image.Image,
    final_2000: Image.Image | None = None,
    zones: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    original.convert("RGB").save(root / "original.png")
    locked.image().save(root / "selected_alpha.png")
    product_rgba.convert("RGBA").save(root / "product_rgba.png")
    if zones is not None:
        zimg = zone_images(zones)
        zimg["interior_mask"].save(root / "interior_mask.png")
        zimg["edge_protection_mask"].save(root / "edge_protection_mask.png")
        zimg["background_mask"].save(root / "background_mask.png")
    white_composite.convert("RGB").save(root / "white_composite.png")
    final = final_2000 or white_composite
    final.convert("RGB").save(root / "final_2000.png")
    _zoom_edge(product_rgba.convert("RGB"), locked.image(), factor=4).save(
        root / "edge_crop_4x.png"
    )
    _zoom_edge(product_rgba.convert("RGB"), locked.image(), factor=8).save(
        root / "edge_crop_8x.png"
    )
    meta = {
        "alpha_lock": locked.to_meta(),
        "zones": None
        if zones is None
        else {
            k: zones.get(k)
            for k in ("width_px", "bbox", "interior_frac", "edge_frac", "background_frac")
        },
        "extra": extra or {},
    }
    (root / "lock_meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8"
    )
    return root
