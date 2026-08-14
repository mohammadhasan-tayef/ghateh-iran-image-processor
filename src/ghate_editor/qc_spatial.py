"""
Spatial RAW↔FINAL product survival (canonical grid).

Detects large contiguous product regions present in RAW that disappear in FINAL,
without relying on a single global average structure score.

Evidence rules (critical):
  - Darkness alone NEVER establishes product membership.
  - Soft contact shadows / gray floor / reflections are excluded.
  - spatial_evidence_confidence (HIGH|MEDIUM|LOW) gates REVIEW authority.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

SpatialConfidence = Literal["HIGH", "MEDIUM", "LOW"]


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


def _border_bg_stats(rgb: np.ndarray, lum: np.ndarray) -> tuple[float, float, np.ndarray]:
    h, w = lum.shape[:2]
    border = np.zeros((h, w), dtype=bool)
    m = max(8, int(0.06 * min(h, w)))
    border[:m, :] = True
    border[-m:, :] = True
    border[:, :m] = True
    border[:, -m:] = True
    bg_lum = float(np.median(lum[border])) if border.any() else 220.0
    bg_std = float(np.std(lum[border])) if border.any() else 15.0
    bg_col = (
        rgb[border].astype(np.float32).mean(axis=0)
        if border.any()
        else np.array([bg_lum, bg_lum, bg_lum], dtype=np.float32)
    )
    return bg_lum, bg_std, bg_col


def estimate_contact_shadow(
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
    alpha: np.ndarray,
) -> np.ndarray:
    """
    Exterior soft contact shadow / dark floor near the cutout — NOT product.

    Darker than local background, low structure, outside solid product core.
    """
    from scipy import ndimage

    soft = alpha >= 40
    solid = alpha >= 80
    if not soft.any():
        return np.zeros_like(soft)

    bg_lum, bg_std, bg_col = _border_bg_stats(rgb, lum)
    d_col = np.linalg.norm(rgb.astype(np.float32) - bg_col[None, None, :], axis=2)
    d_lum = np.abs(lum - bg_lum)

    # Soft halo around product (outside solid core)
    ring = ndimage.binary_dilation(soft, iterations=max(6, int(0.04 * max(soft.shape))))
    exterior = ring & (~solid)

    darker = lum <= (bg_lum - max(8.0, bg_std * 0.35))
    low_struct = (edge < 10.0) & (tex < 6.5)
    weak_chroma = d_col < 28.0
    # Gradual darkness without product texture → shadow/floor
    shadow = exterior & darker & low_struct & weak_chroma & (~_near_white(rgb))
    # Also catch soft penumbra slightly inside dilated support but not solid
    near_soft = ndimage.binary_dilation(soft, iterations=3) & (~solid)
    soft_shadow = near_soft & darker & (edge < 8.0) & (tex < 5.0) & (d_lum < 55.0)
    return shadow | soft_shadow


def build_raw_product_evidence(
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
    alpha: np.ndarray,
    *,
    prior_indep: np.ndarray,
    prior_unreliable: bool,
) -> tuple[np.ndarray, dict[str, Any]]:
    """
    RAW product evidence independent of trusting FINAL alpha alone.

    Darkness alone cannot establish membership. Contact shadows / gray floor
    are explicitly excluded.
    """
    from scipy import ndimage

    soft = alpha >= 40
    solid = alpha >= 80
    nw = _near_white(rgb)
    shadow = estimate_contact_shadow(rgb, lum, edge, tex, alpha)
    meta: dict[str, Any] = {
        "prior_shadow_excluded": float(shadow.mean()) if shadow.size else 0.0,
        "evidence_mode": "independent_prior",
    }

    if (not prior_unreliable) and float(prior_indep.mean()) <= 0.42 and prior_indep.any():
        evidence = prior_indep & (~nw) & (~shadow)
        meta["structured_evidence_frac"] = 1.0
        return evidence, meta

    meta["evidence_mode"] = "structured_near_support"
    if not soft.any():
        evidence = prior_indep & (~nw) & (~shadow)
        meta["structured_evidence_frac"] = 0.0
        return evidence, meta

    ys, xs = np.where(soft)
    bh = max(1, int(ys.max() - ys.min() + 1))
    bw = max(1, int(xs.max() - xs.min() + 1))
    dil_iters = int(min(70, max(14, 0.14 * max(bh, bw) / 3.0)))
    support = ndimage.binary_dilation(soft, iterations=dil_iters)
    bbox = _bbox_from_mask(soft, margin=0.28)
    if bbox is not None:
        y0, y1, x0, x1 = bbox
        roi = np.zeros_like(support)
        roi[y0:y1, x0:x1] = True
        support = support & roi

    bg_lum, bg_std, bg_col = _border_bg_stats(rgb, lum)
    d_col = np.linalg.norm(rgb.astype(np.float32) - bg_col[None, None, :], axis=2)
    d_lum = np.abs(lum - bg_lum)
    bg_like = (d_lum <= max(14.0, bg_std * 1.6)) & (d_col <= 24.0)

    core = solid if solid.any() else soft
    if int(np.count_nonzero(core)) >= 80:
        e_thr = max(7.0, float(np.percentile(edge[core], 52)))
        t_thr = max(5.0, float(np.percentile(tex[core], 50)))
    else:
        e_thr, t_thr = 9.0, 7.0

    # Structure / chroma membership — NEVER luminance-only
    strong_edge = edge >= e_thr
    strong_tex = tex >= t_thr
    chroma_salient = d_col >= 36.0
    # Dark+structured is OK; dark alone is not
    dark_structured = (lum <= (bg_lum - max(18.0, bg_std * 0.7))) & (
        strong_edge | strong_tex | (chroma_salient & (edge >= 6.0))
    )
    structured = strong_edge | strong_tex | chroma_salient | dark_structured

    evidence = (
        support
        & (~nw)
        & (~shadow)
        & (~bg_like)
        & structured
    )
    # Prefer intersection with independent prior or surviving soft when prior exists
    if prior_indep.any() and float(prior_indep.mean()) < 0.85:
        evidence = evidence & (prior_indep | soft)

    # Keep solid product pixels even if weak edge (white panels / flat plastics)
    evidence = evidence | (solid & (~nw) & (~shadow))

    ev_n = max(1, int(np.count_nonzero(evidence)))
    structured_n = int(np.count_nonzero(evidence & (strong_edge | strong_tex | chroma_salient)))
    meta["structured_evidence_frac"] = float(structured_n / ev_n)
    meta["prior_shadow_excluded"] = float(np.count_nonzero(shadow) / max(1, int(shadow.size)))
    return evidence, meta


def classify_spatial_evidence_confidence(
    *,
    prior_unreliable: bool,
    prior_indep: np.ndarray,
    evidence: np.ndarray,
    soft: np.ndarray,
    evidence_meta: dict[str, Any],
) -> SpatialConfidence:
    """
    HIGH: reliable independent prior.
    MEDIUM: unreliable prior but structured evidence tightly tied to cutout.
    LOW: uncertain / shadow-contaminated / weak structure — must not force REVIEW alone.
    """
    mode = str(evidence_meta.get("evidence_mode") or "")
    struct_frac = float(evidence_meta.get("structured_evidence_frac") or 0.0)
    shadow_frac = float(evidence_meta.get("prior_shadow_excluded") or 0.0)
    ev_n = int(np.count_nonzero(evidence))
    soft_n = max(1, int(np.count_nonzero(soft)))
    if ev_n < 120:
        return "LOW"

    overlap = float(np.count_nonzero(evidence & soft) / max(1, ev_n))
    prior_frac = float(prior_indep.mean()) if prior_indep.size else 1.0

    if (
        not prior_unreliable
        and mode == "independent_prior"
        and prior_frac <= 0.42
        and overlap >= 0.35
    ):
        return "HIGH"

    if (
        struct_frac >= 0.55
        and shadow_frac < 0.08
        and overlap >= 0.40
        and ev_n <= soft_n * 2.8
    ):
        return "MEDIUM"

    if struct_frac >= 0.40 and overlap >= 0.50 and ev_n <= soft_n * 2.2:
        return "MEDIUM"

    return "LOW"


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
    large_contiguous_foreground_loss is set only when confidence is HIGH;
    MEDIUM/LOW emit spatial_loss_candidate for optional verifier confirmation.
    """
    from scipy import ndimage

    solid = alpha >= 80
    soft = alpha >= 40
    evidence, ev_meta = build_raw_product_evidence(
        rgb,
        lum,
        edge,
        tex,
        alpha,
        prior_indep=prior_indep,
        prior_unreliable=prior_unreliable,
    )
    conf = classify_spatial_evidence_confidence(
        prior_unreliable=prior_unreliable,
        prior_indep=prior_indep,
        evidence=evidence,
        soft=soft,
        evidence_meta=ev_meta,
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
        "spatial_loss_candidate": 0.0,
        "spatial_evidence_confidence": conf,
        "spatial_verified": 0.0,
        "raw_bbox": "",
        "final_bbox": "",
        "prior_shadow_excluded": float(ev_meta.get("prior_shadow_excluded") or 0.0),
        "structured_evidence_frac": float(ev_meta.get("structured_evidence_frac") or 0.0),
        "evidence_mode": str(ev_meta.get("evidence_mode") or ""),
    }
    if bbox is None or ev_n < 120:
        stats["foreground_survival_score"] = 50.0
        stats["spatial_evidence_confidence"] = "LOW"
        return stats

    y0, y1, x0, x1 = bbox
    stats["raw_bbox"] = f"{y0}:{y1}x{x0}:{x1}"
    fb = _bbox_from_mask(solid, margin=0.0)
    if fb is not None:
        stats["final_bbox"] = f"{fb[0]}:{fb[1]}x{fb[2]}:{fb[3]}"

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
            # Evidence mask is already structure-gated — do not require strong
            # per-cell edges (wiped midtone product can be low-edge).
            if r_frac >= 0.34 and f_frac <= 0.10:
                lost[i, j] = True
            elif r_frac >= 0.28 and f_frac <= 0.08 and e_frac >= 0.03:
                lost[i, j] = True

    raw_cells = raw_occ >= 0.28
    raw_cell_n = int(np.count_nonzero(raw_cells))
    lost_n = int(np.count_nonzero(lost))
    lost_frac = float(lost_n / max(1, raw_cell_n))
    stats["lost_cell_frac"] = lost_frac

    if lost.any():
        labeled, nlab = ndimage.label(lost, structure=np.ones((3, 3), dtype=bool))
        sizes = ndimage.sum(lost, labeled, index=np.arange(1, nlab + 1)) if nlab else []
        largest = float(np.max(sizes)) if len(sizes) else 0.0
    else:
        largest = 0.0
    largest_ratio = float(largest / max(1, raw_cell_n))
    stats["largest_missing_region_ratio"] = largest_ratio

    if raw_cells.any():
        shortfall = np.clip(raw_occ[raw_cells] - fin_occ[raw_cells], 0.0, 1.0)
        q = float(np.percentile(shortfall, 75))
        mean_sf = float(shortfall.mean())
        regional = 100.0 * (0.45 * mean_sf + 0.55 * q)
    else:
        regional = 0.0
    stats["regional_structure_loss_score"] = float(min(100.0, regional))
    stats["foreground_survival_score"] = float(
        max(0.0, min(100.0, 100.0 * survival * (1.0 - 0.55 * largest_ratio)))
    )

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
    ) or (
        # HIGH-confidence evidence with severe pixel wipe even if grid is soft
        conf == "HIGH"
        and survival <= 0.74
        and wipe_of_evidence >= 0.20
        and ev_n >= 400
    )
    stats["spatial_loss_candidate"] = 1.0 if large else 0.0
    # Only HIGH-confidence spatial evidence may independently assert hard loss
    stats["large_contiguous_foreground_loss"] = 1.0 if (large and conf == "HIGH") else 0.0
    stats["n_lost_cells"] = float(lost_n)
    stats["n_raw_cells"] = float(raw_cell_n)
    # Persist lost-grid for verifier (flat row-major)
    stats["_lost_grid"] = lost.astype(np.uint8)
    stats["_evidence"] = evidence
    return stats
