"""
Spatial RAW↔FINAL product survival (canonical grid).

Detects large contiguous product regions present in RAW that disappear in FINAL,
without relying on a single global average structure score.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _near_white(rgb: np.ndarray) -> np.ndarray:
    return (
        (rgb[:, :, 0] >= 248)
        & (rgb[:, :, 1] >= 248)
        & (rgb[:, :, 2] >= 248)
    )


def _bbox_from_mask(mask: np.ndarray, margin: float = 0.06) -> tuple[int, int, int, int] | None:
    if not mask.any():
        return None
    ys, xs = np.where(mask)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    h, w = mask.shape[:2]
    bh, bw = max(1, y1 - y0), max(1, x1 - x0)
    my, mx = int(margin * bh), int(margin * bw)
    return max(0, y0 - my), min(h, y1 + my), max(0, x0 - mx), min(w, x1 + mx)


def build_raw_product_evidence(
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
    alpha: np.ndarray,
    *,
    prior_indep: np.ndarray,
    prior_unreliable: bool,
) -> np.ndarray:
    """
    RAW product evidence independent of trusting FINAL alpha alone.

    When the independent prior is scene-bloated, fall back to structured evidence
    inside a dilated FINAL support (still requires RAW material, so real holes
    that were empty in RAW are not counted as loss).
    """
    from scipy import ndimage

    soft = alpha >= 40
    nw = _near_white(rgb)
    if (not prior_unreliable) and float(prior_indep.mean()) <= 0.42 and prior_indep.any():
        return prior_indep & (~nw)

    # Unreliable full-scene prior → structured evidence near the cutout support
    if soft.any():
        ys, xs = np.where(soft)
        bh = max(1, int(ys.max() - ys.min() + 1))
        bw = max(1, int(xs.max() - xs.min() + 1))
        dil_iters = int(min(90, max(20, 0.18 * max(bh, bw) / 3.0)))
        support = ndimage.binary_dilation(soft, iterations=dil_iters)
        bbox = _bbox_from_mask(soft, margin=0.35)
        if bbox is not None:
            y0, y1, x0, x1 = bbox
            roi = np.zeros_like(support)
            roi[y0:y1, x0:x1] = True
            support = support & roi
        core = soft
        if int(np.count_nonzero(core)) >= 80:
            e_thr = max(5.5, float(np.percentile(edge[core], 48)))
            t_thr = max(4.0, float(np.percentile(tex[core], 45)))
        else:
            e_thr, t_thr = 8.0, 6.0
        evidence = support & (~nw) & ((edge >= e_thr) | (tex >= t_thr) | (lum <= 210))
        # Prefer intersection with independent prior when available (reduces floor)
        if prior_indep.any() and float(prior_indep.mean()) < 0.85:
            evidence = evidence & (prior_indep | soft)
        return evidence

    return prior_indep & (~nw)


def compute_spatial_survival(
    rgb: np.ndarray,
    alpha: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
    *,
    prior_indep: np.ndarray,
    prior_unreliable: bool,
    grid: int = 10,
) -> dict[str, Any]:
    """
    Canonical-grid RAW vs FINAL product survival.

    Returns metrics + flags. Does not decide PASS/REVIEW by itself.
    """
    from scipy import ndimage

    h, w = alpha.shape[:2]
    solid = alpha >= 80
    soft = alpha >= 40
    evidence = build_raw_product_evidence(
        rgb,
        lum,
        edge,
        tex,
        alpha,
        prior_indep=prior_indep,
        prior_unreliable=prior_unreliable,
    )
    ev_n = int(np.count_nonzero(evidence))
    kept_ev = evidence & solid
    wiped_ev = evidence & (alpha < 48)
    survival = float(np.count_nonzero(kept_ev) / max(1, ev_n))
    wipe_of_evidence = float(np.count_nonzero(wiped_ev) / max(1, ev_n))

    union = evidence | soft
    bbox = _bbox_from_mask(union, margin=0.04)
    stats: dict[str, Any] = {
        "foreground_survival_score": float(100.0 * survival),
        "evidence_wipe_frac": wipe_of_evidence,
        "raw_evidence_pixels": float(ev_n),
        "final_solid_pixels": float(np.count_nonzero(solid)),
        "largest_missing_region_ratio": 0.0,
        "regional_structure_loss_score": 0.0,
        "lost_cell_frac": 0.0,
        "spatial_grid": float(grid),
        "large_contiguous_foreground_loss": 0.0,
        "raw_bbox": "",
        "final_bbox": "",
    }
    if bbox is None or ev_n < 120:
        stats["foreground_survival_score"] = 50.0
        return stats

    y0, y1, x0, x1 = bbox
    stats["raw_bbox"] = f"{y0}:{y1}x{x0}:{x1}"
    fb = _bbox_from_mask(solid, margin=0.0)
    if fb is not None:
        stats["final_bbox"] = f"{fb[0]}:{fb[1]}x{fb[2]}:{fb[3]}"

    # Coarse canonical grid over product bbox (aspect preserved by cell sampling)
    gy = np.linspace(y0, y1, grid + 1).astype(int)
    gx = np.linspace(x0, x1, grid + 1).astype(int)
    raw_occ = np.zeros((grid, grid), dtype=np.float32)
    fin_occ = np.zeros((grid, grid), dtype=np.float32)
    raw_edge = np.zeros((grid, grid), dtype=np.float32)
    lost = np.zeros((grid, grid), dtype=bool)

    for i in range(grid):
        for j in range(grid):
            ys, ye = gy[i], max(gy[i] + 1, gy[i + 1])
            xs, xe = gx[j], max(gx[j] + 1, gx[j + 1])
            ev_c = evidence[ys:ye, xs:xe]
            sol_c = solid[ys:ye, xs:xe]
            ed_c = edge[ys:ye, xs:xe]
            if ev_c.size == 0:
                continue
            r_frac = float(ev_c.mean())
            f_frac = float(sol_c.mean())
            e_frac = float((ed_c >= 8.0).mean()) if ed_c.size else 0.0
            raw_occ[i, j] = r_frac
            fin_occ[i, j] = f_frac
            raw_edge[i, j] = e_frac
            # Strong RAW product cell with near-background FINAL → lost
            if r_frac >= 0.32 and f_frac <= 0.10 and e_frac >= 0.04:
                lost[i, j] = True
            elif r_frac >= 0.45 and f_frac <= 0.08:
                lost[i, j] = True

    raw_cells = raw_occ >= 0.28
    raw_cell_n = int(np.count_nonzero(raw_cells))
    lost_n = int(np.count_nonzero(lost))
    lost_frac = float(lost_n / max(1, raw_cell_n))
    stats["lost_cell_frac"] = lost_frac

    # Largest contiguous lost block (8-connectivity)
    if lost.any():
        labeled, nlab = ndimage.label(lost, structure=np.ones((3, 3), dtype=bool))
        sizes = ndimage.sum(lost, labeled, index=np.arange(1, nlab + 1)) if nlab else []
        largest = float(np.max(sizes)) if len(sizes) else 0.0
    else:
        largest = 0.0
    largest_ratio = float(largest / max(1, raw_cell_n))
    stats["largest_missing_region_ratio"] = largest_ratio

    # Regional structure loss: mean shortfall on cells that had RAW evidence
    if raw_cells.any():
        shortfall = np.clip(raw_occ[raw_cells] - fin_occ[raw_cells], 0.0, 1.0)
        # Emphasize worst quartile (do not average away a destroyed half)
        q = float(np.percentile(shortfall, 75))
        mean_sf = float(shortfall.mean())
        regional = 100.0 * (0.45 * mean_sf + 0.55 * q)
    else:
        regional = 0.0
    stats["regional_structure_loss_score"] = float(min(100.0, regional))
    stats["foreground_survival_score"] = float(
        max(0.0, min(100.0, 100.0 * survival * (1.0 - 0.55 * largest_ratio)))
    )

    # Catastrophic contiguous loss — calibrated for real partial wipe cases
    # while ignoring tiny edge fringes (ratio ~0.03).
    large = (
        largest_ratio >= 0.18
        and lost_n >= 4
        and wipe_of_evidence >= 0.12
        and survival <= 0.88
    ) or (
        largest_ratio >= 0.28
        and lost_n >= 6
        and survival <= 0.92
    ) or (
        lost_frac >= 0.30
        and largest_ratio >= 0.15
        and wipe_of_evidence >= 0.18
    )
    stats["large_contiguous_foreground_loss"] = 1.0 if large else 0.0
    stats["n_lost_cells"] = float(lost_n)
    stats["n_raw_cells"] = float(raw_cell_n)
    return stats
