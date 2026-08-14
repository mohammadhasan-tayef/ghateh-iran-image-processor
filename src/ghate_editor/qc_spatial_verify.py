"""
Alternate local segmentation as spatial integrity VERIFIER only.

Does not re-edit the image. Used when spatial loss is suspected but RAW
product-evidence confidence is MEDIUM/LOW.
"""

from __future__ import annotations

from typing import Any, Callable

import numpy as np
from PIL import Image


def _pick_verifier_model(primary_model: str | None) -> str:
    """Always prefer a light alternate — never load BiRefNet solely for QC verify."""
    primary = (primary_model or "u2net").lower()
    if primary == "u2netp":
        return "u2net"
    return "u2netp"


def verify_ambiguous_spatial_loss(
    working_rgb: Image.Image,
    rgba_cutout: Image.Image,
    rf_stats: dict[str, Any],
    *,
    primary_model: str | None = None,
    segment_fn: Callable[..., tuple[Image.Image, int, int]] | None = None,
    max_side: int = 768,
) -> dict[str, Any]:
    """
    Compare alternate-model confident FG against FINAL alpha on suspected loss.

    Upgrades spatial_loss_candidate → large_contiguous_foreground_loss only when
    the verifier agrees the missing region was product (not shadow/background).
    """
    stats = dict(rf_stats)
    candidate = float(stats.get("spatial_loss_candidate") or 0.0) >= 0.5
    conf = str(stats.get("spatial_evidence_confidence") or "LOW").upper()
    already = float(stats.get("large_contiguous_foreground_loss") or 0.0) >= 0.5
    triggered = list(stats.get("_triggered") or [])
    bads = list(stats.get("_bads") or [])
    warns = list(stats.get("_warns") or [])

    if already or not candidate or conf == "HIGH":
        # HIGH already authoritative; nothing to verify
        stats.pop("_lost_grid", None)
        stats.pop("_evidence", None)
        return stats

    if segment_fn is None:
        from .free_pipeline import segment_mask

        segment_fn = segment_mask

    model = _pick_verifier_model(primary_model)
    try:
        from .model_service import release_memory

        release_memory(empty_cuda_cache=True)
    except Exception:
        pass
    try:
        mask, _, _ = segment_fn(
            working_rgb,
            max_side=max_side,
            model_name=model,
            infer_boost=False,
            scene=None,
        )
    except Exception as exc:  # noqa: BLE001
        triggered.append(f"spatial_verifier_error:{type(exc).__name__}")
        # Fail-closed for MEDIUM (keep candidate as warn only); never force on LOW
        stats["spatial_verified"] = 0.0
        stats["spatial_verifier_model"] = model
        stats["_triggered"] = triggered
        stats.pop("_lost_grid", None)
        stats.pop("_evidence", None)
        return stats

    try:
        cut = np.asarray(rgba_cutout.convert("RGBA"), dtype=np.uint8)
        alpha = cut[:, :, 3]
        h, w = alpha.shape[:2]
        m = np.asarray(mask.resize((w, h), Image.Resampling.BILINEAR), dtype=np.uint8)
        # Confident verifier foreground
        v_fg = m >= 140
        solid = alpha >= 80
        soft = alpha >= 40

        # Suspected missing: verifier product not present in FINAL soft alpha
        missing = v_fg & (alpha < 48)
        v_n = int(np.count_nonzero(v_fg))
        miss_n = int(np.count_nonzero(missing))
        miss_frac = float(miss_n / max(1, v_n))

        # Prefer lost-grid if present: map verifier support into lost cells
        lost_grid = stats.get("_lost_grid")
        cell_confirm = 0.0
        if isinstance(lost_grid, np.ndarray) and lost_grid.ndim == 2 and lost_grid.any():
            evidence = stats.get("_evidence")
            if isinstance(evidence, np.ndarray) and evidence.shape == alpha.shape:
                union = evidence | soft
            else:
                union = v_fg | soft
            from .qc_spatial import _bbox_from_mask

            bbox = _bbox_from_mask(union, margin=0.04)
            if bbox is not None:
                y0, y1, x0, x1 = bbox
                gy = np.linspace(y0, y1, lost_grid.shape[0] + 1).astype(int)
                gx = np.linspace(x0, x1, lost_grid.shape[1] + 1).astype(int)
                confirm = 0
                total_lost = int(np.count_nonzero(lost_grid))
                for i in range(lost_grid.shape[0]):
                    for j in range(lost_grid.shape[1]):
                        if not lost_grid[i, j]:
                            continue
                        ys, ye = gy[i], max(gy[i] + 1, gy[i + 1])
                        xs, xe = gx[j], max(gx[j] + 1, gx[j + 1])
                        cell = v_fg[ys:ye, xs:xe]
                        if cell.size and float(cell.mean()) >= 0.28:
                            confirm += 1
                cell_confirm = float(confirm / max(1, total_lost))

        # Verifier says product existed in wiped region
        product_confirmed = (miss_frac >= 0.12 and miss_n >= 400) or (
            cell_confirm >= 0.45 and miss_n >= 200
        )
        # Verifier FG mostly agrees with FINAL → suspected loss was bg/shadow
        agree = float(np.count_nonzero(v_fg & soft) / max(1, v_n))
        bg_like_loss = agree >= 0.82 and miss_frac < 0.08

        stats["spatial_verifier_model"] = model
        stats["spatial_verifier_miss_frac"] = float(miss_frac)
        stats["spatial_verifier_agree"] = float(agree)
        stats["spatial_verifier_cell_confirm"] = float(cell_confirm)

        if product_confirmed and not bg_like_loss:
            stats["large_contiguous_foreground_loss"] = 1.0
            stats["spatial_verified"] = 1.0
            if "large_contiguous_foreground_loss" not in bads:
                bads.append("large_contiguous_foreground_loss")
            triggered.append("spatial_verifier_confirmed_product_loss")
        else:
            stats["large_contiguous_foreground_loss"] = 0.0
            stats["spatial_verified"] = 0.0
            stats["spatial_loss_candidate"] = 0.0
            # Soften metrics so they do not drag completeness/structure alone
            if conf == "LOW" or bg_like_loss:
                stats["largest_missing_region_ratio"] = min(
                    float(stats.get("largest_missing_region_ratio") or 0.0), 0.08
                )
                stats["foreground_survival_score"] = max(
                    float(stats.get("foreground_survival_score") or 0.0), 86.0
                )
            if "spatial_product_loss_warn" not in warns:
                warns.append("spatial_product_loss_warn")
            triggered.append("spatial_verifier_rejected_bg_or_shadow")
    finally:
        try:
            mask.close()
        except Exception:
            pass
        stats.pop("_lost_grid", None)
        stats.pop("_evidence", None)

    stats["_bads"] = bads
    stats["_warns"] = warns
    stats["_triggered"] = triggered
    stats["bad_count"] = float(len(bads))
    stats["warn_count"] = float(len(warns))
    return stats
