"""
Independent RAW vs FINAL product-integrity metrics.

Does NOT trust the processing mask alone. A bad mask that already erased
light/transparent product areas would otherwise under-report structure loss.

Metrics (0–100 scores, higher = better):
  structure_preservation_score
  detail_retention_score
  raw_final_edge_consistency_score
  foreground_overexposure_score
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .qc_config import QCConfig, get_qc_config


def _luma(rgb: np.ndarray) -> np.ndarray:
    r = rgb[:, :, 0].astype(np.float32)
    g = rgb[:, :, 1].astype(np.float32)
    b = rgb[:, :, 2].astype(np.float32)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _sobel(lum: np.ndarray) -> np.ndarray:
    x = np.pad(lum.astype(np.float32), 1, mode="edge")
    gx = (x[1:-1, 2:] - x[1:-1, :-2]) * 0.5
    gy = (x[2:, 1:-1] - x[:-2, 1:-1]) * 0.5
    return np.sqrt(gx * gx + gy * gy)


def _local_std(lum: np.ndarray, win: int = 5) -> np.ndarray:
    from scipy import ndimage

    mean = ndimage.uniform_filter(lum.astype(np.float32), size=win, mode="nearest")
    mean_sq = ndimage.uniform_filter(lum.astype(np.float32) ** 2, size=win, mode="nearest")
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def estimate_raw_product_prior(raw_rgb: np.ndarray) -> np.ndarray:
    """
    Mask-independent product estimate from RAW only.

    Border ring ≈ background; product = interior content that differs from
    border chroma/luma OR has edge/texture structure.
    """
    from scipy import ndimage

    h, w = raw_rgb.shape[:2]
    lum = _luma(raw_rgb)
    edge = _sobel(lum)
    tex = _local_std(lum, win=5)

    border = np.zeros((h, w), dtype=bool)
    m = max(8, int(0.06 * min(h, w)))
    border[:m, :] = True
    border[-m:, :] = True
    border[:, :m] = True
    border[:, -m:] = True

    bg_lum = float(np.median(lum[border])) if border.any() else 220.0
    bg_std = float(np.std(lum[border])) if border.any() else 15.0
    # Distance from background luminance
    d_lum = np.abs(lum - bg_lum)
    # Chroma vs mean border color
    bg_col = raw_rgb[border].astype(np.float32).mean(axis=0) if border.any() else np.array(
        [bg_lum, bg_lum, bg_lum], dtype=np.float32
    )
    d_col = np.linalg.norm(raw_rgb.astype(np.float32) - bg_col[None, None, :], axis=2)

    # Near-white border → product is anything not white-ish with structure
    near_white = (
        (raw_rgb[:, :, 0] >= 248)
        & (raw_rgb[:, :, 1] >= 248)
        & (raw_rgb[:, :, 2] >= 248)
    )
    content = (~near_white) & (
        (d_lum >= max(12.0, bg_std * 1.2))
        | (d_col >= 18.0)
        | (edge >= 8.0)
        | (tex >= 5.0)
    )
    # Drop tiny noise; keep main mass
    content = ndimage.binary_opening(content, iterations=1)
    content = ndimage.binary_closing(content, iterations=2)
    labeled, n = ndimage.label(content)
    if n >= 1:
        sizes = ndimage.sum(content, labeled, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, dtype=bool)
        total = float(sum(sizes)) if len(sizes) else 0.0
        for i, sz in enumerate(sizes, start=1):
            if sz >= max(80.0, 0.002 * h * w) and (total <= 0 or sz / total >= 0.01):
                keep[i] = True
        # Always keep largest
        if len(sizes):
            keep[int(np.argmax(sizes)) + 1] = True
        content = keep[labeled]
    return content


def compute_raw_final_integrity(
    source_rgb: Image.Image,
    rgba_cutout: Image.Image,
    studio_rgb: Image.Image | None = None,
    *,
    cfg: QCConfig | None = None,
    features: Any = None,
) -> dict[str, Any]:
    """
    Compare RAW product content to cutout/FINAL independently of processing mask.

    Returns stats with scores (0–100) and tags for the QC engine.
    Optional `features` (RawFeatureCache) avoids recomputing RAW sobel/tex/prior.
    """
    cfg = cfg or get_qc_config()
    src_img = source_rgb if source_rgb.mode == "RGB" else source_rgb.convert("RGB")
    cut_img = rgba_cutout.convert("RGBA")
    if features is not None:
        src = features.rgb
        lum_s = features.lum
        edge_s = features.edge
        tex_s = features.tex
        prior = features.prior if features.prior is not None else estimate_raw_product_prior(src)
    else:
        src = np.asarray(src_img, dtype=np.uint8)
        lum_s = _luma(src)
        edge_s = _sobel(lum_s)
        tex_s = _local_std(lum_s, win=5)
        prior = estimate_raw_product_prior(src)
    cut = np.asarray(cut_img, dtype=np.uint8)

    warns: list[str] = []
    bads: list[str] = []
    posits: list[str] = []
    triggered: list[str] = []

    stats: dict[str, Any] = {
        "structure_preservation_score": 50.0,
        "detail_retention_score": 50.0,
        "raw_final_edge_consistency_score": 50.0,
        "foreground_overexposure_score": 50.0,
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
    }

    if cut.ndim != 3 or cut.shape[2] < 4:
        bads.append("raw_final_compare_failed")
        stats["bad_count"] = 1.0
        stats["_bads"] = bads
        stats["_warns"] = warns
        stats["_posits"] = posits
        stats["_triggered"] = ["raw_final_shape_mismatch"]
        return stats

    if cut.shape[:2] != src.shape[:2]:
        cut_img = cut_img.resize((src.shape[1], src.shape[0]), Image.Resampling.NEAREST)
        cut = np.asarray(cut_img, dtype=np.uint8)

    alpha = cut[:, :, 3].astype(np.float32)
    rgb_out = cut[:, :, :3]
    lum_o = _luma(rgb_out)
    edge_o = _sobel(lum_o)
    tex_o = _local_std(lum_o, win=5)

    prior_n = int(np.count_nonzero(prior))
    stats["raw_prior_pixels"] = float(prior_n)
    stats["raw_prior_frac"] = float(prior.mean()) if prior.size else 0.0

    if prior_n < 120:
        # Cannot form independent prior — fall back to soft alpha support
        prior = alpha >= 40
        prior_n = int(np.count_nonzero(prior))
        stats["raw_prior_fallback"] = 1.0
        if prior_n < 80:
            bads.append("empty_or_tiny_foreground")
            stats.update(
                {
                    "structure_preservation_score": 8.0,
                    "detail_retention_score": 8.0,
                    "raw_final_edge_consistency_score": 8.0,
                    "foreground_overexposure_score": 8.0,
                    "bad_count": 1.0,
                    "_bads": bads,
                    "_warns": warns,
                    "_posits": posits,
                    "_triggered": ["raw_prior_empty"],
                }
            )
            return stats

    # --- Structure preservation: how much RAW prior survives with real alpha ---
    kept = prior & (alpha >= 80)
    wiped = prior & (alpha < 48)
    kept_frac = float(np.count_nonzero(kept) / max(1, prior_n))
    wipe_frac = float(np.count_nonzero(wiped) / max(1, prior_n))
    stats["prior_kept_frac"] = kept_frac
    stats["prior_wipe_frac"] = wipe_frac

    # Light/midtone prior wipe (classic false-PASS: greys gone, dark remains)
    mid_prior = prior & (lum_s >= 95) & (lum_s <= 220)
    dark_prior = prior & (lum_s < 95)
    mid_n = int(np.count_nonzero(mid_prior))
    dark_n = int(np.count_nonzero(dark_prior))
    mid_wipe = (
        float(np.count_nonzero(mid_prior & (alpha < 48)) / mid_n) if mid_n >= 80 else 0.0
    )
    dark_wipe = (
        float(np.count_nonzero(dark_prior & (alpha < 48)) / dark_n) if dark_n >= 80 else 0.0
    )
    stats["mid_prior_wipe"] = mid_wipe
    stats["dark_prior_wipe"] = dark_wipe
    selective = mid_wipe >= 0.38 and dark_wipe <= 0.25 and mid_n >= 300

    struct_score = 100.0 * kept_frac
    struct_score -= 55.0 * max(0.0, wipe_frac - cfg.raw_wipe_soft)
    if selective:
        struct_score -= 35.0
        triggered.append("selective_midtone_wipe")
        bads.append("product_structure_destroyed")
    if wipe_frac >= cfg.raw_wipe_hard:
        triggered.append("severe_prior_wipe")
        bads.append("product_structure_destroyed")
    elif wipe_frac >= cfg.raw_wipe_soft:
        triggered.append("moderate_prior_wipe")
        warns.append("structure_integrity_warn")

    # --- Detail retention: texture/gradient in kept region vs RAW ---
    if kept.any():
        tex_ratio = float(tex_o[kept].mean() / max(1e-3, tex_s[kept].mean()))
        edge_ratio = float(edge_o[kept].mean() / max(1e-3, edge_s[kept].mean()))
    else:
        tex_ratio, edge_ratio = 0.0, 0.0
    stats["texture_ratio"] = tex_ratio
    stats["edge_energy_ratio"] = edge_ratio
    # Cap ratios (enhance can inflate slightly)
    tex_ratio_c = min(1.15, tex_ratio)
    edge_ratio_c = min(1.15, edge_ratio)
    detail_score = 50.0 * tex_ratio_c + 50.0 * edge_ratio_c
    if tex_ratio < cfg.detail_ratio_hard:
        detail_score = min(detail_score, 28.0)
        triggered.append("detail_collapse")
        bads.append("detail_destroyed")
    elif tex_ratio < cfg.detail_ratio_soft:
        detail_score = min(detail_score, 55.0)
        triggered.append("detail_soft_loss")
        warns.append("detail_retention_warn")

    # --- Edge consistency: strong RAW edges in prior should remain ---
    if prior.any():
        e_thr = max(6.0, float(np.percentile(edge_s[prior], 70)))
    else:
        e_thr = 10.0
    strong_raw = prior & (edge_s >= e_thr)
    strong_n = int(np.count_nonzero(strong_raw))
    if strong_n >= 60:
        # Survives if alpha kept OR final still has edge energy
        survive = strong_raw & ((alpha >= 80) | (edge_o >= e_thr * 0.55))
        edge_keep = float(np.count_nonzero(survive) / strong_n)
    else:
        edge_keep = kept_frac
    stats["strong_edge_keep"] = edge_keep
    edge_cons = 100.0 * edge_keep
    if edge_keep < cfg.edge_keep_hard:
        edge_cons = min(edge_cons, 30.0)
        triggered.append("edge_consistency_hard")
        bads.append("edge_structure_lost")
    elif edge_keep < cfg.edge_keep_soft:
        triggered.append("edge_consistency_soft")
        warns.append("edge_consistency_warn")

    # --- Foreground overexposure / white-out inside product ---
    # Where RAW had non-white product, FINAL (cutout RGB with alpha, or studio)
    # should not become near-pure white with no structure.
    prod_raw = prior & (lum_s < 245)
    # Visible product on cutout
    visible = alpha >= 40
    # White-out: RAW had content, cutout shows near-white RGB with low local contrast
    # OR alpha wiped (counts as destroyed → already in structure)
    out_white = (
        (rgb_out[:, :, 0] >= 248)
        & (rgb_out[:, :, 1] >= 248)
        & (rgb_out[:, :, 2] >= 248)
    )
    flat = tex_o < 3.5
    whiteout = prod_raw & visible & out_white & flat
    whiteout_n = int(np.count_nonzero(whiteout))
    prod_n = int(np.count_nonzero(prod_raw))
    whiteout_frac = whiteout_n / float(max(1, prod_n))
    # Also: regions that were midtone in RAW and are now very bright in kept alpha
    blown = prod_raw & (alpha >= 80) & (lum_s < 200) & (lum_o >= 245) & (tex_o < 5.0)
    blown_frac = float(np.count_nonzero(blown) / max(1, prod_n))
    stats["whiteout_frac"] = whiteout_frac
    stats["blown_frac"] = blown_frac
    overexp_score = 100.0 - 120.0 * max(whiteout_frac, blown_frac * 1.2)
    if max(whiteout_frac, blown_frac) >= cfg.whiteout_hard:
        overexp_score = min(overexp_score, 22.0)
        triggered.append("severe_product_whiteout")
        bads.append("product_whiteout")
    elif max(whiteout_frac, blown_frac) >= cfg.whiteout_soft:
        triggered.append("moderate_product_whiteout")
        warns.append("product_whiteout_warn")

    # Optional studio canvas check: product pixels that are ghost-white
    if studio_rgb is not None:
        try:
            st = np.asarray(
                studio_rgb if studio_rgb.mode == "RGB" else studio_rgb.convert("RGB"),
                dtype=np.uint8,
            )
            st_lum = _luma(st)
            st_prod = ~(
                (st[:, :, 0] >= 250) & (st[:, :, 1] >= 250) & (st[:, :, 2] >= 250)
            )
            st_n = int(np.count_nonzero(st_prod))
            if st_n >= 200:
                st_tex = _local_std(st_lum, win=5)
                ghost = st_prod & (st_lum >= 240) & (st_tex < 4.0)
                ghost_frac = float(np.count_nonzero(ghost) / st_n)
                stats["studio_ghost_frac"] = ghost_frac
                if ghost_frac >= 0.35:
                    overexp_score = min(overexp_score, overexp_score - 25.0)
                    triggered.append("studio_ghost_product")
                    warns.append("product_whiteout_warn")
                if ghost_frac >= 0.55 and st_lum[st_prod].std() < 12.0:
                    overexp_score = min(overexp_score, 20.0)
                    bads.append("product_whiteout")
                    triggered.append("studio_washed_product")
        except Exception:
            pass

    struct_score = _clamp(struct_score)
    detail_score = _clamp(detail_score)
    edge_cons = _clamp(edge_cons)
    overexp_score = _clamp(overexp_score)

    if (
        struct_score >= 85
        and detail_score >= 75
        and edge_cons >= 80
        and overexp_score >= 80
    ):
        posits.append("raw_final_integrity_ok")

    stats["structure_preservation_score"] = struct_score
    stats["detail_retention_score"] = detail_score
    stats["raw_final_edge_consistency_score"] = edge_cons
    stats["foreground_overexposure_score"] = overexp_score
    # Aggregate for convenience
    stats["raw_final_integrity"] = float(
        0.35 * struct_score
        + 0.25 * detail_score
        + 0.20 * edge_cons
        + 0.20 * overexp_score
    )
    stats["warn_count"] = float(len(warns))
    stats["bad_count"] = float(len(bads))
    stats["pos_count"] = float(len(posits))
    stats["_bads"] = bads
    stats["_warns"] = warns
    stats["_posits"] = posits
    stats["_triggered"] = triggered
    return stats
