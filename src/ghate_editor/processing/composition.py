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


def straight_over_white(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Straight (non-premultiplied) alpha over exact #FFFFFF."""
    a = np.clip(alpha.astype(np.float32) / 255.0, 0.0, 1.0)[:, :, None]
    src = rgb.astype(np.float32)
    out = src * a + 255.0 * (1.0 - a)
    out[alpha == 0] = 255.0
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def compose_white_square(
    rgba: Image.Image,
    *,
    size: int | None = None,
    with_shadow: bool = False,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
    locked_alpha=None,
    verify_lock: bool = True,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Composite anti-aliased foreground onto pure #FFFFFF canvas.
    Shape-aware scale + visual-mass centering.

    If locked_alpha is provided, RGB and alpha are resized with the SAME
    geometric transform (one LANCZOS of each after a shared crop). Alpha
    checksum is verified before the transform; the lock buffer itself is
    never written.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    size = size or cfg.canvas_size
    # Catalog default: no synthetic shadow unless explicitly enabled.
    if not bool(getattr(cfg, "enable_synthetic_shadow", False)):
        with_shadow = False

    from ghate_editor.extraction.lock import FinalAlpha  # noqa: WPS433

    if locked_alpha is not None and not isinstance(locked_alpha, FinalAlpha):
        locked_alpha = None

    rgba = rgba.convert("RGBA")
    hash_ok = True
    if locked_alpha is not None:
        if verify_lock:
            hash_ok = locked_alpha.verify(rgba.split()[-1], strict=False, label="pre_compose")
            if not hash_ok or not locked_alpha.matches(rgba.split()[-1]):
                from ghate_editor.extraction.lock import restore_locked_alpha

                rgb_only = Image.fromarray(np.asarray(rgba.convert("RGB")), mode="RGB")
                rgba = restore_locked_alpha(rgb_only, locked_alpha)
                hash_ok = locked_alpha.matches(rgba.split()[-1])
                if not hash_ok:
                    from ghate_editor.extraction.lock import AlphaMutationError

                    raise AlphaMutationError("ALPHA_MUTATION_DETECTED pre_compose restore failed")

    thr = 6 if profile.gentle_edges else 8
    bbox = _alpha_bbox(rgba, threshold=thr)
    cropped = rgba.crop(bbox)

    fill = adaptive_product_fill(cropped, profile=profile, cfg=cfg)
    margin = float(np.clip(0.5 * (1.0 - fill), cfg.margin_min_frac, cfg.margin_max_frac))
    max_side = int(size * (1.0 - 2.0 * margin))
    w, h = cropped.size
    scale = min(max_side / max(1, w), max_side / max(1, h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    rgb_c = cropped.convert("RGB")
    a_c = cropped.split()[-1]
    # ONE paired resize: same filter, same size, no separate geometry.
    rgb_r = rgb_c.resize((new_w, new_h), Image.Resampling.LANCZOS)
    a_r = a_c.resize((new_w, new_h), Image.Resampling.LANCZOS)
    rgb_np = np.asarray(rgb_r, dtype=np.uint8)
    a_np = np.asarray(a_r, dtype=np.uint8)
    over = straight_over_white(rgb_np, a_np)
    product = Image.fromarray(over, mode="RGB")
    product_a = Image.fromarray(a_np, mode="L")

    a = a_np.astype(np.float32)
    ys, xs = np.mgrid[0:new_h, 0:new_w]
    mass = float(a.sum())
    if mass > 1:
        cy = float((ys * a).sum() / mass)
        cx = float((xs * a).sum() / mass)
    else:
        cy, cx = new_h / 2.0, new_w / 2.0

    # Shadow padding kept only for optional future mode; default stays 0.
    pad = 48 if with_shadow else 0
    layer_w = new_w + pad * 2
    layer_h = new_h + pad * 2 + (18 if with_shadow else 0)
    layer_rgb = Image.new("RGB", (layer_w, layer_h), (255, 255, 255))
    px, py = pad, pad
    if with_shadow:
        shadow = _soft_shadow(
            product_a,
            blur=max(16, new_w // 45),
            opacity=cfg.contact_shadow_opacity,
            offset_y=max(8, new_h // 90),
        )
        layer_rgba = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
        layer_rgba.paste(shadow, (px, py), shadow)
        prem = Image.fromarray(over, mode="RGB").convert("RGBA")
        prem.putalpha(product_a)
        layer_rgba.paste(prem, (px, py), prem)
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        mass_x = px + cx
        mass_y = py + cy
        paste_x = int(round(size / 2.0 - mass_x))
        paste_y = int(round(size / 2.0 - mass_y))
        paste_x = int(np.clip(paste_x, 0, max(0, size - layer_w)))
        paste_y = int(np.clip(paste_y, 0, max(0, size - layer_h)))
        canvas.paste(layer_rgba, (paste_x, paste_y), layer_rgba)
    else:
        layer_rgb.paste(product, (px, py))
        canvas = Image.new("RGB", (size, size), (255, 255, 255))
        mass_x = px + cx
        mass_y = py + cy
        paste_x = int(round(size / 2.0 - mass_x))
        paste_y = int(round(size / 2.0 - mass_y))
        paste_x = int(np.clip(paste_x, 0, max(0, size - layer_w)))
        paste_y = int(np.clip(paste_y, 0, max(0, size - layer_h)))
        canvas.paste(layer_rgb, (paste_x, paste_y))
        # Exact white outside the product paste (already 255); snap any drip.
        arr = np.asarray(canvas)
        # Reconstruct coverage on canvas via paste coords
        cov = np.zeros((size, size), dtype=np.uint8)
        y0, x0 = paste_y, paste_x
        y1, x1 = min(size, y0 + layer_h), min(size, x0 + layer_w)
        ay0, ax0 = 0, 0
        if y0 < 0:
            ay0 = -y0
            y0 = 0
        if x0 < 0:
            ax0 = -x0
            x0 = 0
        ah, aw = y1 - y0, x1 - x0
        cov[y0:y1, x0:x1] = a_np[ay0 : ay0 + ah, ax0 : ax0 + aw]
        canvas_np = arr.copy()
        canvas_np[cov == 0] = (255, 255, 255)
        canvas = Image.fromarray(canvas_np, mode="RGB")

    info = {
        "fill": fill,
        "margin": margin,
        "product_size": [new_w, new_h],
        "paste": [paste_x, paste_y],
        "bbox": list(bbox),
        "resize_ops": 1,
        "resample": "LANCZOS",
        "composite": "straight_over_white",
        "with_shadow": bool(with_shadow),
        "alpha_locked": locked_alpha is not None,
        "alpha_checksum": locked_alpha.checksum if locked_alpha is not None else None,
        "alpha_hash_verified": bool(hash_ok),
        "scale": scale,
    }
    return canvas, info
