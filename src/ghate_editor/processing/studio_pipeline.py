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
from .alpha_matting import refine_alpha_matting
from .edge_refinement import (
    decontaminate_halo,
    refine_edges,
    strip_large_shadows,
    uncomposite_edge_band,
)
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
    matting: dict[str, Any] = field(default_factory=dict)
    uncomposite: dict[str, Any] = field(default_factory=dict)
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
            "matting": self.matting,
            "uncomposite": self.uncomposite,
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
    skip_color: bool | None = None,
    raw_mask_for_debug: Image.Image | None = None,
    skip_matting: bool = False,
    skip_mask_refine: bool = False,
    locked_alpha=None,
) -> tuple[Image.Image, ProfileDecision, StudioProcessReport, Image.Image]:
    """
    Mask refine → trimap/matting → original RGB + alpha → shadow strip
    → edge uncomposite/halo. Color/enhance only if skip_color is False.

    Default (fidelity): keep original product RGB; no synthetic recolor.
    Returns (refined_rgba, profile, report, refined_mask).
    """
    cfg = cfg or DEFAULT_PROCESSING
    scene = scene or {}
    report = StudioProcessReport()
    if os.environ.get("GHATE_LEGACY_EDGES", "").strip().lower() in {"1", "true", "yes"}:
        from dataclasses import replace

        cfg = replace(
            cfg,
            fidelity_extraction=False,
            use_alpha_matting=False,
            skip_color_by_default=False,
        )
    if skip_color is None:
        skip_color = bool(cfg.skip_color_by_default)

    from ghate_editor.extraction.lock import FinalAlpha, lock_alpha

    if locked_alpha is not None and not isinstance(locked_alpha, FinalAlpha):
        locked_alpha = lock_alpha(locked_alpha, source_engine=model_name)

    # LOCKED PATH: geometry is frozen. No refine/matting/erode/feather/strip.
    if locked_alpha is not None:
        lock_mask = locked_alpha.image()
        seg = score_mask_confidence(lock_mask, model_name=model_name, rgb=working_rgb)
        report.segmentation = seg.to_dict()
        analysis = analyze_image(working_rgb, mask=lock_mask)
        report.analysis = analysis.to_dict()
        profile = select_profile(analysis, mask=lock_mask, scene=scene, cfg=cfg)
        report.profile = profile.to_dict()
        report.mask_refine = {"skipped": True, "reason": "alpha_locked"}
        report.matting = {"used": False, "reason": "alpha_locked"}
        report.edge = {"mode": "locked"}
        report.shadow = {"skipped": True, "reason": "alpha_locked_no_geometry_change"}

        from ghate_editor.extraction.fidelity import assemble_fidelity_rgba
        from ghate_editor.extraction.enhancer import ProductEnhancer

        gate = str((scene or {}).get("primary_gate") or "")
        uncertain = gate in {"UNCERTAIN", "INVALID"}
        rgba, finfo = assemble_fidelity_rgba(
            working_rgb,
            locked_alpha,
            decontam=True,
            canvas_size=int(cfg.canvas_size),
            uncertain=uncertain,
            lo=float(getattr(cfg, "edge_alpha_lo", 0.02)),
            hi=float(getattr(cfg, "edge_alpha_hi", 0.98)),
        )
        report.uncomposite = {"skipped": True, "reason": "replaced_by_locked_decontam"}
        report.decontam = finfo.get("decontam") or {}
        report.composition["alpha_lock"] = finfo.get("alpha_lock")
        report.composition["zones"] = finfo.get("zones")
        report.composition["rgb_source"] = finfo.get("rgb_source")
        report.composition["assemble_ms"] = finfo.get("assemble_ms")
        report.enhance = {"skipped": True, "product_enhancer": False}
        enhancer = ProductEnhancer()
        if getattr(cfg, "enable_product_enhancer", False):
            enhancer.enabled = True
            from ghate_editor.extraction.zones import product_zones, zone_images

            zimg = zone_images(
                product_zones(locked_alpha, canvas_size=int(cfg.canvas_size))
            )
            rgb_maybe = enhancer.enhance(
                working_rgb,
                zimg["interior_mask"],
                zimg["edge_protection_mask"],
            )
            # Interior-only future path; reassemble with SAME locked alpha.
            from ghate_editor.extraction.lock import restore_locked_alpha

            rgba = restore_locked_alpha(rgb_maybe, locked_alpha)
            report.enhance = {"skipped": False, "product_enhancer": True}
        locked_alpha.verify(rgba.split()[-1], strict=True, label="build_studio_rgba")
        report.exposure_wb = {"skipped": True, "reason": "skip_color"}
        report.color_preserve = {
            "delta_e": 0.0,
            "acceptable": True,
            "rolled_back": False,
        }
        # Stash zone images for debug (not serialized in to_dict unless converted)
        report.debug_dir = None
        return rgba, profile, report, lock_mask


    seg = score_mask_confidence(mask, model_name=model_name, rgb=working_rgb)
    report.segmentation = seg.to_dict()

    analysis = analyze_image(working_rgb, mask=seg.mask)
    report.analysis = analysis.to_dict()

    profile = select_profile(analysis, mask=seg.mask, scene=scene, cfg=cfg)
    report.profile = profile.to_dict()

    if skip_mask_refine:
        refined_mask = seg.mask
        minfo = {"skipped": True, "reason": "soft_alpha_engine"}
    else:
        refined_mask, minfo = refine_mask(seg.mask, profile=profile, cfg=cfg)
    report.mask_refine = minfo

    matted_alpha = refined_mask
    use_matting = bool(cfg.use_alpha_matting and cfg.fidelity_extraction and not skip_matting)
    if use_matting:
        try:
            matted_alpha, minfo_m = refine_alpha_matting(
                working_rgb,
                refined_mask,
                cfg=cfg,
                max_side=int(cfg.matting_max_side),
            )
            report.matting = minfo_m
        except Exception as exc:  # noqa: BLE001
            report.matting = {"used": False, "reason": f"error:{type(exc).__name__}"}
            matted_alpha = refined_mask
    else:
        report.matting = {
            "used": False,
            "reason": "skipped_soft_alpha" if skip_matting else "disabled",
        }

    rgba = working_rgb.convert("RGBA")
    alpha = matted_alpha.convert("L")
    if alpha.size != rgba.size:
        alpha = alpha.resize(rgba.size, Image.Resampling.LANCZOS)
    rgba.putalpha(alpha)

    if not cfg.fidelity_extraction:
        rgba, einfo = refine_edges(rgba, working_rgb, profile=profile, cfg=cfg)
        report.edge = einfo
    else:
        report.edge = {"mode": "matting"}

    rgba, sinfo = strip_large_shadows(rgba, cfg=cfg)
    report.shadow = sinfo
    rgba, uinfo = uncomposite_edge_band(rgba, working_rgb, cfg=cfg)
    report.uncomposite = uinfo
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

    if getattr(cfg, "enable_product_enhancer", False):
        from ghate_editor.extraction.enhancer import ProductEnhancer

        enhancer = ProductEnhancer()
        enhancer.enabled = True
        rgba = enhancer.enhance(rgba)
        report.enhance = {**report.enhance, "product_enhancer": True}
    # else ProductEnhancer remains a no-op extension point (not invoked)

    return rgba, profile, report, matted_alpha


def process_cutout_to_studio(
    working_rgb: Image.Image,
    mask: Image.Image,
    *,
    size: int = 2000,
    with_shadow: bool = False,
    scene: dict[str, Any] | None = None,
    model_name: str = "unknown",
    cfg: ProcessingConfig | None = None,
    debug_root: Path | str | None = None,
    debug_name: str | None = None,
    skip_color: bool | None = None,
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
