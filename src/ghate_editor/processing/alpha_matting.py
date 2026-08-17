"""
Trimap + local closed-form-style alpha matting (no extra models).

Works on the unknown band around the rembg mask. Definite FG/BG stay locked.
Interior product RGB is never written here — callers keep working RGB and
only swap alpha, then optionally uncomposite the thin edge band.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .config import ProcessingConfig
from .morphology import binary_dilate, binary_erode


TRIMAP_FG = 255
TRIMAP_UNKNOWN = 128
TRIMAP_BG = 0


def _luma(rgb: np.ndarray) -> np.ndarray:
    return (
        0.299 * rgb[:, :, 0].astype(np.float32)
        + 0.587 * rgb[:, :, 1].astype(np.float32)
        + 0.114 * rgb[:, :, 2].astype(np.float32)
    )


def _box_mean(x: np.ndarray, radius: int) -> np.ndarray:
    from scipy import ndimage

    size = int(radius) * 2 + 1
    return ndimage.uniform_filter(x, size=size, mode="nearest")


def guided_filter_gray(
    guide: np.ndarray,
    src: np.ndarray,
    *,
    radius: int = 4,
    eps: float = 1e-4,
) -> np.ndarray:
    """He et al. guided filter (single-channel). guide/src in [0,1] float."""
    r = max(1, int(radius))
    mean_i = _box_mean(guide, r)
    mean_p = _box_mean(src, r)
    mean_ii = _box_mean(guide * guide, r)
    mean_ip = _box_mean(guide * src, r)
    var_i = np.maximum(mean_ii - mean_i * mean_i, 0.0)
    cov_ip = mean_ip - mean_i * mean_p
    a = cov_ip / (var_i + float(eps))
    b = mean_p - a * mean_i
    mean_a = _box_mean(a, r)
    mean_b = _box_mean(b, r)
    return mean_a * guide + mean_b


def build_trimap(
    mask: Image.Image | np.ndarray,
    *,
    fg_erode: int = 2,
    bg_dilate: int = 4,
    fg_thr: int = 200,
    bg_thr: int = 18,
) -> np.ndarray:
    """
    Binary-ish rembg alpha → Levin-style trimap.
    255 definite product, 0 definite background, 128 unknown edge.
    """
    if isinstance(mask, Image.Image):
        a = np.asarray(mask.convert("L"), dtype=np.uint8)
    else:
        a = np.asarray(mask, dtype=np.uint8)

    solid = a >= int(fg_thr)
    any_fg = a >= int(bg_thr)
    fg = binary_erode(solid, radius=max(1, int(fg_erode))) if solid.any() else solid
    near = binary_dilate(any_fg, radius=max(1, int(bg_dilate))) if any_fg.any() else any_fg
    bg = ~near

    tri = np.full(a.shape, TRIMAP_UNKNOWN, dtype=np.uint8)
    tri[bg] = TRIMAP_BG
    tri[fg] = TRIMAP_FG
    # Keep obvious voids (true holes already 0 in mask) as BG if they are
    # fully enclosed AND far from residual alpha — handled by bg dilate.
    return tri


def _nearest_color(
    rgb: np.ndarray,
    member: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Nearest member color + Euclidean distance in pixels."""
    from scipy import ndimage

    h, w = member.shape[:2]
    if not member.any():
        return np.zeros((h, w, 3), dtype=np.float32), np.full((h, w), 1e6, dtype=np.float32)

    dist, idx = ndimage.distance_transform_edt(~member, return_indices=True)
    colors = rgb[idx[0], idx[1]].astype(np.float32)
    return colors, dist.astype(np.float32)


def estimate_alpha_from_trimap(
    rgb: np.ndarray,
    trimap: np.ndarray,
    *,
    prior: np.ndarray | None = None,
) -> np.ndarray:
    """
    Shared-matting style unmix using nearest FG/BG colors, then guided filter.

    Prior (0–1) is rembg alpha — used when FG and BG colors are similar
    (white-on-white, light plastics).
    """
    rgb_f = rgb.astype(np.float32)
    unk = trimap == TRIMAP_UNKNOWN
    fg_m = trimap == TRIMAP_FG
    bg_m = trimap == TRIMAP_BG

    out = np.zeros(trimap.shape, dtype=np.float32)
    out[fg_m] = 1.0
    out[bg_m] = 0.0
    if prior is None:
        prior_a = np.clip(trimap.astype(np.float32) / 255.0, 0.0, 1.0)
    else:
        prior_a = prior.astype(np.float32)
        if prior_a.max() > 1.5:
            prior_a = prior_a / 255.0
        prior_a = np.clip(prior_a, 0.0, 1.0)

    if not unk.any():
        return out

    f_col, f_dist = _nearest_color(rgb_f, fg_m)
    b_col, b_dist = _nearest_color(rgb_f, bg_m)
    c = rgb_f[unk]
    f = f_col[unk]
    b = b_col[unk]
    fb = f - b
    denom = np.sum(fb * fb, axis=1) + 1e-4
    unmix = np.sum((c - b) * fb, axis=1) / denom
    unmix = np.clip(unmix, 0.0, 1.0)

    fb_norm = np.sqrt(np.maximum(denom - 1e-4, 0.0))
    # Color-similar FG/BG → trust rembg prior more
    w = np.clip(fb_norm / 38.0, 0.0, 1.0)
    p = prior_a[unk]
    mixed = w * unmix + (1.0 - w) * p

    fd = f_dist[unk]
    bd = b_dist[unk]
    dist_a = bd / np.maximum(fd + bd, 1e-3)
    mixed = 0.55 * mixed + 0.45 * np.clip(dist_a, 0.0, 1.0)

    # Halo / floor: pixel closer to BG color than FG → not product
    d_f = np.sqrt(np.sum((c - f) ** 2, axis=1) + 1e-6)
    d_b = np.sqrt(np.sum((c - b) ** 2, axis=1) + 1e-6)
    closer_bg = d_b * 1.05 < d_f
    mixed = np.where(closer_bg, np.minimum(mixed, dist_a * 0.35), mixed)

    # Weak rembg alpha in the unknown ring is usually floor/shadow leak
    weak = p < 0.70
    mixed = np.where(weak, mixed * np.clip(p / 0.70, 0.0, 1.0), mixed)

    out[unk] = np.clip(mixed, 0.0, 1.0)

    # Smooth unknown band with RGB-guided filter (luma)
    guide = _luma(rgb_f) / 255.0
    smoothed = guided_filter_gray(guide, out, radius=3, eps=2e-4)
    # Relock definite regions
    smoothed[fg_m] = 1.0
    smoothed[bg_m] = 0.0
    # Blend only unknown (keep lock). Re-apply leak suppression AFTER
    # the guided filter so it cannot restore floor/halo alpha.
    post = np.clip(smoothed[unk], 0.0, 1.0)
    post = np.where(p < 0.78, np.minimum(post, np.power(np.clip(p, 0.0, 1.0), 1.15)), post)
    post = np.where(closer_bg, np.minimum(post, 0.18), post)
    out[unk] = np.clip(post, 0.0, 1.0)
    return out


def uncomposite_edge_rgb(
    rgb: np.ndarray,
    alpha01: np.ndarray,
    bg_color: np.ndarray,
    *,
    lo: float = 0.04,
    hi: float = 0.92,
) -> np.ndarray:
    """
    Recover foreground RGB on the *partial-alpha band only*.

    C = a F + (1-a) B  →  F = (C - (1-a) B) / a
    Interior (a>=hi) keeps original RGB unchanged.
    """
    a = np.clip(alpha01.astype(np.float32), 0.0, 1.0)
    band = (a > lo) & (a < hi)
    if not band.any():
        return rgb.astype(np.uint8, copy=True) if rgb.dtype != np.uint8 else rgb.copy()
    c = rgb.astype(np.float32)
    b = bg_color.astype(np.float32)
    if b.ndim == 1:
        b = b.reshape(1, 1, 3)
    aa = np.maximum(a[:, :, None], 1e-3)
    f = (c - (1.0 - a[:, :, None]) * b) / aa
    out = c.copy()
    out[band] = np.clip(f[band], 0.0, 255.0)
    return np.clip(out, 0, 255).astype(np.uint8)


def refine_alpha_matting(
    working_rgb: Image.Image,
    mask: Image.Image,
    *,
    cfg: ProcessingConfig | None = None,
    max_side: int = 1280,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Estimate a refined alpha for `mask` using working RGB (same HxW).

    Returns alpha L-image at original size + diagnostics.
    Downsamples for speed when the frame is large; upsamples alpha only.
    """
    cfg = cfg or ProcessingConfig()
    rgb_img = working_rgb.convert("RGB")
    mask_l = mask.convert("L")
    if mask_l.size != rgb_img.size:
        mask_l = mask_l.resize(rgb_img.size, Image.Resampling.LANCZOS)

    ow, oh = rgb_img.size
    scale = 1.0
    side = max(ow, oh)
    work_rgb = rgb_img
    work_mask = mask_l
    if side > max_side:
        scale = max_side / float(side)
        nw, nh = max(1, int(ow * scale)), max(1, int(oh * scale))
        work_rgb = rgb_img.resize((nw, nh), Image.Resampling.BILINEAR)
        work_mask = mask_l.resize((nw, nh), Image.Resampling.BILINEAR)

    rgb = np.asarray(work_rgb, dtype=np.uint8)
    prior = np.asarray(work_mask, dtype=np.uint8)

    # Restrict to product bbox so EDT/guided-filter stay cheap on large HEIC
    support = prior >= 18
    if support.any():
        ys, xs = np.where(support)
        pad = 24
        y0 = max(0, int(ys.min()) - pad)
        y1 = min(prior.shape[0], int(ys.max()) + 1 + pad)
        x0 = max(0, int(xs.min()) - pad)
        x1 = min(prior.shape[1], int(xs.max()) + 1 + pad)
        rgb_c = rgb[y0:y1, x0:x1]
        prior_c = prior[y0:y1, x0:x1]
    else:
        y0, x0 = 0, 0
        y1, x1 = prior.shape
        rgb_c, prior_c = rgb, prior

    fg_erode = int(getattr(cfg, "matting_fg_erode", 2))
    bg_dilate = int(getattr(cfg, "matting_bg_dilate", 4))
    tri = build_trimap(prior_c, fg_erode=fg_erode, bg_dilate=bg_dilate)
    unk = int(np.count_nonzero(tri == TRIMAP_UNKNOWN))
    frame = int(tri.size)
    unk_frac = float(unk / max(1, frame))
    info: dict[str, Any] = {
        "unknown_px": unk,
        "unknown_frac": unk_frac,
        "matting_scale": float(scale),
        "used": False,
        "reason": "",
        "roi": [y0, y1, x0, x1],
    }
    if unk < 80:
        info["reason"] = "too_few_unknown"
        return mask_l, info
    if unk_frac > 0.42:
        info["reason"] = "trimap_too_uncertain"
        return mask_l, info

    alpha_c = estimate_alpha_from_trimap(rgb_c, tri, prior=prior_c)
    full01 = prior.astype(np.float32) / 255.0
    full01[y0:y1, x0:x1] = alpha_c
    small = Image.fromarray(np.clip(full01 * 255.0, 0, 255).astype(np.uint8), mode="L")
    if small.size != (ow, oh):
        out = small.resize((ow, oh), Image.Resampling.LANCZOS)
    else:
        out = small
    info["used"] = True
    info["fg_px"] = int(np.count_nonzero(tri == TRIMAP_FG))
    info["bg_px"] = int(np.count_nonzero(tri == TRIMAP_BG))
    # Compress foggy mid-alpha into a thin AA band so white composite
    # does not show a wide gray halo. 0..lo → 0, hi..1 → 1.
    lo, hi = 0.20, 0.78
    a = np.asarray(out, dtype=np.float32) / 255.0
    snapped = np.clip((a - lo) / max(1e-6, hi - lo), 0.0, 1.0)
    snapped = snapped * snapped * (3.0 - 2.0 * snapped)  # smoothstep
    out = Image.fromarray(np.clip(snapped * 255.0, 0, 255).astype(np.uint8), mode="L")
    return out, info
