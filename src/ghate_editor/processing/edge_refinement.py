"""Edge refinement and color decontamination near mask boundaries."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .config import ProcessingConfig
from .morphology import binary_dilate, binary_erode, max_filter_radius_from_size
from .profiles import ProductProfile, ProfileDecision


def refine_edges(
    rgba: Image.Image,
    rgb_src: Image.Image,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Align alpha boundary with image gradients; light AA; strip jagged leftovers.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)

    rgba = rgba.convert("RGBA")
    src = rgb_src.convert("RGB")
    if src.size != rgba.size:
        src = src.resize(rgba.size, Image.Resampling.LANCZOS)

    arr_rgba = np.asarray(rgba, dtype=np.float32)
    alpha = arr_rgba[:, :, 3]
    rgb_keep = arr_rgba[:, :, :3]
    arr = np.asarray(src, dtype=np.float32)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    gy, gx = np.gradient(lum)
    grad = np.sqrt(gx * gx + gy * gy)

    soft = (alpha >= 20) & (alpha <= 230)
    strong_edge = grad > 18.0
    recover = soft & strong_edge & (alpha >= 40) & (alpha < 160)
    alpha2 = alpha.copy()
    if recover.any() and not profile.gentle_edges:
        alpha2[recover] = np.minimum(255.0, alpha2[recover] * 1.12 + 10.0)

    solid = alpha >= 160
    dil = binary_dilate(solid, radius=max_filter_radius_from_size(5))
    fringe = soft & (~dil) & (grad < 10.0)
    if fringe.any():
        strength = 0.55 if profile.gentle_edges else 0.75
        alpha2[fringe] = alpha2[fringe] * (1.0 - strength)

    out_a = Image.fromarray(np.clip(alpha2, 0, 255).astype(np.uint8), mode="L")
    blur = 0.35 if profile.preserve_holes else 0.55
    out_a = out_a.filter(ImageFilter.GaussianBlur(blur))

    out = Image.fromarray(np.clip(rgb_keep, 0, 255).astype(np.uint8), mode="RGB").convert(
        "RGBA"
    )
    out.putalpha(out_a)
    info = {
        "recover_px": int(recover.sum()) if recover.any() else 0,
        "fringe_px": int(fringe.sum()) if fringe.any() else 0,
    }
    return out, info


def decontaminate_halo(
    rgba: Image.Image,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
    bg_color: tuple[int, int, int] = (255, 255, 255),
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Remove background color bleed on edge pixels without shifting core product color.
    Conservative — lower strength for white/metallic products.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)

    rgba = rgba.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    solid = alpha >= 180
    soft = (alpha >= 25) & (alpha < 200)
    dil = binary_dilate(solid, radius=max_filter_radius_from_size(cfg.halo_band_px * 2 + 1))
    band = soft & dil

    strength = cfg.decontam_strength_white if profile.gentle_edges else cfg.decontam_strength
    if ProductProfile.DARK_OBJECT in (profile.tags or [profile.primary]):
        strength = min(strength, 0.40)

    bg = np.array(bg_color, dtype=np.float32)
    out = rgb
    touched = 0
    if band.any():
        eroded = binary_erode(solid, radius=max_filter_radius_from_size(3))
        if eroded.any():
            fg_mean = rgb[eroded].mean(axis=0)
        else:
            fg_mean = rgb[solid].mean(axis=0) if solid.any() else rgb.mean(axis=(0, 1))

        edge_pix = rgb[band]
        d_bg = np.linalg.norm(edge_pix - bg, axis=1)
        d_fg = np.linalg.norm(edge_pix - fg_mean, axis=1)
        contam = d_bg < d_fg * 1.15
        if contam.any():
            out = rgb.copy()
            idx = np.where(band)
            sel = contam
            ys, xs = idx[0][sel], idx[1][sel]
            t = strength * (1.0 - alpha[ys, xs] / 255.0)
            t = np.clip(t, 0.0, strength)[:, None]
            out[ys, xs] = edge_pix[sel] * (1.0 - t) + fg_mean[None, :] * t
            touched = int(ys.size)

    if touched:
        result = np.concatenate([out, alpha[:, :, None]], axis=2)
        img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGBA")
    else:
        img = rgba
    return img, {"decontam_px": touched, "strength": strength}


def uncomposite_edge_band(
    rgba: Image.Image,
    working_rgb: Image.Image,
    *,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Edge-only color unmix against local background estimated from working RGB.

    Interior solid pixels stay the original working RGB. Partial-alpha fringe
    is unpremultiplied so gray floor / halo does not composite onto white.
    """
    from .alpha_matting import uncomposite_edge_rgb
    from .morphology import binary_dilate

    cfg = cfg or ProcessingConfig()
    rgba = rgba.convert("RGBA")
    src = working_rgb.convert("RGB")
    if src.size != rgba.size:
        src = src.resize(rgba.size, Image.Resampling.LANCZOS)

    arr = np.asarray(rgba, dtype=np.uint8)
    rgb_keep = np.asarray(src, dtype=np.uint8)
    alpha = arr[:, :, 3].astype(np.float32) / 255.0
    solid = alpha >= 0.78
    soft = (alpha >= 0.04) & (alpha < 0.92)
    if not soft.any():
        # Interior RGB locked to original
        out = np.dstack([rgb_keep, arr[:, :, 3]])
        return Image.fromarray(out, mode="RGBA"), {"uncomposite_px": 0}

    band = binary_dilate(solid, radius=max(1, cfg.halo_band_px)) & soft
    src_f = rgb_keep.astype(np.float32)
    # Per-pixel local background from working RGB just outside the product
    exterior = binary_dilate(alpha >= 0.08, radius=cfg.halo_band_px + 3) & (alpha < 0.08)
    from .alpha_matting import _nearest_color

    if exterior.any():
        bg_map, _ = _nearest_color(src_f, exterior)
        bg_mean = src_f[exterior].mean(axis=0)
    else:
        h, w = alpha.shape
        m = max(4, int(0.04 * min(h, w)))
        border = np.zeros_like(alpha, dtype=bool)
        border[:m, :] = True
        border[-m:, :] = True
        border[:, :m] = True
        border[:, -m:] = True
        bg_mean = src_f[border].mean(axis=0) if border.any() else np.array(
            [255.0, 255.0, 255.0], dtype=np.float32
        )
        bg_map = np.broadcast_to(bg_mean.reshape(1, 1, 3), src_f.shape).copy()

    recovered = uncomposite_edge_rgb(src_f, alpha, bg_map, lo=0.04, hi=0.92)
    mixed = rgb_keep.copy()
    # Apply recovered RGB only in the narrow edge band
    mixed[band] = recovered[band]
    # Interior: original RGB
    mixed[solid] = rgb_keep[solid]
    out = np.dstack([mixed, arr[:, :, 3]])
    return Image.fromarray(out, mode="RGBA"), {
        "uncomposite_px": int(band.sum()),
        "bg_color": [float(x) for x in np.asarray(bg_mean).reshape(-1)[:3].tolist()],
    }


def strip_large_shadows(
    rgba: Image.Image,
    *,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Remove dark low-sat fringe likely to be cast shadow / dirty floor,
    keeping the main product mass.
    """
    cfg = cfg or ProcessingConfig()
    rgba = rgba.convert("RGBA")
    arr = np.asarray(rgba, dtype=np.float32)
    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    solid = alpha >= 160
    if not solid.any():
        return rgba, {"shadow_px_removed": 0}

    # MaxFilter(15) → radius 7; MinFilter(5) → radius 2
    dil = binary_dilate(solid, radius=7)
    erode = binary_erode(solid, radius=2)

    # ROI crop: only evaluate shadow-like pixels near the dilated mass
    ys, xs = np.where(dil)
    if ys.size == 0:
        return rgba, {"shadow_px_removed": 0}
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    rgb_c = rgb[y0:y1, x0:x1]
    alpha_c = alpha[y0:y1, x0:x1]
    dil_c = dil[y0:y1, x0:x1]
    erode_c = erode[y0:y1, x0:x1]
    lum_c = 0.299 * rgb_c[:, :, 0] + 0.587 * rgb_c[:, :, 1] + 0.114 * rgb_c[:, :, 2]
    mx = rgb_c.max(axis=2)
    mn = rgb_c.min(axis=2)
    sat_c = np.where(mx > 1.0, (mx - mn) / np.maximum(mx, 1.0) * 255.0, 0.0)

    shadow_like_c = (
        dil_c
        & (~erode_c)
        & (alpha_c >= 20)
        & (lum_c <= cfg.shadow_luma_max)
        & (sat_c <= cfg.shadow_sat_max)
    )
    removed = int(shadow_like_c.sum())
    if removed:
        alpha2 = alpha.copy()
        alpha2[y0:y1, x0:x1][shadow_like_c] = 0.0
        arr2 = arr.copy()
        arr2[:, :, 3] = alpha2
        return Image.fromarray(np.clip(arr2, 0, 255).astype(np.uint8), mode="RGBA"), {
            "shadow_px_removed": removed
        }
    return rgba, {"shadow_px_removed": 0}
