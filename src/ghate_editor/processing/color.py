"""Adaptive exposure / white balance with color-preservation guards."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .analyzer import ImageAnalysis
from .config import ProcessingConfig
from .profiles import ProductProfile, ProfileDecision


@dataclass
class ColorPreservationResult:
    delta_e: float
    acceptable: bool
    rolled_back: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta_e": self.delta_e,
            "acceptable": self.acceptable,
            "rolled_back": self.rolled_back,
        }


def _srgb_to_linear(c: np.ndarray) -> np.ndarray:
    c = np.clip(c / 255.0, 0.0, 1.0)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _rgb_to_lab_mean(rgb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Approximate mean Lab of masked pixels (D65)."""
    if not mask.any():
        return np.array([50.0, 0.0, 0.0], dtype=np.float64)
    pix = rgb[mask].astype(np.float64)
    lin = _srgb_to_linear(pix)
    # sRGB D65 matrix
    m = np.array(
        [
            [0.4124564, 0.3575761, 0.1804375],
            [0.2126729, 0.7151522, 0.0721750],
            [0.0193339, 0.1191920, 0.9503041],
        ],
        dtype=np.float64,
    )
    xyz = lin @ m.T
    # D65 white
    x_n, y_n, z_n = 0.95047, 1.0, 1.08883
    xyz_n = xyz / np.array([x_n, y_n, z_n])

    def f(t: np.ndarray) -> np.ndarray:
        delta = 6 / 29
        return np.where(t > delta**3, np.cbrt(t), t / (3 * delta**2) + 4 / 29)

    fx, fy, fz = f(xyz_n[:, 0]), f(xyz_n[:, 1]), f(xyz_n[:, 2])
    L = 116 * fy - 16
    a = 500 * (fx - fy)
    b = 200 * (fy - fz)
    return np.array([L.mean(), a.mean(), b.mean()], dtype=np.float64)


def delta_e76(lab1: np.ndarray, lab2: np.ndarray) -> float:
    d = lab1 - lab2
    return float(np.sqrt(np.dot(d, d)))


def product_color_signature(rgba: Image.Image) -> np.ndarray:
    arr = np.asarray(rgba.convert("RGBA"), dtype=np.float32)
    rgb = arr[:, :, :3]
    a = arr[:, :, 3]
    mask = a >= 80
    return _rgb_to_lab_mean(rgb, mask)


def check_color_preservation(
    before_lab: np.ndarray,
    after_rgba: Image.Image,
    *,
    max_delta_e: float,
) -> ColorPreservationResult:
    after_lab = product_color_signature(after_rgba)
    de = delta_e76(before_lab, after_lab)
    return ColorPreservationResult(delta_e=de, acceptable=de <= max_delta_e)


def adaptive_exposure_wb(
    rgba: Image.Image,
    analysis: ImageAnalysis,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Mild per-image exposure and WB. Skips when already good.
    Returns adjusted RGBA + report; caller should run color preservation.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    rgba = rgba.convert("RGBA")
    alpha = rgba.split()[-1]
    rgb = rgba.convert("RGB")
    report: dict[str, Any] = {
        "exposure_gain": 1.0,
        "wb_applied": False,
        "skipped": False,
        "local_contrast": 0.0,
    }

    # Target luma by profile
    if ProductProfile.DARK_OBJECT in profile.tags or profile.primary == ProductProfile.DARK_OBJECT:
        target = cfg.target_fg_luma_dark
    elif ProductProfile.WHITE_OBJECT in profile.tags or profile.primary == ProductProfile.WHITE_OBJECT:
        target = cfg.target_fg_luma_white
    else:
        target = cfg.target_fg_luma

    mean = analysis.mean_luma
    # Already good?
    good_exposure = abs(mean - target) < 18.0 and analysis.highlight_clip < 0.04
    good_wb = analysis.wb_tendency == "neutral" or abs(analysis.color_cast[0]) < 8
    if good_exposure and good_wb and analysis.sharpness >= 0.55:
        report["skipped"] = True
        report["reason"] = "no_significant_correction_required"
        return rgba, report

    gain = 1.0
    if not good_exposure:
        if mean < target - 8:
            gain = min(cfg.max_exposure_gain, target / max(mean, 1.0))
            # Protect dark objects from greying out
            if profile.primary == ProductProfile.DARK_OBJECT:
                gain = min(gain, 1.10)
        elif mean > target + 12:
            gain = max(cfg.max_exposure_cut, target / max(mean, 1.0))
            if profile.primary == ProductProfile.WHITE_OBJECT:
                gain = max(gain, 0.96)  # barely darken whites

    arr = np.asarray(rgb, dtype=np.float32)
    a = np.asarray(alpha, dtype=np.uint8)
    fg = a >= 40

    if abs(gain - 1.0) > 0.01 and fg.any():
        # Soft highlight protection
        lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        protect = np.clip((lum - 220.0) / 35.0, 0.0, 1.0)
        eff = gain * (1.0 - protect) + 1.0 * protect
        adj = arr.copy()
        adj[fg] = np.clip(arr[fg] * eff[fg, None], 0, 255)
        arr = adj
        report["exposure_gain"] = float(gain)

    # Conservative WB
    if not good_wb and not profile.conservative_color:
        rg, gb, rb = analysis.color_cast
        shift = min(cfg.max_wb_shift, 0.04)
        if analysis.wb_tendency == "warm":
            arr[:, :, 0] = np.clip(arr[:, :, 0] * (1.0 - shift), 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * (1.0 + shift * 0.7), 0, 255)
            report["wb_applied"] = True
            report["wb"] = "cool_correct"
        elif analysis.wb_tendency == "cool":
            arr[:, :, 0] = np.clip(arr[:, :, 0] * (1.0 + shift * 0.7), 0, 255)
            arr[:, :, 2] = np.clip(arr[:, :, 2] * (1.0 - shift), 0, 255)
            report["wb_applied"] = True
            report["wb"] = "warm_correct"
        elif analysis.wb_tendency == "green":
            arr[:, :, 1] = np.clip(arr[:, :, 1] * (1.0 - shift * 0.8), 0, 255)
            report["wb_applied"] = True
            report["wb"] = "magenta_correct"

    out_rgb = Image.fromarray(arr.astype(np.uint8), mode="RGB")

    # Mild local contrast only when flat
    if analysis.contrast < 0.85 and not profile.conservative_color:
        amt = cfg.local_contrast_amount * (0.6 if profile.primary == ProductProfile.DARK_OBJECT else 1.0)
        blurred = out_rgb.filter(ImageFilter.GaussianBlur(2.2))
        base = np.asarray(out_rgb, dtype=np.float32)
        blur = np.asarray(blurred, dtype=np.float32)
        detail = base - blur
        mixed = np.clip(base + detail * amt, 0, 255)
        # Only on FG
        a_f = a.astype(bool)
        base[a_f] = mixed[a_f]
        out_rgb = Image.fromarray(base.astype(np.uint8), mode="RGB")
        report["local_contrast"] = float(amt)

    out = out_rgb.convert("RGBA")
    out.putalpha(alpha)
    return out, report


def apply_with_preservation(
    rgba_original: Image.Image,
    rgba_edited: Image.Image,
    *,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, ColorPreservationResult]:
    """If color drift too high, blend back toward original FG colors."""
    cfg = cfg or ProcessingConfig()
    before = product_color_signature(rgba_original)
    result = check_color_preservation(before, rgba_edited, max_delta_e=cfg.max_delta_e)
    if result.acceptable:
        return rgba_edited, result

    # Blend 60% original color into edited (keep edited alpha)
    o = np.asarray(rgba_original.convert("RGBA"), dtype=np.float32)
    e = np.asarray(rgba_edited.convert("RGBA"), dtype=np.float32)
    if o.shape != e.shape:
        rgba_original = rgba_original.resize(rgba_edited.size, Image.Resampling.LANCZOS)
        o = np.asarray(rgba_original.convert("RGBA"), dtype=np.float32)
    blend = e.copy()
    blend[:, :, :3] = 0.55 * o[:, :, :3] + 0.45 * e[:, :, :3]
    blend[:, :, 3] = e[:, :, 3]
    out = Image.fromarray(np.clip(blend, 0, 255).astype(np.uint8), mode="RGBA")
    again = check_color_preservation(before, out, max_delta_e=cfg.max_delta_e)
    if not again.acceptable:
        # Stronger rollback
        blend[:, :, :3] = 0.8 * o[:, :, :3] + 0.2 * e[:, :, :3]
        out = Image.fromarray(np.clip(blend, 0, 255).astype(np.uint8), mode="RGBA")
        again = check_color_preservation(before, out, max_delta_e=cfg.max_delta_e)
        again.rolled_back = True
    else:
        again.rolled_back = True
    return out, again
