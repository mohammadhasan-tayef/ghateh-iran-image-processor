"""Edge refinement and color decontamination near mask boundaries."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .config import ProcessingConfig
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

    r, g, b, a = rgba.split()
    alpha = np.asarray(a, dtype=np.float32)
    arr = np.asarray(src, dtype=np.float32)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    gy, gx = np.gradient(lum)
    grad = np.sqrt(gx * gx + gy * gy)

    # Boundary band: soft alpha transition
    soft = (alpha >= 20) & (alpha <= 230)
    # Strengthen alpha where strong image edge + mid alpha (recover cut details)
    strong_edge = grad > 18.0
    recover = soft & strong_edge & (alpha >= 40) & (alpha < 160)
    alpha2 = alpha.copy()
    if recover.any() and not profile.gentle_edges:
        alpha2[recover] = np.minimum(255.0, alpha2[recover] * 1.12 + 10.0)

    # Reduce alpha on weak-gradient fog outside solid core (likely halo)
    solid = alpha >= 160
    dil = np.asarray(
        Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(ImageFilter.MaxFilter(5)),
        dtype=np.uint8,
    ) > 0
    fringe = soft & (~dil) & (grad < 10.0)
    if fringe.any():
        strength = 0.55 if profile.gentle_edges else 0.75
        alpha2[fringe] = alpha2[fringe] * (1.0 - strength)

    # Tiny blur for AA
    out_a = Image.fromarray(np.clip(alpha2, 0, 255).astype(np.uint8), mode="L")
    blur = 0.35 if profile.preserve_holes else 0.55
    out_a = out_a.filter(ImageFilter.GaussianBlur(blur))

    out = Image.merge("RGBA", (r, g, b, out_a))
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

    # Edge band
    solid = alpha >= 180
    soft = (alpha >= 25) & (alpha < 200)
    dil = np.asarray(
        Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(
            ImageFilter.MaxFilter(cfg.halo_band_px * 2 + 1)
        ),
        dtype=np.uint8,
    ) > 0
    band = soft & dil

    strength = cfg.decontam_strength_white if profile.gentle_edges else cfg.decontam_strength
    if ProductProfile.DARK_OBJECT in (profile.tags or [profile.primary]):
        strength = min(strength, 0.40)

    bg = np.array(bg_color, dtype=np.float32)
    out = rgb.copy()
    touched = 0
    if band.any():
        # Estimate local FG color from inward solid neighbors
        eroded = np.asarray(
            Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(
                ImageFilter.MinFilter(3)
            ),
            dtype=np.uint8,
        ) > 0
        if eroded.any():
            fg_mean = rgb[eroded].mean(axis=0)
        else:
            fg_mean = rgb[solid].mean(axis=0) if solid.any() else rgb.mean(axis=(0, 1))

        # Pull edge pixels away from bg toward estimated FG
        # Contaminated if closer to bg than to fg_mean
        edge_pix = rgb[band]
        d_bg = np.linalg.norm(edge_pix - bg, axis=1)
        d_fg = np.linalg.norm(edge_pix - fg_mean, axis=1)
        contam = d_bg < d_fg * 1.15
        if contam.any():
            idx = np.where(band)
            # Only contaminated subset
            sel = contam
            ys, xs = idx[0][sel], idx[1][sel]
            t = strength * (1.0 - alpha[ys, xs] / 255.0)
            t = np.clip(t, 0.0, strength)[:, None]
            out[ys, xs] = edge_pix[sel] * (1.0 - t) + fg_mean[None, :] * t
            touched = int(ys.size)

    result = np.concatenate([out, alpha[:, :, None]], axis=2)
    img = Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), mode="RGBA")
    return img, {"decontam_px": touched, "strength": strength}


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
    lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
    mx = rgb.max(axis=2)
    mn = rgb.min(axis=2)
    sat = np.where(mx > 1.0, (mx - mn) / mx * 255.0, 0.0)

    solid = alpha >= 160
    if not solid.any():
        return rgba, {"shadow_px_removed": 0}

    # Dilate solid to find near-product band
    dil = np.asarray(
        Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(ImageFilter.MaxFilter(15)),
        dtype=np.uint8,
    ) > 0
    erode = np.asarray(
        Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(ImageFilter.MinFilter(5)),
        dtype=np.uint8,
    ) > 0

    shadow_like = (
        dil
        & (~erode)
        & (alpha >= 20)
        & (lum <= cfg.shadow_luma_max)
        & (sat <= cfg.shadow_sat_max)
    )
    removed = int(shadow_like.sum())
    if removed:
        alpha2 = alpha.copy()
        alpha2[shadow_like] = 0.0
        arr2 = arr.copy()
        arr2[:, :, 3] = alpha2
        return Image.fromarray(np.clip(arr2, 0, 255).astype(np.uint8), mode="RGBA"), {
            "shadow_px_removed": removed
        }
    return rgba, {"shadow_px_removed": 0}
