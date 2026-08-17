"""Cheap extraction-integrity gate. Must NOT run full QC."""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

# Gate labels
PRIMARY_GOOD = "GOOD"
PRIMARY_UNCERTAIN = "UNCERTAIN"
PRIMARY_INVALID = "INVALID"


def alpha_array(alpha: Image.Image) -> np.ndarray:
    return np.asarray(alpha.convert("L"), dtype=np.float32) / 255.0


def cheap_alpha_metrics(alpha: Image.Image | None) -> dict[str, Any]:
    if alpha is None:
        return {
            "solid_frac": 0.0,
            "soft_frac": 0.0,
            "uncertain_frac": 1.0,
            "interior_mean": 0.0,
            "border_hit": 1.0,
            "ghost_ratio": 1.0,
            "n_components": 0,
            "empty": True,
            "score": 0.0,
        }
    a = alpha_array(alpha)
    h, w = a.shape
    solid = a >= 0.50
    soft = a >= 0.05
    uncertain = (a > 0.05) & (a < 0.95)
    solid_frac = float(solid.mean())
    soft_frac = float(soft.mean())
    uncertain_frac = float(uncertain.mean())
    # Interior: eroded solid core (3px) — do not assume a single blob.
    try:
        from scipy import ndimage

        core = ndimage.binary_erosion(solid, iterations=2)
        n_comp = int(ndimage.label(solid.astype(np.uint8))[1])
    except Exception:
        core = solid[2:-2, 2:-2] if h > 8 and w > 8 else solid
        n_comp = 1 if solid.any() else 0
    if isinstance(core, np.ndarray) and core.size and core.any():
        # Map erosion back if cropped approximation
        if core.shape == solid.shape:
            interior_mean = float(a[core].mean()) if core.any() else 0.0
        else:
            interior_mean = float(a[2:-2, 2:-2][core].mean()) if np.asarray(core).any() else 0.0
    else:
        interior_mean = float(a[solid].mean()) if solid.any() else 0.0

    border = np.concatenate([soft[0, :], soft[-1, :], soft[:, 0], soft[:, -1]])
    border_hit = float(border.mean()) if border.size else 0.0
    ghost_ratio = float(uncertain_frac / max(solid_frac, 1e-4))
    empty = solid_frac < 0.004

    score = 1.0
    if empty:
        score -= 0.7
    if solid_frac < 0.02:
        score -= 0.25
    if solid_frac > 0.88:
        score -= 0.30
    if uncertain_frac > 0.14:
        score -= 0.18
    if interior_mean < 0.82:
        score -= 0.16
    if border_hit > 0.22:
        score -= 0.12
    if ghost_ratio > 2.5:
        score -= 0.22
    # Many *tiny* islands can be noise; many sizable parts can be a real kit.
    # Only penalize extreme fragmentation with almost no mass.
    if n_comp >= 18 and solid_frac < 0.04:
        score -= 0.12
    score = float(np.clip(score, 0.0, 1.0))
    return {
        "solid_frac": round(solid_frac, 5),
        "soft_frac": round(soft_frac, 5),
        "uncertain_frac": round(uncertain_frac, 5),
        "interior_mean": round(interior_mean, 4),
        "border_hit": round(border_hit, 4),
        "ghost_ratio": round(ghost_ratio, 4),
        "n_components": int(n_comp),
        "empty": bool(empty),
        "score": round(score, 4),
    }


def classify_primary(metrics: dict[str, Any], *, free_mode: str = "adaptive") -> str:
    """PRIMARY_GOOD → stop; UNCERTAIN/INVALID → rescue (mode-dependent)."""
    solid = float(metrics.get("solid_frac") or 0.0)
    unc = float(metrics.get("uncertain_frac") or 0.0)
    interior = float(metrics.get("interior_mean") or 0.0)
    ghost = float(metrics.get("ghost_ratio") or 0.0)
    border = float(metrics.get("border_hit") or 0.0)
    empty = bool(metrics.get("empty"))

    if empty or solid < 0.012 or solid > 0.93 or (ghost > 3.5 and interior < 0.55):
        return PRIMARY_INVALID
    if interior < 0.45 and unc > 0.18:
        return PRIMARY_INVALID

    uncertain = (
        unc > 0.11
        or interior < 0.84
        or border > 0.28
        or solid < 0.028
        or solid > 0.78
        or ghost > 1.8
        or float(metrics.get("score") or 0.0) < 0.62
    )
    if not uncertain:
        return PRIMARY_GOOD
    return PRIMARY_UNCERTAIN


def needs_rescue(gate: str, *, free_mode: str = "adaptive") -> bool:
    if gate == PRIMARY_INVALID:
        return True
    if gate == PRIMARY_UNCERTAIN and free_mode != "fast":
        return True
    # quality: same as adaptive (still conditional)
    return False
