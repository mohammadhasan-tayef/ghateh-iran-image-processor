"""Central processing parameters for the studio editing pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProcessingConfig:
    """Tunable knobs — avoid magic numbers in pipeline stages."""

    # Canvas
    canvas_size: int = 2000
    product_fill_min: float = 0.72
    product_fill_max: float = 0.88
    product_fill_default: float = 0.84
    margin_min_frac: float = 0.06
    margin_max_frac: float = 0.14

    # Mask refinement
    tiny_component_max_frac: float = 0.0025
    min_component_px: int = 48
    preserve_holes_min_px: int = 12
    edge_feather_sigma: float = 0.55
    mesh_feather_sigma: float = 0.35
    morph_open_kernel: int = 3

    # Edge / halo
    halo_band_px: int = 3
    decontam_strength: float = 0.55
    decontam_strength_white: float = 0.35
    edge_gradient_agree_min: float = 0.35

    # Color / exposure
    max_exposure_gain: float = 1.18
    max_exposure_cut: float = 0.92
    max_wb_shift: float = 0.06
    max_delta_e: float = 8.0
    target_fg_luma: float = 118.0
    target_fg_luma_dark: float = 72.0
    target_fg_luma_white: float = 175.0

    # Enhance
    denoise_noise_threshold: float = 0.045
    denoise_strength: float = 0.35
    sharpen_amount_min: float = 0.0
    sharpen_amount_max: float = 0.55
    local_contrast_amount: float = 0.22

    # Segmentation confidence
    conf_min_accept: float = 0.62
    conf_second_model: float = 0.78
    iou_agree_min: float = 0.72

    # Shadow cleanup
    shadow_luma_max: float = 55.0
    shadow_sat_max: float = 28.0
    contact_shadow_opacity: float = 0.18

    # Debug / reporting
    debug_enabled: bool = False
    write_processing_report: bool = True

    # Feature flag: use new studio post-process (mask/edge/color/compose)
    use_studio_engine: bool = True


DEFAULT_PROCESSING = ProcessingConfig()
