"""
Weighted, explainable QC decision engine (v3 — RAW-aware).

Philosophy:
  Is the PRODUCT seriously damaged (RAW vs FINAL)? → REVIEW
  Is segmentation / integrity uncertain?           → SECOND_PASS
  Is background seriously dirty?                   → SECOND_PASS / REVIEW
  Otherwise commercially usable?                   → PASS

Product integrity from independent RAW↔FINAL comparison dominates.
Clean white background alone can NEVER pass a destroyed product.
Composition / size / mild shadow are aesthetic-only.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .qc_config import QCConfig, get_qc_config

QCDecision = Literal["pass", "second_pass", "review"]

_ZONE_MAP = {
    "pass": "high_good",
    "second_pass": "uncertain",
    "review": "high_bad",
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(max(lo, min(hi, x)))


def _lerp_penalty(value: float, soft: float, hard: float, max_pen: float) -> float:
    if value <= soft:
        return 0.0
    if value >= hard:
        return max_pen
    t = (value - soft) / max(1e-6, hard - soft)
    return max_pen * t


def _collect_tags(
    *blocks: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    bads: list[str] = []
    warns: list[str] = []
    posits: list[str] = []
    for st in blocks:
        if not st:
            continue
        bads.extend(list(st.get("_bads") or []))
        warns.extend(list(st.get("_warns") or []))
        posits.extend(list(st.get("_posits") or []))
    bads = list(dict.fromkeys(bads))
    warns = list(dict.fromkeys(w for w in warns if w not in bads))
    posits = list(dict.fromkeys(posits))
    return bads, warns, posits


def _f(stats: dict[str, Any] | None, key: str, default: float = 0.0) -> float:
    if not stats:
        return default
    try:
        return float(stats.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def detect_qc_profile(
    mask: dict[str, Any] | None,
    studio: dict[str, Any] | None,
    posits: list[str],
    bads: list[str],
    warns: list[str],
) -> str:
    """Lightweight profile label for diagnostics / rule modulation."""
    n_sig = int(_f(mask, "n_significant_components", 1))
    if "multi_object_ok" in posits or (
        n_sig >= 2 and "foreground_fragmented" not in bads
    ):
        if n_sig >= 2:
            return "MULTI_OBJECT"
    if "legitimate_holes" in posits or _f(mask, "hole_frac") >= 0.08:
        if "dark_on_white" in posits or "dark_high_contrast" in posits:
            return "DARK_OBJECT_WITH_HOLES"
        return "OPEN_FRAME"
    if "dark_on_white" in posits or "dark_high_contrast" in posits:
        return "DARK_OBJECT"
    mean = _f(studio, "product_mean", 128.0)
    lg = _f(studio, "light_grey_frac")
    if mean >= 175.0 or lg >= 0.45:
        return "LIGHT_OBJECT_ON_WHITE"
    if "foggy_soft_mask" in warns or "foggy_alpha_edges" in warns:
        return "TRANSLUCENT_OR_REFLECTIVE"
    return "NORMAL"


def is_legitimate_multi_object(mask: dict[str, Any] | None, cfg: QCConfig) -> bool:
    """True when several sizable components look like a kit, not spray noise."""
    n_sig = _f(mask, "n_significant_components", 1.0)
    main = _f(mask, "main_component_frac", 1.0)
    n_all = _f(mask, "n_solid_components", n_sig)
    if n_sig < cfg.multi_object_min_components:
        return False
    if n_sig > cfg.multi_object_max_components:
        return False
    # Spray: many components but none dominate AND too many tiny vs significant
    if n_all >= 20 and n_sig <= 2:
        return False
    # Kit: 2–12 significant pieces, main not necessarily huge
    if n_sig <= cfg.multi_object_max_components and main >= cfg.multi_object_min_comp_frac:
        return True
    return False


def score_mask_confidence(
    mask: dict[str, Any] | None,
    bads: list[str],
    warns: list[str],
    posits: list[str],
    cfg: QCConfig,
) -> tuple[float, list[str]]:
    triggered: list[str] = []
    s = 84.0
    soft = _f(mask, "soft_coverage")
    solid_of = _f(mask, "solid_of_soft", 0.5)
    fog = _f(mask, "fog_ratio")
    mean_a = _f(mask, "mean_alpha_soft", 128.0)
    roi_fill = _f(mask, "roi_fill", 0.5)

    if soft < 0.008:
        return 5.0, ["mask_empty_or_tiny"]
    if soft > 0.55:
        s -= 28.0
        triggered.append("mask_near_full_frame")
    elif soft > 0.45:
        s -= 10.0
        triggered.append("mask_large_coverage")

    s -= _lerp_penalty(fog, 0.50, 0.75, 24.0)
    if fog >= 0.55:
        triggered.append("foggy_mask")
    s -= _lerp_penalty(1.0 - solid_of, 0.50, 0.88, 26.0)
    s -= _lerp_penalty(max(0.0, 110.0 - mean_a), 0.0, 55.0, 18.0)
    # Sparse ROI is soft only (small products / multi-object kits)
    s -= _lerp_penalty(max(0.0, 0.15 - roi_fill), 0.0, 0.12, 12.0)

    if "strong_main_component" in posits or "multi_object_ok" in posits:
        s += 6.0
    if "opaque_core" in posits:
        s += 5.0
    if "plausible_coverage" in posits:
        s += 3.0
    if "legitimate_holes" in posits:
        s += 4.0
        triggered.append("holes_preserved_ok")

    multi = is_legitimate_multi_object(mask, cfg) or "multi_object_ok" in posits
    if "foreground_fragmented" in bads and multi:
        s -= 4.0
        triggered.append("multi_object_soft_note")
    elif "foreground_fragmented" in bads:
        s -= 18.0
        triggered.append("mask_fragmented_bad")
    elif "foreground_fragmented" in warns:
        s -= 5.0
        triggered.append("mask_fragmented_soft")

    return _clamp(s), triggered


def score_edge_integrity(
    cutout: dict[str, Any] | None,
    studio: dict[str, Any] | None,
    bads: list[str],
    warns: list[str],
) -> tuple[float, list[str]]:
    triggered: list[str] = []
    s = 86.0
    fog_fg = _f(cutout, "fog_of_fg")
    edge_haze = _f(studio, "edge_inner_light_frac", 0.0)

    s -= _lerp_penalty(fog_fg, 0.55, 0.80, 28.0)
    if fog_fg >= 0.60:
        triggered.append("soft_alpha_edges")
    s -= _lerp_penalty(edge_haze, 0.50, 0.75, 22.0)
    if edge_haze >= 0.55:
        triggered.append("edge_haze")

    if "foggy_alpha_edges" in bads:
        s -= 16.0
        triggered.append("foggy_alpha_edges_bad")
    elif "foggy_alpha_edges" in warns:
        s -= 6.0
        triggered.append("foggy_alpha_edges_soft")
    return _clamp(s), triggered


def score_object_completeness(
    structure: dict[str, Any] | None,
    mask: dict[str, Any] | None,
    bads: list[str],
    warns: list[str],
    posits: list[str],
    cfg: QCConfig,
    raw_final: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    triggered: list[str] = []
    s = 90.0
    sl = _f(structure, "structure_loss")
    ed = _f(structure, "edge_drop")
    mid = _f(structure, "midtone_loss")
    collapsed = _f(structure, "collapsed_regions")
    rf = raw_final or {}
    survival = _f(rf, "foreground_survival_score", 100.0)
    largest_miss = _f(rf, "largest_missing_region_ratio")
    regional = _f(rf, "regional_structure_loss_score")

    s -= _lerp_penalty(sl, cfg.struct_loss_soft, cfg.struct_loss_hard, 42.0)
    if sl >= cfg.struct_loss_soft:
        triggered.append(
            "structure_loss_soft" if sl < cfg.struct_loss_hard else "structure_loss_hard"
        )
    s -= _lerp_penalty(ed, cfg.edge_drop_soft, cfg.edge_drop_hard, 28.0)
    if ed >= cfg.edge_drop_soft:
        triggered.append("edge_drop")
    s -= _lerp_penalty(mid, 0.40, 0.65, 18.0)
    if collapsed >= 3:
        s -= min(18.0, collapsed * 5.0)
        triggered.append("shape_collapse")

    # RAW-aware spatial completeness (surviving regions must not hide missing halves)
    if survival < 95.0:
        s -= _lerp_penalty(max(0.0, 88.0 - survival), 0.0, 40.0, 36.0)
    if largest_miss >= 0.10:
        s -= min(40.0, largest_miss * 120.0)
        triggered.append("largest_missing_region")
    if regional >= 25.0:
        s -= min(28.0, regional * 0.45)
        triggered.append("regional_completeness_loss")
    if "large_contiguous_foreground_loss" in bads:
        s = min(s, 22.0)
        triggered.append("spatial_loss_completeness_cap")

    if "catastrophic_structure_loss" in bads and sl >= cfg.instant_struct_loss:
        s = min(s, 28.0)
        triggered.append("catastrophic_structure_loss")
    elif "catastrophic_structure_loss" in bads:
        s -= 22.0
        triggered.append("structure_bad_softened")
    elif "catastrophic_structure_loss" in warns:
        # Soft only — do NOT hard-cap final score
        s -= 8.0
        triggered.append("structure_warn")

    if "structure_preserved" in posits:
        s += 8.0
    if "edges_retained" in posits:
        s += 5.0
    if "legitimate_holes" in posits:
        s += 3.0
    main = _f(mask, "main_component_frac", 0.7)
    if main >= 0.70 or "multi_object_ok" in posits:
        s += 3.0
    return _clamp(s), triggered


def score_background_purity(
    studio: dict[str, Any] | None,
    bads: list[str],
    warns: list[str],
    cfg: QCConfig,
) -> tuple[float, list[str]]:
    """
    Prefer mask-aware outer-background dirty fraction when present.
    Falls back to light_grey ghost metric inside product region.
    """
    triggered: list[str] = []
    s = 92.0
    dirty = _f(studio, "bg_dirty_frac", -1.0)
    if dirty >= 0.0:
        s -= _lerp_penalty(dirty, cfg.bg_dirty_soft, cfg.bg_dirty_hard, 40.0)
        if dirty >= cfg.bg_dirty_soft:
            triggered.append("mask_aware_bg_dirty")
    else:
        lg = _f(studio, "light_grey_frac")
        s -= _lerp_penalty(lg, 0.80, 0.95, 30.0)
        if lg >= 0.85:
            triggered.append("ghost_light_regions")

    if "final_washed_out" in bads or "product_faded" in bads:
        s = min(s, 22.0)
        triggered.append("washed_out_or_faded")
    elif "product_faded" in warns:
        s -= 10.0
        triggered.append("mild_fade")
    return _clamp(s), triggered


def score_shadow(
    studio: dict[str, Any] | None,
    cfg: QCConfig,
) -> tuple[float, list[str]]:
    triggered: list[str] = []
    s = 94.0
    sh = _f(studio, "bg_shadow_frac", -1.0)
    if sh < 0.0:
        return s, triggered
    if cfg.mild_shadow_ok and sh < cfg.shadow_soft:
        return s, triggered
    s -= _lerp_penalty(sh, cfg.shadow_soft, cfg.shadow_hard, 35.0)
    if sh >= cfg.shadow_hard:
        triggered.append("large_bg_shadow")
    elif sh >= cfg.shadow_soft:
        triggered.append("mild_bg_shadow")
    return _clamp(s), triggered


def score_composition(
    mask: dict[str, Any] | None,
    studio: dict[str, Any] | None,
    cfg: QCConfig,
) -> tuple[float, list[str]]:
    """Aesthetic only — never decisive alone."""
    triggered: list[str] = []
    s = 90.0
    roi_fill = _f(mask, "roi_fill", _f(studio, "studio_roi_fill", 0.5))
    bbox_frac = _f(mask, "bbox_frac", _f(studio, "product_frac", 0.15))
    aspect = _f(mask, "bbox_aspect", 1.5)

    if roi_fill < cfg.size_fill_soft_lo:
        s -= _lerp_penalty(cfg.size_fill_soft_lo - roi_fill, 0.0, 0.12, 15.0)
        triggered.append("product_sparse_in_roi")
    if roi_fill > cfg.size_fill_soft_hi:
        s -= 6.0
        triggered.append("product_fills_roi_tight")
    # Tiny on canvas — soft only (never REVIEW alone)
    if bbox_frac < 0.015:
        s -= 12.0
        triggered.append("tiny_on_canvas")
    elif bbox_frac < 0.03:
        s -= 4.0
    if aspect > 16.0:
        s -= 10.0
        triggered.append("extreme_aspect")
    return _clamp(s), triggered


def score_color_preservation(
    cutout: dict[str, Any] | None,
    studio: dict[str, Any] | None,
    posits: list[str],
) -> tuple[float, list[str]]:
    triggered: list[str] = []
    s = 88.0
    nw = _f(cutout, "near_white_in_solid")
    vis = _f(cutout, "visibility", _f(studio, "product_visibility", 40.0))
    std = _f(cutout, "solid_std", _f(studio, "product_std", 20.0))

    s -= _lerp_penalty(nw, 0.75, 0.96, 38.0)
    if nw >= 0.80:
        triggered.append("solid_near_white")
    if vis < 10.0:
        s -= 32.0
        triggered.append("low_visibility")
    elif vis < 16.0:
        s -= 10.0
    if std < 5.0 and vis < 22.0:
        s -= 14.0
        triggered.append("flat_washed_product")
    if "dark_high_contrast" in posits or "dark_on_white" in posits:
        s += 6.0
    if "strong_visibility" in posits:
        s += 4.0
    return _clamp(s), triggered


def score_sharpness_exposure_halo(
    cutout: dict[str, Any] | None,
    studio: dict[str, Any] | None,
    warns: list[str],
    bads: list[str],
    profile: str,
) -> tuple[float, float, float, list[str]]:
    triggered: list[str] = []
    std = _f(cutout, "solid_std", _f(studio, "product_std", 15.0))
    sharp = _clamp(55.0 + min(40.0, std * 1.2))
    if std < 8.0:
        sharp -= 12.0
        triggered.append("low_texture_std")

    vis = _f(cutout, "visibility", _f(studio, "product_visibility", 40.0))
    mean = _f(studio, "product_mean", 128.0)
    # Profile-aware exposure target
    if profile.startswith("DARK"):
        target = 70.0
    elif profile.startswith("LIGHT"):
        target = 175.0
    else:
        target = 120.0
    exposure = _clamp(100.0 - abs(mean - target) * 0.22)
    if vis < 12.0:
        exposure = min(exposure, 42.0)
        triggered.append("underexposed_or_ghost")
    if mean >= 248.0 and profile.startswith("LIGHT") is False:
        exposure = min(exposure, 40.0)
        triggered.append("overexposed_product")

    fog = _f(cutout, "fog_of_fg")
    edge_mean = _f(cutout, "edge_band_mean_alpha", 100.0)
    halo = _clamp(93.0 - _lerp_penalty(fog, 0.50, 0.75, 32.0))
    if edge_mean < 55.0 and fog > 0.45:
        halo -= 8.0
        triggered.append("halo_ring")
    if "foggy_alpha_edges" in bads:
        halo = min(halo, 48.0)

    return _clamp(sharp), _clamp(exposure), _clamp(halo), triggered


def check_instant_reject(
    bads: list[str],
    structure: dict[str, Any] | None,
    cfg: QCConfig,
    raw_final: dict[str, Any] | None = None,
) -> str | None:
    sl = _f(structure, "structure_loss")
    for r in cfg.instant_reject_reasons:
        if r in bads:
            return r
    if "catastrophic_structure_loss" in bads and sl >= cfg.instant_struct_loss:
        return "catastrophic_structure_loss"
    if "empty_mask" in bads or "foreground_too_small" in bads:
        return "empty_or_tiny_foreground"
    # Independent integrity collapse — only when whiteout/detail truly collapse
    integ = _f(raw_final, "raw_final_integrity", 100.0)
    if raw_final and integ <= cfg.instant_integrity_max:
        rf_bads = list(raw_final.get("_bads") or [])
        if any(
            t in rf_bads
            for t in ("product_whiteout", "detail_destroyed", "empty_or_tiny_foreground")
        ):
            return "raw_final_integrity_collapse"
    return None


def destruction_corroborated(
    rf: dict[str, Any] | None,
    structure: dict[str, Any] | None,
    bads: list[str],
) -> bool:
    """
    True only when ≥2 independent integrity signals agree the product is destroyed.

    A lone wipe / structure heuristic with excellent edge/detail/overexposure
    is treated as a false positive (seen on real dark products on busy floors).
    """
    rf = rf or {}
    structure = structure or {}
    struct_p = _f(rf, "structure_preservation_score", 75.0)
    detail_p = _f(rf, "detail_retention_score", 75.0)
    edge_rf = _f(rf, "raw_final_edge_consistency_score", 75.0)
    overexp = _f(rf, "foreground_overexposure_score", 80.0)
    alpha_edge = _f(rf, "strong_edge_keep", edge_rf / 100.0)
    wipe = _f(rf, "prior_wipe_frac")
    kept = _f(rf, "prior_kept_frac", 1.0)
    unreliable = _f(rf, "prior_unreliable") >= 0.5
    whiteout = _f(rf, "whiteout_frac")
    sl = _f(structure, "structure_loss")
    mid_loss = _f(structure, "midtone_loss")
    edge_drop = _f(structure, "edge_drop")

    signals = 0
    if struct_p < 50.0:
        signals += 1
    if edge_rf < 55.0 or alpha_edge < 0.55:
        signals += 1
    if detail_p < 55.0 or "detail_destroyed" in bads:
        signals += 1
    if overexp < 55.0 or whiteout >= 0.20 or "product_whiteout" in bads:
        signals += 1
    if sl >= 0.35 or mid_loss >= 0.40 or edge_drop >= 0.40:
        signals += 1
    if (
        wipe >= 0.38
        and kept < 0.45
        and not unreliable
        and (edge_rf < 70.0 or alpha_edge < 0.65 or sl >= 0.28)
    ):
        signals += 1
    if _f(rf, "large_contiguous_foreground_loss") >= 0.5:
        signals += 1
    if _f(rf, "largest_missing_region_ratio") >= 0.18 and _f(
        rf, "foreground_survival_score", 100.0
    ) < 78.0:
        signals += 1

    # Explicit pre-confirmed tag from compute_raw_final_integrity
    if _f(rf, "destruction_signal_count") >= 2:
        return True
    return signals >= 2


def sanitize_destruction_and_fragmentation(
    bads: list[str],
    warns: list[str],
    posits: list[str],
    rf: dict[str, Any],
    structure: dict[str, Any] | None,
    mask_stats: dict[str, Any] | None,
    cfg: QCConfig,
    triggered: list[str],
) -> tuple[list[str], list[str], list[str], float, float]:
    """
    Demote false-positive destruction / soft fragmentation.
    Returns (bads, warns, posits, struct_p, integ) possibly repaired.
    """
    struct_p = _f(rf, "structure_preservation_score", 75.0)
    detail_p = _f(rf, "detail_retention_score", 75.0)
    edge_rf = _f(rf, "raw_final_edge_consistency_score", 75.0)
    overexp = _f(rf, "foreground_overexposure_score", 80.0)
    integ = _f(
        rf,
        "raw_final_integrity",
        (struct_p + detail_p + edge_rf + overexp) / 4.0,
    )

    # Soften foreground_fragmented unless spray-like / catastrophic holes
    if "foreground_fragmented" in bads:
        n_tiny = _f(mask_stats, "n_tiny_components")
        main_frac = _f(mask_stats, "main_component_frac", 1.0)
        n_sig = _f(mask_stats, "n_significant_components", 1.0)
        severe_frag = (n_tiny >= 12 and main_frac < 0.35) or (
            n_sig >= 8 and main_frac < 0.22
        )
        if (
            not severe_frag
            or "multi_object_ok" in posits
            or is_legitimate_multi_object(mask_stats, cfg)
        ):
            bads = [b for b in bads if b != "foreground_fragmented"]
            if "foreground_fragmented" not in warns:
                warns.append("foreground_fragmented")
            triggered.append("fragmentation_softened")

    # Demote uncorroborated product_structure_destroyed
    if "product_structure_destroyed" in bads:
        if destruction_corroborated(rf, structure, bads):
            triggered.append("destruction_confirmed")
        else:
            bads = [b for b in bads if b != "product_structure_destroyed"]
            if "structure_integrity_warn" not in warns:
                warns.append("structure_integrity_warn")
            triggered.append("destruction_false_positive_demoted")
            survival = _f(rf, "foreground_survival_score", 100.0)
            largest_miss = _f(rf, "largest_missing_region_ratio")
            # Contradicted wipe zeroing structure while other channels + spatial healthy
            if (
                edge_rf >= 80.0
                and detail_p >= 80.0
                and overexp >= 80.0
                and survival >= 82.0
                and largest_miss < 0.12
                and "large_contiguous_foreground_loss" not in bads
            ):
                struct_p = max(struct_p, 72.0)
                integ = float(
                    0.30 * struct_p
                    + 0.20 * detail_p
                    + 0.15 * edge_rf
                    + 0.15 * overexp
                    + 0.20 * min(100.0, survival)
                )
                rf["structure_preservation_score"] = struct_p
                rf["raw_final_integrity"] = integ
                triggered.append("structure_score_repaired_fp")

    # Never demote explicit spatial contiguous loss
    if _f(rf, "large_contiguous_foreground_loss") >= 0.5:
        if "large_contiguous_foreground_loss" not in bads:
            bads.append("large_contiguous_foreground_loss")
        triggered.append("spatial_loss_retained")

    return bads, warns, posits, struct_p, integ


def _weighted(subs: dict[str, float], weights: dict[str, float]) -> float:
    wsum = sum(weights.values()) or 1.0
    return sum(subs[k] * (weights[k] / wsum) for k in weights if k in subs)


@dataclass
class QCResult:
    filename: str = ""
    final_score: float = 0.0
    core_score: float = 0.0
    aesthetic_score: float = 0.0
    decision: str = "review"
    background_purity_score: float = 0.0
    edge_integrity_score: float = 0.0
    object_completeness_score: float = 0.0
    structure_preservation_score: float = 0.0
    detail_retention_score: float = 0.0
    raw_final_edge_consistency_score: float = 0.0
    foreground_overexposure_score: float = 0.0
    segmentation_confidence_score: float = 0.0
    color_preservation_score: float = 0.0
    sharpness_score: float = 0.0
    exposure_score: float = 0.0
    composition_score: float = 0.0
    halo_score: float = 0.0
    shadow_score: float = 0.0
    triggered_rules: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fatal_errors: list[str] = field(default_factory=list)
    processing_profile: str = "NORMAL"
    reason: str = ""
    zone: str = "high_bad"

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.filename,
            "decision": self.decision,
            "final_score": round(self.final_score, 2),
            "core_score": round(self.core_score, 2),
            "aesthetic_score": round(self.aesthetic_score, 2),
            "processing_profile": self.processing_profile,
            "profile": self.processing_profile,
            "subscores": {
                "background_purity": round(self.background_purity_score, 1),
                "edge_integrity": round(self.edge_integrity_score, 1),
                "object_completeness": round(self.object_completeness_score, 1),
                "structure_preservation": round(self.structure_preservation_score, 1),
                "detail_retention": round(self.detail_retention_score, 1),
                "raw_final_edge_consistency": round(
                    self.raw_final_edge_consistency_score, 1
                ),
                "foreground_overexposure": round(self.foreground_overexposure_score, 1),
                "segmentation_confidence": round(self.segmentation_confidence_score, 1),
                "color_preservation": round(self.color_preservation_score, 1),
                "sharpness": round(self.sharpness_score, 1),
                "exposure": round(self.exposure_score, 1),
                "composition": round(self.composition_score, 1),
                "halo": round(self.halo_score, 1),
                "shadow": round(self.shadow_score, 1),
                # legacy keys
                "background_purity_score": round(self.background_purity_score, 1),
                "edge_integrity_score": round(self.edge_integrity_score, 1),
                "object_completeness_score": round(self.object_completeness_score, 1),
                "composition_score": round(self.composition_score, 1),
                "color_preservation_score": round(self.color_preservation_score, 1),
                "sharpness_score": round(self.sharpness_score, 1),
                "exposure_score": round(self.exposure_score, 1),
                "halo_score": round(self.halo_score, 1),
                "mask_confidence_score": round(self.segmentation_confidence_score, 1),
            },
            "triggered_rules": list(self.triggered_rules),
            "warnings": list(self.warnings),
            "fatal_errors": list(self.fatal_errors),
            "reason": self.reason,
            "zone": self.zone,
        }


def build_qc_report(
    mask_stats: dict[str, Any] | None,
    cutout_stats: dict[str, Any] | None,
    studio_stats: dict[str, Any] | None,
    structure_stats: dict[str, Any] | None = None,
    *,
    raw_final_stats: dict[str, Any] | None = None,
    cfg: QCConfig | None = None,
    after_rescue: bool = False,
    filename: str = "",
) -> dict[str, Any]:
    """Produce explainable QC report with core/aesthetic scores and decision."""
    cfg = cfg or get_qc_config()
    bads, warns, posits = _collect_tags(
        mask_stats, cutout_stats, studio_stats, structure_stats, raw_final_stats
    )
    triggered: list[str] = []
    fatal: list[str] = []

    if is_legitimate_multi_object(mask_stats, cfg) or "multi_object_ok" in posits:
        if "foreground_fragmented" in bads:
            bads = [b for b in bads if b != "foreground_fragmented"]
            if "foreground_fragmented" not in warns:
                warns.append("foreground_fragmented")
            posits = list(dict.fromkeys(posits + ["multi_object_ok"]))
            triggered.append("multi_object_reclassified")

    profile = detect_qc_profile(mask_stats, studio_stats, posits, bads, warns)

    rf = dict(raw_final_stats or {})
    triggered.extend(list(rf.get("_triggered") or []))

    # Demote false-positive destruction / soft fragmentation BEFORE instant reject
    bads, warns, posits, struct_p, integ = sanitize_destruction_and_fragmentation(
        bads, warns, posits, rf, structure_stats, mask_stats, cfg, triggered
    )
    detail_p = _f(rf, "detail_retention_score", 75.0)
    edge_rf = _f(rf, "raw_final_edge_consistency_score", 75.0)
    overexp = _f(rf, "foreground_overexposure_score", 80.0)
    # Keep rf tags in sync for downstream consumers
    rf["_bads"] = [b for b in (rf.get("_bads") or []) if b in bads or b not in {
        "product_structure_destroyed"
    }]
    if "product_structure_destroyed" in bads and "product_structure_destroyed" not in (
        rf.get("_bads") or []
    ):
        rf["_bads"] = list(rf.get("_bads") or []) + ["product_structure_destroyed"]

    instant = check_instant_reject(bads, structure_stats, cfg, raw_final=rf)
    if instant:
        fatal.append(instant)
        result = QCResult(
            filename=filename,
            final_score=22.0,
            core_score=18.0,
            aesthetic_score=35.0,
            decision="review",
            background_purity_score=20.0,
            edge_integrity_score=20.0,
            object_completeness_score=15.0,
            structure_preservation_score=struct_p if rf else 15.0,
            detail_retention_score=detail_p if rf else 15.0,
            raw_final_edge_consistency_score=edge_rf if rf else 15.0,
            foreground_overexposure_score=overexp if rf else 15.0,
            segmentation_confidence_score=15.0,
            color_preservation_score=25.0,
            sharpness_score=40.0,
            exposure_score=40.0,
            composition_score=40.0,
            halo_score=30.0,
            shadow_score=40.0,
            triggered_rules=[f"instant_reject:{instant}"],
            warnings=warns,
            fatal_errors=fatal,
            processing_profile=profile,
            reason=f"Severe failure: {instant}",
            zone="high_bad",
        )
        report = result.to_dict()
        report["bads"] = bads
        report["warns"] = warns
        report["posits"] = posits
        report["raw_final"] = {k: v for k, v in rf.items() if not str(k).startswith("_")}
        report["thresholds"] = {
            "pass_min": cfg.pass_min,
            "second_pass_min": cfg.second_pass_min,
            "core_pass_min": cfg.core_pass_min,
            "after_rescue": after_rescue,
        }
        return report

    mask_s, t1 = score_mask_confidence(mask_stats, bads, warns, posits, cfg)
    edge_s, t2 = score_edge_integrity(cutout_stats, studio_stats, bads, warns)
    obj_s, t3 = score_object_completeness(
        structure_stats, mask_stats, bads, warns, posits, cfg, raw_final=rf
    )
    bg_s, t4 = score_background_purity(studio_stats, bads, warns, cfg)
    shadow_s, t4b = score_shadow(studio_stats, cfg)
    comp_s, t5 = score_composition(mask_stats, studio_stats, cfg)
    color_s, t6 = score_color_preservation(cutout_stats, studio_stats, posits)
    sharp_s, exp_s, halo_s, t7 = score_sharpness_exposure_halo(
        cutout_stats, studio_stats, warns, bads, profile
    )
    triggered.extend(t1 + t2 + t3 + t4 + t4b + t5 + t6 + t7)
    triggered = list(dict.fromkeys(triggered))

    cw = cfg.core_weights
    core_subs = {
        "object_completeness": obj_s,
        "structure_preservation": struct_p,
        "detail_retention": detail_p,
        "edge_integrity": edge_s,
        "raw_final_edge_consistency": edge_rf,
        "foreground_overexposure": overexp,
        "segmentation_confidence": mask_s,
        "background_purity": bg_s,
        "color_preservation": color_s,
    }
    core_w = {
        "object_completeness": cw.object_completeness,
        "structure_preservation": cw.structure_preservation,
        "detail_retention": cw.detail_retention,
        "edge_integrity": cw.edge_integrity,
        "raw_final_edge_consistency": cw.raw_final_edge_consistency,
        "foreground_overexposure": cw.foreground_overexposure,
        "segmentation_confidence": cw.segmentation_confidence,
        "background_purity": cw.background_purity,
        "color_preservation": cw.color_preservation,
    }
    core = _weighted(core_subs, core_w)
    core = 0.92 * core + 0.08 * halo_s

    aw = cfg.aesthetic_weights
    aesthetic_subs = {
        "composition": comp_s,
        "exposure": exp_s,
        "sharpness": sharp_s,
        "shadow": shadow_s,
    }
    aesthetic_w = {
        "composition": aw.composition,
        "exposure": aw.exposure,
        "sharpness": aw.sharpness,
        "shadow": aw.shadow,
    }
    aesthetic = _weighted(aesthetic_subs, aesthetic_w)

    final = cfg.core_blend * core + (1.0 - cfg.core_blend) * aesthetic

    if "raw_final_integrity_ok" in posits:
        final = min(100.0, final + 2.0)
        core = min(100.0, core + 1.5)
    if ("dark_high_contrast" in posits or "dark_on_white" in posits) and integ >= 70:
        final = min(100.0, final + 1.5)
    if "multi_object_ok" in posits and integ >= 65:
        final = min(100.0, final + 1.0)
        triggered.append("multi_object_boost")

    sl = _f(structure_stats, "structure_loss")
    soft_cov = _f(mask_stats, "soft_coverage")
    if "mask_near_full_frame" in bads and soft_cov > 0.55:
        final = min(final, 62.0)
        core = min(core, 60.0)
        triggered.append("cap_full_frame_mask_severe")
    if "foggy_soft_mask" in bads and "foggy_alpha_edges" in bads:
        final = min(final, 58.0)
        triggered.append("cap_severe_fog")
    if "catastrophic_structure_loss" in bads and sl >= cfg.struct_loss_hard:
        final = min(final, 50.0)
        core = min(core, 48.0)
        triggered.append("cap_structure_bad_severe")

    if integ < cfg.integrity_pass_floor:
        core = min(core, integ + 8.0)
        final = min(final, max(integ + 5.0, cfg.second_pass_min - 1.0))
        triggered.append("integrity_floor_cap")
    if struct_p < cfg.structure_pass_floor:
        core = min(core, struct_p + 6.0)
        triggered.append("structure_floor_cap")
    if overexp < cfg.overexposure_pass_floor:
        core = min(core, overexp + 8.0)
        final = min(final, max(overexp + 10.0, cfg.second_pass_min - 1.0))
        triggered.append("overexposure_floor_cap")

    if (
        "foreground_fragmented" in bads
        and "multi_object_ok" not in posits
        and not is_legitimate_multi_object(mask_stats, cfg)
    ):
        final = min(final, max(56.0, final - 8.0))
        triggered.append("frag_noise_penalty")

    destruction = {
        "product_structure_destroyed",
        "product_whiteout",
        "detail_destroyed",
        "edge_structure_lost",
        "large_contiguous_foreground_loss",
    }
    has_destruction = any(t in destruction for t in bads)
    # Only confirmed destruction blocks; uncorroborated tags already demoted
    if has_destruction and not destruction_corroborated(rf, structure_stats, bads):
        has_destruction = (
            "product_whiteout" in bads
            or "detail_destroyed" in bads
            or "large_contiguous_foreground_loss" in bads
        )
    pass_bar = cfg.pass_min_after_rescue if after_rescue else cfg.pass_min

    survival = _f(rf, "foreground_survival_score", 100.0)
    largest_miss = _f(rf, "largest_missing_region_ratio")
    spatial_block = (
        "large_contiguous_foreground_loss" in bads
        or (
            largest_miss >= 0.18
            and survival < 78.0
            and _f(rf, "evidence_wipe_frac") >= 0.12
        )
    )

    if spatial_block:
        decision: QCDecision = "review"
        reason = "Large contiguous product region missing (RAW vs FINAL) — REVIEW"
        triggered.append("spatial_foreground_loss_review")
        if "large_contiguous_foreground_loss" not in bads:
            bads.append("large_contiguous_foreground_loss")
    elif has_destruction:
        # Confirmed product destruction → always REVIEW (never PASS)
        decision = "review"
        reason = "Corroborated product destruction (RAW vs FINAL) — REVIEW"
        triggered.append("integrity_forced_review")
    elif integ < cfg.core_second_pass_min:
        if integ < 40:
            decision = "review"
            reason = "Product integrity damaged (RAW vs FINAL) — REVIEW"
            triggered.append("integrity_forced_review")
        else:
            decision = "second_pass"
            reason = "Uncertain product integrity (RAW vs FINAL) — SECOND_PASS"
            triggered.append("integrity_forced_second_pass")
    elif core < cfg.core_second_pass_min and final < cfg.second_pass_min:
        decision = "review"
        reason = "Core product integrity too low for commercial PASS"
    elif core < cfg.core_pass_min or final < pass_bar:
        if core >= cfg.core_second_pass_min and final >= cfg.second_pass_min:
            decision = "second_pass"
            reason = "Borderline core — SECOND_PASS"
        elif final >= cfg.second_pass_min:
            decision = "second_pass"
            reason = "Borderline overall score — SECOND_PASS"
        else:
            decision = "review"
            reason = "Below commercial threshold — REVIEW"
    else:
        if (
            integ < cfg.integrity_pass_floor
            or struct_p < cfg.structure_pass_floor
            or overexp < cfg.overexposure_pass_floor
        ):
            decision = "second_pass"
            reason = "Core score OK but RAW↔FINAL integrity below PASS floor"
            triggered.append("integrity_pass_blocked")
        else:
            decision = "pass"
            reason = "Core + RAW↔FINAL integrity commercially acceptable"

    if (
        decision == "review"
        and final >= cfg.second_pass_min - 2
        and core >= 50
        and not has_destruction
    ):
        decision = "second_pass"
        reason = "Near-threshold — prefer SECOND_PASS"

    if (
        decision == "second_pass"
        and core >= cfg.core_pass_min + 4
        and integ >= cfg.integrity_pass_floor + 8
        and struct_p >= cfg.structure_pass_floor + 8
        and overexp >= cfg.overexposure_pass_floor + 10
        and obj_s >= 80
        and "final_washed_out" not in bads
        and "product_faded" not in bads
        and not has_destruction
        and not (
            "catastrophic_structure_loss" in bads and sl >= cfg.struct_loss_hard
        )
    ):
        decision = "pass"
        reason = "Excellent core + RAW↔FINAL integrity — PASS"
        triggered.append("core_quality_pass_override")

    if decision == "pass" and (
        has_destruction or spatial_block or "large_contiguous_foreground_loss" in bads
    ):
        decision = "review"
        reason = "Product destruction / spatial loss tags present — REVIEW"
        triggered.append("destruction_blocks_pass")

    # Incomplete product: catastrophic structure bad + very low completeness
    if decision == "pass" and "catastrophic_structure_loss" in bads and obj_s < 40.0:
        decision = "review"
        reason = "Severe object incompleteness with structure loss — REVIEW"
        triggered.append("incomplete_product_review")

    result = QCResult(
        filename=filename,
        final_score=final,
        core_score=core,
        aesthetic_score=aesthetic,
        decision=decision,
        background_purity_score=bg_s,
        edge_integrity_score=edge_s,
        object_completeness_score=obj_s,
        structure_preservation_score=struct_p,
        detail_retention_score=detail_p,
        raw_final_edge_consistency_score=edge_rf,
        foreground_overexposure_score=overexp,
        segmentation_confidence_score=mask_s,
        color_preservation_score=color_s,
        sharpness_score=sharp_s,
        exposure_score=exp_s,
        composition_score=comp_s,
        halo_score=halo_s,
        shadow_score=shadow_s,
        triggered_rules=triggered,
        warnings=warns,
        fatal_errors=fatal,
        processing_profile=profile,
        reason=reason,
        zone=_ZONE_MAP[decision],
    )
    report = result.to_dict()
    report["bads"] = bads
    report["warns"] = warns
    report["posits"] = posits
    report["raw_final"] = {k: v for k, v in rf.items() if not str(k).startswith("_")}
    report["thresholds"] = {
        "pass_min": pass_bar,
        "second_pass_min": cfg.second_pass_min,
        "core_pass_min": cfg.core_pass_min,
        "core_second_pass_min": cfg.core_second_pass_min,
        "core_blend": cfg.core_blend,
        "integrity_pass_floor": cfg.integrity_pass_floor,
        "after_rescue": after_rescue,
    }
    return report


def decision_to_zone(decision: str) -> str:
    return _ZONE_MAP.get(decision, "uncertain")


def write_qc_diagnostics(
    report: dict[str, Any],
    *,
    output_root: Path,
    review_id: str,
    cfg: QCConfig | None = None,
) -> Path | None:
    """Write per-image QC JSON under output_root/QC/ and append qc_report.csv."""
    cfg = cfg or get_qc_config()
    if not cfg.write_qc_json:
        return None
    try:
        qc_dir = Path(output_root) / cfg.qc_subdir
        qc_dir.mkdir(parents=True, exist_ok=True)
        path = qc_dir / f"{review_id}.json"
        path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if cfg.write_qc_csv:
            _append_qc_csv(Path(output_root) / cfg.qc_csv_name, report, review_id)
        return path
    except Exception:
        return None


_CSV_FIELDS = [
    "review_id",
    "file",
    "decision",
    "final_score",
    "core_score",
    "aesthetic_score",
    "processing_profile",
    "reason",
    "triggered_rules",
    "fatal_errors",
    "warnings",
    "background_purity",
    "edge_integrity",
    "object_completeness",
    "structure_preservation",
    "detail_retention",
    "raw_final_edge_consistency",
    "foreground_overexposure",
    "segmentation_confidence",
    "color_preservation",
    "sharpness",
    "exposure",
    "composition",
    "halo",
    "shadow",
]


def _append_qc_csv(path: Path, report: dict[str, Any], review_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    subs = report.get("subscores") or {}
    row = {
        "review_id": review_id,
        "file": report.get("file", ""),
        "decision": report.get("decision", ""),
        "final_score": report.get("final_score", ""),
        "core_score": report.get("core_score", ""),
        "aesthetic_score": report.get("aesthetic_score", ""),
        "processing_profile": report.get("processing_profile", ""),
        "reason": report.get("reason", ""),
        "triggered_rules": ";".join(report.get("triggered_rules") or []),
        "fatal_errors": ";".join(report.get("fatal_errors") or []),
        "warnings": ";".join(report.get("warnings") or report.get("warns") or []),
        "background_purity": subs.get("background_purity", ""),
        "edge_integrity": subs.get("edge_integrity", ""),
        "object_completeness": subs.get("object_completeness", ""),
        "structure_preservation": subs.get("structure_preservation", ""),
        "detail_retention": subs.get("detail_retention", ""),
        "raw_final_edge_consistency": subs.get("raw_final_edge_consistency", ""),
        "foreground_overexposure": subs.get("foreground_overexposure", ""),
        "segmentation_confidence": subs.get("segmentation_confidence", ""),
        "color_preservation": subs.get("color_preservation", ""),
        "sharpness": subs.get("sharpness", ""),
        "exposure": subs.get("exposure", ""),
        "composition": subs.get("composition", ""),
        "halo": subs.get("halo", ""),
        "shadow": subs.get("shadow", ""),
    }
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        if write_header:
            w.writeheader()
        w.writerow(row)
