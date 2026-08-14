"""Professional local studio processing modules (post-segmentation)."""

from .analyzer import ImageAnalysis, analyze_image
from .composition import compose_white_square
from .config import DEFAULT_PROCESSING, ProcessingConfig
from .mask_refinement import (
    SegmentationResult,
    mask_iou,
    score_mask_confidence,
    select_or_ensemble_masks,
)
from .profiles import ProductProfile, ProfileDecision, select_profile
from .studio_pipeline import (
    StudioProcessReport,
    build_studio_rgba,
    process_cutout_to_studio,
    refine_mask_only,
)

__all__ = [
    "ImageAnalysis",
    "analyze_image",
    "DEFAULT_PROCESSING",
    "ProcessingConfig",
    "SegmentationResult",
    "mask_iou",
    "score_mask_confidence",
    "select_or_ensemble_masks",
    "ProductProfile",
    "ProfileDecision",
    "select_profile",
    "StudioProcessReport",
    "build_studio_rgba",
    "compose_white_square",
    "process_cutout_to_studio",
    "refine_mask_only",
]
