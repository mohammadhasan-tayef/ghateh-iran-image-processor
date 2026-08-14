"""
Central QC configuration for GHATE PRODUCT STUDIO (v3 — RAW-aware integrity).

Decision bands:
  core excellent + overall OK → PASS (Approved)
  uncertain product integrity → SECOND_PASS (Adaptive rescue)
  confirmed commercially bad → REVIEW

v3 priority: product integrity from RAW vs FINAL dominates.
Background cleanliness alone can never PASS a destroyed product.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class QCCoreWeights:
    """Product integrity — dominates PASS/REVIEW."""

    object_completeness: float = 0.14
    structure_preservation: float = 0.18
    detail_retention: float = 0.14
    edge_integrity: float = 0.10
    raw_final_edge_consistency: float = 0.12
    foreground_overexposure: float = 0.14
    segmentation_confidence: float = 0.08
    background_purity: float = 0.06
    color_preservation: float = 0.04


@dataclass
class QCAestheticWeights:
    """Presentation — soft influence only."""

    composition: float = 0.25
    exposure: float = 0.25
    sharpness: float = 0.25
    shadow: float = 0.25


@dataclass
class QCConfig:
    """
    Folder mapping:
      PASS        → Approved/
      SECOND_PASS → internal reprocess
      REVIEW      → Review/
      FAILED      → no usable candidate
    """

    # Decision bands
    pass_min: float = 76.0
    second_pass_min: float = 58.0
    pass_min_after_rescue: float = 72.0

    # Core must be healthy for PASS
    core_pass_min: float = 74.0
    core_second_pass_min: float = 56.0
    core_blend: float = 0.85  # heavier core than v2

    # Integrity floors: even with high aesthetic, block PASS
    integrity_pass_floor: float = 62.0
    structure_pass_floor: float = 58.0
    overexposure_pass_floor: float = 55.0

    core_weights: QCCoreWeights = field(default_factory=QCCoreWeights)
    aesthetic_weights: QCAestheticWeights = field(default_factory=QCAestheticWeights)

    mild_shadow_ok: bool = True
    center_offset_soft: float = 0.12
    center_offset_hard: float = 0.28
    size_fill_soft_lo: float = 0.08
    size_fill_soft_hi: float = 0.94

    # Legacy mask-structure curves (evaluate_structure_consistency)
    struct_loss_soft: float = 0.22
    struct_loss_hard: float = 0.42
    edge_drop_soft: float = 0.26
    edge_drop_hard: float = 0.50

    # Independent RAW↔FINAL thresholds
    raw_wipe_soft: float = 0.18
    raw_wipe_hard: float = 0.38
    detail_ratio_soft: float = 0.55
    detail_ratio_hard: float = 0.32
    edge_keep_soft: float = 0.62
    edge_keep_hard: float = 0.40
    whiteout_soft: float = 0.12
    whiteout_hard: float = 0.28

    # Mask-aware background
    bg_safety_band_iters: int = 6
    bg_dirty_soft: float = 0.012
    bg_dirty_hard: float = 0.06
    shadow_soft: float = 0.008
    shadow_hard: float = 0.045

    # Multi-object
    multi_object_min_components: int = 2
    multi_object_max_components: int = 12
    multi_object_min_comp_frac: float = 0.06
    spray_tiny_max_frac: float = 0.02

    # Instant-reject (severe only).
    # NOTE: product_structure_destroyed is intentionally NOT here — it requires
    # corroboration in qc_engine (blind wipe heuristics caused mass false REVIEW).
    instant_reject_reasons: tuple[str, ...] = (
        "empty_mask",
        "final_too_white_small_product",
        "final_washed_out",
        "product_faded",
        "product_whiteout",
        "empty_or_tiny_foreground",
    )
    instant_struct_loss: float = 0.48
    # Instant when independent integrity is catastrophic
    instant_integrity_max: float = 28.0

    write_qc_json: bool = True
    write_qc_csv: bool = True
    qc_subdir: str = "QC"
    qc_csv_name: str = "qc_report.csv"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["instant_reject_reasons"] = list(self.instant_reject_reasons)
        return d


@dataclass
class QCWeights:
    """Legacy flat weights for older report consumers."""

    background_purity_score: float = 0.06
    edge_integrity_score: float = 0.10
    object_completeness_score: float = 0.14
    composition_score: float = 0.05
    color_preservation_score: float = 0.04
    sharpness_score: float = 0.05
    exposure_score: float = 0.05
    halo_score: float = 0.06
    mask_confidence_score: float = 0.08


QC_CONFIG = QCConfig()


def set_qc_config(cfg: QCConfig | None = None) -> QCConfig:
    global QC_CONFIG
    QC_CONFIG = cfg or QCConfig()
    return QC_CONFIG


def get_qc_config() -> QCConfig:
    return QC_CONFIG
