"""Shape-aware composition onto pure white 1:1 canvas."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .config import ProcessingConfig
from .profiles import ProductProfile, ProfileDecision


def _alpha_bbox(rgba: Image.Image, threshold: int = 8) -> tuple[int, int, int, int]:
    alpha = rgba.split()[-1]
    mask = alpha.point(lambda a: 255 if a > threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return (0, 0, rgba.width, rgba.height)
    return bbox


def _soft_shadow(
    alpha: Image.Image,
    *,
    blur: int = 28,
    opacity: float = 0.18,
    offset_y: int = 12,
) -> Image.Image:
    blur = max(8, min(int(blur), 36))
    shadow_a = alpha.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    scaled = shadow_a.point(lambda a: int(a * opacity))
    shadow.putalpha(scaled)
    canvas = Image.new("RGBA", (alpha.size[0], alpha.size[1] + offset_y), (0, 0, 0, 0))
    canvas.paste(shadow, (0, offset_y), shadow)
    return canvas


def adaptive_product_fill(
    cropped: Image.Image,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> float:
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    w, h = cropped.size
    aspect = max(w, h) / max(1, min(w, h))
    fill = profile.product_fill
    if aspect >= 2.5:
        fill = min(cfg.product_fill_max, fill + 0.04)
    elif aspect <= 1.15:
        fill = max(cfg.product_fill_min, fill - 0.02)
    return float(np.clip(fill, cfg.product_fill_min, cfg.product_fill_max))


def compose_white_square(
    rgba: Image.Image,
    *,
    size: int | None = None,
    with_shadow: bool = False,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Composite anti-aliased foreground onto pure #FFFFFF canvas.
    Shape-aware scale + visual-mass centering.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    size = size or cfg.canvas_size

    rgba = rgba.convert("RGBA")
    thr = 6 if profile.gentle_edges else 8
    bbox = _alpha_bbox(rgba, threshold=thr)
    cropped = rgba.crop(bbox)

    fill = adaptive_product_fill(cropped, profile=profile, cfg=cfg)
    # Leave margin
    margin = float(np.clip(0.5 * (1.0 - fill), cfg.margin_min_frac, cfg.margin_max_frac))
    max_side = int(size * (1.0 - 2.0 * margin))
    w, h = cropped.size
    scale = min(max_side / max(1, w), max_side / max(1, h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    product = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # Visual mass center (alpha-weighted)
    a = np.asarray(product.split()[-1], dtype=np.float32)
    ys, xs = np.mgrid[0:new_h, 0:new_w]
    mass = a.sum()
    if mass > 1:
        cy = float((ys * a).sum() / mass)
        cx = float((xs * a).sum() / mass)
    else:
        cy, cx = new_h / 2.0, new_w / 2.0

    pad = 48 if with_shadow else 0
    layer_w = new_w + pad * 2
    layer_h = new_h + pad * 2 + (18 if with_shadow else 0)
    layer = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    px, py = pad, pad
    if with_shadow:
        shadow = _soft_shadow(
            product.split()[-1],
            blur=max(16, new_w // 45),
            opacity=cfg.contact_shadow_opacity,
            offset_y=max(8, new_h // 90),
        )
        layer.paste(shadow, (px, py), shadow)
    layer.paste(product, (px, py), product)

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    # Place so visual mass lands near canvas center
    # Product mass in layer coords
    mass_x = px + cx
    mass_y = py + cy
    paste_x = int(round(size / 2.0 - mass_x))
    paste_y = int(round(size / 2.0 - mass_y))
    # Clamp so product stays fully on canvas
    lx, ly = layer.size
    paste_x = int(np.clip(paste_x, 0, max(0, size - lx)))
    paste_y = int(np.clip(paste_y, 0, max(0, size - ly)))
    canvas.paste(layer, (paste_x, paste_y), layer)

    info = {
        "fill": fill,
        "margin": margin,
        "product_size": [new_w, new_h],
        "paste": [paste_x, paste_y],
        "bbox": list(bbox),
    }
    return canvas, info
