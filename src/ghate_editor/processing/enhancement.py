"""Adaptive denoise + sharpen — only when justified."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from .analyzer import ImageAnalysis
from .config import ProcessingConfig
from .profiles import ProductProfile, ProfileDecision


def adaptive_denoise_sharpen(
    rgba: Image.Image,
    analysis: ImageAnalysis,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    rgba = rgba.convert("RGBA")
    alpha = rgba.split()[-1]
    rgb = rgba.convert("RGB")
    report: dict[str, Any] = {"denoise": 0.0, "sharpen": 0.0, "skipped": False}

    # Protect mesh / packaging textures — minimal denoise
    protect_texture = profile.preserve_holes or profile.primary in {
        ProductProfile.MESH,
        ProductProfile.PACKAGING,
        ProductProfile.THIN_COMPLEX_EDGES,
    }

    if analysis.noise_level >= cfg.denoise_noise_threshold and not protect_texture:
        strength = cfg.denoise_strength
        if profile.primary == ProductProfile.DARK_OBJECT:
            strength *= 0.7
        blur = rgb.filter(ImageFilter.GaussianBlur(0.65))
        base = np.asarray(rgb, dtype=np.float32)
        b = np.asarray(blur, dtype=np.float32)
        a = np.asarray(alpha, dtype=np.uint8) >= 40
        mixed = base.copy()
        mixed[a] = base[a] * (1.0 - strength) + b[a] * strength
        rgb = Image.fromarray(np.clip(mixed, 0, 255).astype(np.uint8), mode="RGB")
        report["denoise"] = float(strength)
    elif analysis.sharpness >= 1.1 and analysis.noise_level < 0.03:
        report["skipped"] = True
        report["reason"] = "already_sharp_clean"
        out = rgb.convert("RGBA")
        out.putalpha(alpha)
        return out, report

    # Sharpen based on blur estimate
    # sharpness ~0.4 blurry, ~1.0 ok, >1.5 already sharp
    if analysis.sharpness < 0.95:
        amount = float(
            np.interp(
                analysis.sharpness,
                [0.2, 0.95],
                [cfg.sharpen_amount_max, cfg.sharpen_amount_min],
            )
        )
        if protect_texture:
            amount *= 0.55
        if profile.primary == ProductProfile.WHITE_OBJECT:
            amount *= 0.7
        if amount > 0.05:
            # Unsharp via enhance — mild
            factor = 1.0 + amount
            rgb = ImageEnhance.Sharpness(rgb).enhance(factor)
            report["sharpen"] = float(amount)

    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out, report
