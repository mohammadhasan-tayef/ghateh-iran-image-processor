"""
Independent RAW vs FINAL product-integrity metrics.

Does NOT trust the processing mask alone. A bad mask that already erased
light/transparent product areas would otherwise under-report structure loss.

Metrics (0–100 scores, higher = better):
  structure_preservation_score
  detail_retention_score
  raw_final_edge_consistency_score
  foreground_overexposure_score

IMPORTANT — coordinate space:
  Compare RAW working RGB and cutout RGBA at the SAME HxW (pre-compose).
  Never compare absolute pixels of RAW against the 2000×2000 studio canvas.
  When an independent scene prior is unreliable (busy non-white backgrounds),
  wipe metrics fall back to a mask-anchored structural prior in that same space.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from PIL import Image

from .qc_config import QCConfig, get_qc_config

# Independent prior covering more than this fraction of the frame is treated as
# a scene/background prior (typical of real product photos on floors/tables),
# NOT a product silhouette. Wipe-based destruction tags must not use it as-is.
PRIOR_RELIABLE_MAX_FRAC = 0.42


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


def _keep_top_components(
    content: np.ndarray,
    *,
    max_frac: float = PRIOR_RELIABLE_MAX_FRAC,
    max_components: int = 3,
    min_frac: float = 0.004,
) -> np.ndarray:
    """Keep largest connected components until max_frac of the frame."""
    from scipy import ndimage

    h, w = content.shape[:2]
    labeled, n = ndimage.label(content)
    if n < 1:
        return content
    sizes = ndimage.sum(content, labeled, index=np.arange(1, n + 1))
    order = np.argsort(sizes)[::-1]
    keep = np.zeros(n + 1, dtype=bool)
    acc = 0.0
    frame = float(h * w)
    for idx in order[:max_components]:
        sz = float(sizes[idx])
        if sz < max(80.0, min_frac * frame):
            break
        keep[int(idx) + 1] = True
        acc += sz
        if acc / frame >= max_frac:
            break
    if not keep.any() and len(sizes):
        keep[int(np.argmax(sizes)) + 1] = True
    return keep[labeled]


def estimate_raw_product_prior(
    raw_rgb: np.ndarray,
    *,
    lum: np.ndarray | None = None,
    edge: np.ndarray | None = None,
    tex: np.ndarray | None = None,
) -> np.ndarray:
    """
    Mask-independent product estimate from RAW only.

    Designed for real e-commerce photos (non-white floors/tables). Weak
    edge/texture alone must NOT mark the entire scene as product.
    """
    from scipy import ndimage

    h, w = raw_rgb.shape[:2]
    if lum is None:
        lum = _luma(raw_rgb)
    if edge is None:
        edge = _sobel(lum)
    if tex is None:
        tex = _local_std(lum, win=5)

    border = np.zeros((h, w), dtype=bool)
    m = max(8, int(0.06 * min(h, w)))
    border[:m, :] = True
    border[-m:, :] = True
    border[:, :m] = True
    border[:, -m:] = True

    bg_lum = float(np.median(lum[border])) if border.any() else 220.0
    bg_std = float(np.std(lum[border])) if border.any() else 15.0
    d_lum = np.abs(lum - bg_lum)
    bg_col = (
        raw_rgb[border].astype(np.float32).mean(axis=0)
        if border.any()
        else np.array([bg_lum, bg_lum, bg_lum], dtype=np.float32)
    )
    d_col = np.linalg.norm(raw_rgb.astype(np.float32) - bg_col[None, None, :], axis=2)

    near_white = (
        (raw_rgb[:, :, 0] >= 248)
        & (raw_rgb[:, :, 1] >= 248)
        & (raw_rgb[:, :, 2] >= 248)
    )
    # Pixels that look like the border ring (floor/table continuing inward)
    bg_like = (d_lum <= max(16.0, bg_std * 1.8)) & (d_col <= 26.0)

    # Salient product: clearly darker/brighter OR strongly different chroma.
    # Do NOT use weak edge/tex ORs — those light up entire textured floors.
    dark_salient = lum <= (bg_lum - max(22.0, bg_std * 0.85))
    bright_salient = lum >= (bg_lum + max(28.0, bg_std * 1.1))
    chroma_salient = d_col >= 42.0
    strong_struct = (edge >= 16.0) & (tex >= 7.0) & (d_lum >= 14.0)

    content = (~near_white) & (~bg_like) & (
        dark_salient | bright_salient | chroma_salient | strong_struct
    )
    content = ndimage.binary_opening(content, iterations=2)
    content = ndimage.binary_closing(content, iterations=2)
    content = _keep_top_components(content, max_frac=PRIOR_RELIABLE_MAX_FRAC)
    return content


def mask_anchored_structural_prior(
    alpha: np.ndarray,
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
) -> np.ndarray:
    """
    Product-structure prior anchored to the cutout mask support.

    Detects selective wipe of structured midtones next to surviving cores
    without treating the entire non-white scene as product.
    Same coordinate space as RAW working + cutout RGBA.
    """
    from scipy import ndimage

    soft = alpha >= 40
    soft_n = int(np.count_nonzero(soft))
    h, w = soft.shape[:2]
    if soft_n < 80:
        # Mask collapsed — fall back to compact independent prior only
        return estimate_raw_product_prior(rgb, lum=lum, edge=edge, tex=tex)

    ys, xs = np.where(soft)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    bh, bw = max(1, y1 - y0), max(1, x1 - x0)
    dil_iters = int(min(70, max(14, 0.12 * max(bh, bw) / 3.0)))
    support = ndimage.binary_dilation(soft, iterations=dil_iters)
    # Cap support to generous bbox around product (avoid full-frame floor)
    margin = int(0.22 * max(bh, bw))
    roi = np.zeros_like(support)
    yy0, yy1 = max(0, y0 - margin), min(h, y1 + margin)
    xx0, xx1 = max(0, x0 - margin), min(w, x1 + margin)
    roi[yy0:yy1, xx0:xx1] = True
    support = support & roi

    near_white = (
        (rgb[:, :, 0] >= 248) & (rgb[:, :, 1] >= 248) & (rgb[:, :, 2] >= 248)
    )
    core = soft & roi
    if int(np.count_nonzero(core)) >= 80:
        e_thr = float(np.percentile(edge[core], 50))
        t_thr = float(np.percentile(tex[core], 48))
    else:
        e_thr, t_thr = 8.0, 6.0
    e_thr = max(5.5, e_thr)
    t_thr = max(4.0, t_thr)

    prior = support & (~near_white) & ((edge >= e_thr) | (tex >= t_thr) | (alpha >= 80))
    return prior


def canonicalize_product_roi(
    rgb: np.ndarray,
    mask: np.ndarray,
    *,
    out_size: int = 256,
) -> np.ndarray:
    """
    Aspect-preserving product ROI → fixed canvas (for transform-invariance checks).
    mask: bool or alpha uint8.
    """
    if mask.dtype != bool:
        m = mask >= 40
    else:
        m = mask
    if not m.any():
        return np.zeros((out_size, out_size, 3), dtype=np.uint8)
    ys, xs = np.where(m)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    crop = rgb[y0:y1, x0:x1]
    ch, cw = crop.shape[:2]
    scale = float(out_size) / float(max(ch, cw))
    nh, nw = max(1, int(round(ch * scale))), max(1, int(round(cw * scale)))
    img = Image.fromarray(crop, mode="RGB").resize((nw, nh), Image.Resampling.BILINEAR)
    canvas = Image.new("RGB", (out_size, out_size), (255, 255, 255))
    canvas.paste(img, ((out_size - nw) // 2, (out_size - nh) // 2))
    return np.asarray(canvas, dtype=np.uint8)


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
    Optional `features` (RawFeatureCache) avoids recomputing RAW sobel/tex.
    Cache must match cutout HxW; otherwise features are ignored.
    """
    cfg = cfg or get_qc_config()
    src_img = source_rgb if source_rgb.mode == "RGB" else source_rgb.convert("RGB")
    cut_img = rgba_cutout.convert("RGBA")
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

    # Resolve RAW features; reject stale/mismatched cache (wrong HxW / stage)
    use_feats = False
    if features is not None:
        fr = getattr(features, "rgb", None)
        if (
            fr is not None
            and getattr(fr, "shape", None) is not None
            and fr.shape[:2] == cut.shape[:2]
        ):
            use_feats = True
        else:
            triggered.append("raw_feature_cache_mismatch_ignored")

    if use_feats:
        src = features.rgb
        lum_s = features.lum
        edge_s = features.edge
        tex_s = features.tex
        prior_indep = (
            features.prior
            if features.prior is not None
            else estimate_raw_product_prior(src, lum=lum_s, edge=edge_s, tex=tex_s)
        )
        if prior_indep.shape[:2] != src.shape[:2]:
            prior_indep = estimate_raw_product_prior(
                src, lum=lum_s, edge=edge_s, tex=tex_s
            )
            triggered.append("raw_prior_cache_shape_rebuilt")
    else:
        if cut.shape[:2] != (src_img.size[1], src_img.size[0]):
            cut_img = cut_img.resize(src_img.size, Image.Resampling.NEAREST)
            cut = np.asarray(cut_img, dtype=np.uint8)
        src = np.asarray(src_img, dtype=np.uint8)
        if cut.shape[:2] != src.shape[:2]:
            cut_img = cut_img.resize((src.shape[1], src.shape[0]), Image.Resampling.NEAREST)
            cut = np.asarray(cut_img, dtype=np.uint8)
        lum_s = _luma(src)
        edge_s = _sobel(lum_s)
        tex_s = _local_std(lum_s, win=5)
        prior_indep = estimate_raw_product_prior(src, lum=lum_s, edge=edge_s, tex=tex_s)

    alpha = cut[:, :, 3].astype(np.float32)
    rgb_out = cut[:, :, :3]
    lum_o = _luma(rgb_out)
    edge_o = _sobel(lum_o)
    tex_o = _local_std(lum_o, win=5)

    indep_frac = float(prior_indep.mean()) if prior_indep.size else 0.0
    stats["raw_prior_frac_independent"] = indep_frac
    stats["raw_prior_pixels_independent"] = float(np.count_nonzero(prior_indep))

    prior_unreliable = indep_frac > PRIOR_RELIABLE_MAX_FRAC
    if prior_unreliable:
        # Busy real-world backgrounds: do not treat full scene as product.
        prior = mask_anchored_structural_prior(alpha, src, lum_s, edge_s, tex_s)
        stats["prior_unreliable"] = 1.0
        stats["prior_mode"] = "mask_anchored"
        triggered.append("prior_unreliable_mask_anchored")
    else:
        prior = prior_indep
        stats["prior_unreliable"] = 0.0
        stats["prior_mode"] = "independent"

    prior_n = int(np.count_nonzero(prior))
    stats["raw_prior_pixels"] = float(prior_n)
    stats["raw_prior_frac"] = float(prior.mean()) if prior.size else 0.0

    if prior_n < 120:
        # Cannot form prior — fall back to soft alpha support
        prior = alpha >= 40
        prior_n = int(np.count_nonzero(prior))
        stats["raw_prior_fallback"] = 1.0
        stats["prior_mode"] = "alpha_fallback"
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
                    "_triggered": triggered + ["raw_prior_empty"],
                }
            )
            return stats

    # --- Structure preservation: how much product prior survives with real alpha ---
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
    wipe_hard = wipe_frac >= cfg.raw_wipe_hard
    wipe_soft = wipe_frac >= cfg.raw_wipe_soft

    struct_score = 100.0 * kept_frac
    struct_score -= 55.0 * max(0.0, wipe_frac - cfg.raw_wipe_soft)
    if selective:
        struct_score -= 35.0
        triggered.append("selective_midtone_wipe")
    if wipe_hard:
        triggered.append("severe_prior_wipe")
    elif wipe_soft:
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
        # RGB-under-transparent still has edges — do NOT count that as survival.
        alpha_edge_keep = float(np.count_nonzero(strong_raw & (alpha >= 80)) / strong_n)
        # Soft visual continuity (for scoring only)
        survive_vis = strong_raw & ((alpha >= 80) | (edge_o >= e_thr * 0.55))
        edge_keep_vis = float(np.count_nonzero(survive_vis) / strong_n)
    else:
        alpha_edge_keep = kept_frac
        edge_keep_vis = kept_frac
    stats["strong_edge_keep"] = alpha_edge_keep
    stats["strong_edge_keep_visual"] = edge_keep_vis
    # Destruction-relevant edge score uses alpha support (geometry), not RGB ghosts
    edge_cons = 100.0 * alpha_edge_keep
    if alpha_edge_keep < cfg.edge_keep_hard:
        edge_cons = min(edge_cons, 30.0)
        triggered.append("edge_consistency_hard")
        bads.append("edge_structure_lost")
    elif alpha_edge_keep < cfg.edge_keep_soft:
        triggered.append("edge_consistency_soft")
        warns.append("edge_consistency_warn")

    # --- Foreground overexposure / white-out inside product ---
    prod_raw = prior & (lum_s < 245)
    visible = alpha >= 40
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
    # Studio is a DIFFERENT coordinate space — only use for washout heuristics,
    # never for pixel-aligned wipe vs RAW.
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

    # --- Corroborated destruction only (never a single wipe heuristic) ---
    # Real destruction needs ≥2 independent integrity signals.
    # Counter-example that must NOT tag destroy: wipe high from bloated scene
    # prior while alpha-edge / detail / overexposure remain excellent.
    wipe_candidate = bool(selective or wipe_hard)
    signals = 0
    signal_names: list[str] = []
    if struct_score < 50.0:
        signals += 1
        signal_names.append("structure_low")
    if alpha_edge_keep < cfg.edge_keep_soft:
        signals += 1
        signal_names.append("alpha_edge_loss")
    if detail_score < 55.0 or "detail_destroyed" in bads:
        signals += 1
        signal_names.append("detail_loss")
    if overexp_score < 55.0 or "product_whiteout" in bads:
        signals += 1
        signal_names.append("whiteout")
    if wipe_candidate and kept_frac < 0.45 and not prior_unreliable:
        signals += 1
        signal_names.append("reliable_prior_wipe")
    if selective and mid_wipe >= 0.50 and kept_frac < 0.55 and alpha_edge_keep < 0.70:
        signals += 1
        signal_names.append("selective_alpha_edge")
    stats["destruction_signal_count"] = float(signals)
    stats["destruction_signals"] = ",".join(signal_names)

    if wipe_candidate and signals >= 2:
        bads.append("product_structure_destroyed")
        triggered.append("destruction_corroborated")
    elif wipe_candidate:
        # Soft only — do not force REVIEW / instant reject
        warns.append("structure_integrity_warn")
        triggered.append("destruction_uncorroborated_demoted")
        # If other integrity channels are healthy, repair contradicted structure score
        if (
            edge_cons >= 80.0
            and detail_score >= 80.0
            and overexp_score >= 80.0
        ) or prior_unreliable:
            struct_score = max(struct_score, min(88.0, 100.0 * max(kept_frac, 0.55)))
            triggered.append("structure_score_repaired_contradiction")
            struct_score = _clamp(struct_score)

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
