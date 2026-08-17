"""Fidelity assemble: original RGB + locked alpha. RGB-only conservative edge work."""

from __future__ import annotations

import time
from typing import Any

import numpy as np
from PIL import Image

from .lock import AlphaMutationError, FinalAlpha, restore_locked_alpha
from .zones import product_zones


def conservative_edge_decontam(
    original_rgb: Image.Image,
    locked: FinalAlpha,
    zones: dict[str, Any],
    *,
    enabled: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    RGB-only. Writes NEVER go to FINAL_ALPHA.

    Only transitional pixels in the edge band with *strong* background
    contamination are unmixed. Low confidence → keep original RGB.
    Interior RGB is copied unchanged.
    """
    src = np.asarray(original_rgb.convert("RGB"), dtype=np.uint8)
    out = src.copy()
    info: dict[str, Any] = {
        "used": False,
        "touched_px": 0,
        "skipped_reason": None,
    }
    if not enabled:
        info["skipped_reason"] = "disabled"
        return out, info
    a = locked.data.astype(np.float32) / 255.0
    lo = float(zones.get("lo") or 0.02)
    hi = float(zones.get("hi") or 0.98)
    edge = zones["edge"]
    interior = zones["interior"]
    trans = edge & (a > lo) & (a < hi)
    if not trans.any() or not interior.any():
        info["skipped_reason"] = "no_transitional_edge"
        return out, info

    fsrc = src.astype(np.float32)
    fg_mean = fsrc[interior].mean(axis=0)
    bg_mask = zones["background"]
    if bg_mask.any():
        bg_mean = fsrc[bg_mask].mean(axis=0)
    else:
        bg_mean = np.array([255.0, 255.0, 255.0], dtype=np.float32)

    edge_pix = fsrc[trans]
    d_bg = np.linalg.norm(edge_pix - bg_mean, axis=1)
    d_fg = np.linalg.norm(edge_pix - fg_mean, axis=1)
    # Strong contamination only: clearly closer to background than product.
    strong = (d_bg * 1.35) < d_fg
    if not strong.any():
        info["skipped_reason"] = "no_strong_contamination"
        return out, info

    aa = np.maximum(a[trans][strong], 0.05)[:, None]
    recovered = (edge_pix[strong] - (1.0 - aa) * bg_mean) / aa
    recovered = np.clip(recovered, 0.0, 255.0)
    idx = np.where(trans)
    ys, xs = idx[0][strong], idx[1][strong]
    out[ys, xs] = recovered.astype(np.uint8)
    info["used"] = True
    info["touched_px"] = int(ys.size)
    return out, info


def assemble_fidelity_rgba(
    original_rgb: Image.Image,
    locked: FinalAlpha,
    *,
    decontam: bool = True,
    canvas_size: int = 2000,
    uncertain: bool = False,
    lo: float = 0.02,
    hi: float = 0.98,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    product.rgb = original_rgb (edge may be conservatively unmixed)
    product.alpha = FINAL_ALPHA (immutable)
    """
    t0 = time.perf_counter()
    if not locked.verify(strict=False):
        raise AlphaMutationError("ALPHA_MUTATION_DETECTED at assemble start")
    zones = product_zones(locked, canvas_size=canvas_size, lo=lo, hi=hi)
    # Uncertain extraction → do not cosmetically unmix (preservation first).
    rgb_u8, dinfo = conservative_edge_decontam(
        original_rgb,
        locked,
        zones,
        enabled=decontam and not uncertain,
    )
    rgba = Image.fromarray(rgb_u8, mode="RGB").convert("RGBA")
    rgba.putalpha(locked.image())
    if not locked.matches(rgba.split()[-1]):
        raise AlphaMutationError("ALPHA_MUTATION_DETECTED after assemble")
    meta = {
        "alpha_lock": locked.to_meta(),
        "alpha_checksum_before": locked.checksum,
        "alpha_checksum_after": locked.checksum,
        "zones": {
            k: zones[k]
            for k in (
                "width_px",
                "bbox",
                "interior_frac",
                "edge_frac",
                "background_frac",
                "lo",
                "hi",
            )
        },
        "decontam": dinfo,
        "resize_ops_after_lock": 0,
        "rgb_source": "original_working_rgb",
        "assemble_ms": round((time.perf_counter() - t0) * 1000.0, 2),
    }
    return rgba, meta
