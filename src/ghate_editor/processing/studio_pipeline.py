"""
Studio post-segmentation pipeline: refine → decontam → adaptive color → compose.

Called from free_pipeline after rembg mask is obtained. Does not load AI models.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from .analyzer import ImageAnalysis, analyze_image
from .color import adaptive_exposure_wb, apply_with_preservation, product_color_signature
from .composition import compose_white_square
from .config import DEFAULT_PROCESSING, ProcessingConfig
from .debug_io import save_debug_bundle
from .edge_refinement import decontaminate_halo, refine_edges, strip_large_shadows
from .enhancement import adaptive_denoise_sharpen
from .mask_refinement import refine_mask, score_mask_confidence
from .profiles import ProfileDecision, select_profile


@dataclass
class StudioProcessReport:
    profile: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    segmentation: dict[str, Any] = field(default_factory=dict)
    mask_refine: dict[str, Any] = field(default_factory=dict)
    edge: dict[str, Any] = field(default_factory=dict)
    decontam: dict[str, Any] = field(default_factory=dict)
    shadow: dict[str, Any] = field(default_factory=dict)
    exposure_wb: dict[str, Any] = field(default_factory=dict)
    color_preserve: dict[str, Any] = field(default_factory=dict)
    enhance: dict[str, Any] = field(default_factory=dict)
    composition: dict[str, Any] = field(default_factory=dict)
    debug_dir: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "analysis": self.analysis,
            "segmentation": self.segmentation,
            "mask_refine": self.mask_refine,
            "edge": self.edge,
            "decontam": self.decontam,
            "shadow": self.shadow,
            "exposure_wb": self.exposure_wb,
            "color_preserve": self.color_preserve,
            "enhance": self.enhance,
            "composition": self.composition,
            "debug_dir": self.debug_dir,
        }


def _debug_enabled(cfg: ProcessingConfig) -> bool:
    if cfg.debug_enabled:
        return True
    return os.environ.get("GHATE_DEBUG", "").strip().lower() in {"1", "true", "yes"}


def build_studio_rgba(
    working_rgb: Image.Image,
    mask: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
    model_name: str = "unknown",
    cfg: ProcessingConfig | None = None,
    skip_color: bool = False,
    raw_mask_for_debug: Image.Image | None = None,
) -> tuple[Image.Image, ProfileDecision, StudioProcessReport, Image.Image]:
    """
    Mask refine → edge → shadow strip → halo → adaptive color/enhance.

    Returns (refined_rgba, profile, report, refined_mask).
    """
    cfg = cfg or DEFAULT_PROCESSING
    scene = scene or {}
    report = StudioProcessReport()

    seg = score_mask_confidence(mask, model_name=model_name, rgb=working_rgb)
    report.segmentation = seg.to_dict()

    analysis = analyze_image(working_rgb, mask=seg.mask)
    report.analysis = analysis.to_dict()

    profile = select_profile(analysis, mask=seg.mask, scene=scene, cfg=cfg)
    report.profile = profile.to_dict()

    refined_mask, minfo = refine_mask(seg.mask, profile=profile, cfg=cfg)
    report.mask_refine = minfo

    rgba = working_rgb.convert("RGBA")
    alpha = refined_mask.convert("L")
    if alpha.size != rgba.size:
        alpha = alpha.resize(rgba.size, Image.Resampling.LANCZOS)
    rgba.putalpha(alpha)

    rgba, einfo = refine_edges(rgba, working_rgb, profile=profile, cfg=cfg)
    report.edge = einfo
    rgba, sinfo = strip_large_shadows(rgba, cfg=cfg)
    report.shadow = sinfo
    rgba, dinfo = decontaminate_halo(rgba, profile=profile, cfg=cfg)
    report.decontam = dinfo

    if not skip_color:
        edited, erep = adaptive_exposure_wb(rgba, analysis, profile=profile, cfg=cfg)
        report.exposure_wb = erep
        edited, cpres = apply_with_preservation(rgba, edited, cfg=cfg)
        report.color_preserve = cpres.to_dict()
        # Re-analyze only when exposure/WB actually changed pixels
        if bool(erep.get("skipped")):
            analysis2 = analysis
        else:
            analysis2 = analyze_image(edited.convert("RGB"), mask=edited.split()[-1])
        edited, hen = adaptive_denoise_sharpen(edited, analysis2, profile=profile, cfg=cfg)
        report.enhance = hen
        rgba = edited
    else:
        report.exposure_wb = {"skipped": True, "reason": "skip_color"}
        report.color_preserve = {"delta_e": 0.0, "acceptable": True, "rolled_back": False}
        report.enhance = {"skipped": True}

    return rgba, profile, report, refined_mask


def process_cutout_to_studio(
    working_rgb: Image.Image,
    mask: Image.Image,
    *,
    size: int = 2000,
    with_shadow: bool = True,
    scene: dict[str, Any] | None = None,
    model_name: str = "unknown",
    cfg: ProcessingConfig | None = None,
    debug_root: Path | str | None = None,
    debug_name: str | None = None,
    skip_color: bool = False,
) -> tuple[Image.Image, Image.Image, StudioProcessReport]:
    """
    Full studio path from RGB + raw mask → refined RGBA cutout + final RGB canvas.

    Returns (studio_rgb, refined_rgba, report).
    """
    cfg = cfg or DEFAULT_PROCESSING
    rgba, profile, report, refined_mask = build_studio_rgba(
        working_rgb,
        mask,
        scene=scene,
        model_name=model_name,
        cfg=cfg,
        skip_color=skip_color,
        raw_mask_for_debug=mask,
    )

    studio, cinfo = compose_white_square(
        rgba,
        size=size,
        with_shadow=with_shadow,
        profile=profile,
        cfg=cfg,
    )
    report.composition = cinfo

    if _debug_enabled(cfg) and debug_root is not None:
        name = debug_name or "image"
        bundle = Path(debug_root) / name
        color_sig = product_color_signature(rgba)
        save_debug_bundle(
            bundle,
            original=working_rgb,
            mask_raw=mask,
            mask_refined=refined_mask,
            foreground=rgba,
            edge_debug=rgba,
            final=studio,
            analysis={
                **report.to_dict(),
                "color_signature_lab": color_sig.tolist(),
            },
        )
        report.debug_dir = str(bundle)

    return studio, rgba, report


def refine_mask_only(
    mask: Image.Image,
    working_rgb: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
    model_name: str = "unknown",
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, ProfileDecision, ImageAnalysis, dict[str, Any]]:
    """Lightweight path used when only mask upgrade is needed mid-_run_once."""
    cfg = cfg or DEFAULT_PROCESSING
    seg = score_mask_confidence(mask, model_name=model_name, rgb=working_rgb)
    analysis = analyze_image(working_rgb, mask=seg.mask)
    profile = select_profile(analysis, mask=seg.mask, scene=scene, cfg=cfg)
    refined, info = refine_mask(seg.mask, profile=profile, cfg=cfg)
    meta = {
        "segmentation": seg.to_dict(),
        "profile": profile.to_dict(),
        "analysis": analysis.to_dict(),
        "mask_refine": info,
    }
    return refined, profile, analysis, meta
