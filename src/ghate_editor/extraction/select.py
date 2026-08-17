"""Choose the safest alpha between primary and optional rescue.

Priority: product completeness > thin parts/holes > low halo. Never assume
BiRefNet is better just because it ran.
"""

from __future__ import annotations

from typing import Any

from .integrity import PRIMARY_INVALID, cheap_alpha_metrics
from .types import ExtractionResult


def select_candidate(
    primary: ExtractionResult | None,
    rescue: ExtractionResult | None,
) -> tuple[ExtractionResult, dict[str, Any]]:
    meta: dict[str, Any] = {
        "primary_engine": primary.engine_name if primary else None,
        "rescue_engine": rescue.engine_name if rescue else None,
        "reason": "primary_only",
    }
    if primary is None or primary.alpha is None:
        if rescue is not None and rescue.alpha is not None:
            meta["reason"] = "primary_missing"
            rescue.metadata["selected"] = True
            return rescue, meta
        raise RuntimeError("no_extraction_candidate")
    if rescue is None or rescue.alpha is None:
        primary.metadata["selected"] = True
        return primary, meta

    p = primary.metadata.get("metrics") or cheap_alpha_metrics(primary.alpha)
    r = rescue.metadata.get("metrics") or cheap_alpha_metrics(rescue.alpha)
    p_solid = float(p.get("solid_frac") or 0.0)
    r_solid = float(r.get("solid_frac") or 0.0)
    p_unc = float(p.get("uncertain_frac") or 0.0)
    r_unc = float(r.get("uncertain_frac") or 0.0)
    p_int = float(p.get("interior_mean") or 0.0)
    r_int = float(r.get("interior_mean") or 0.0)
    p_gate = primary.gate or primary.metadata.get("gate") or ""

    # Rescue ate a large chunk of product compared to primary → keep primary.
    if p_gate != PRIMARY_INVALID and r_solid < p_solid * 0.72 and p_solid >= 0.02:
        meta["reason"] = "rescue_lost_product"
        primary.metadata["selected"] = True
        return primary, meta

    # Primary is a ghost / empty and rescue recovered mass.
    if (p_gate == PRIMARY_INVALID or p_solid < 0.02) and r_solid > max(0.03, p_solid * 1.2):
        meta["reason"] = "rescue_recovered_product"
        rescue.metadata["selected"] = True
        return rescue, meta

    # Similar coverage: prefer the crisper interior / smaller uncertain band.
    if abs(r_solid - p_solid) / max(p_solid, r_solid, 1e-4) < 0.18:
        rescue_cleaner = (r_unc + 0.025 < p_unc) and (r_int + 0.02 >= p_int)
        if rescue_cleaner:
            meta["reason"] = "rescue_cleaner_edges"
            rescue.metadata["selected"] = True
            return rescue, meta
        meta["reason"] = "primary_comparable_keep"
        primary.metadata["selected"] = True
        return primary, meta

    if r_solid > p_solid * 1.15 and r_int >= min(0.75, p_int):
        meta["reason"] = "rescue_more_complete"
        rescue.metadata["selected"] = True
        return rescue, meta

    meta["reason"] = "primary_default"
    primary.metadata["selected"] = True
    return primary, meta
