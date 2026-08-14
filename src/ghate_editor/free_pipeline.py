"""Free local ecommerce studio — adaptive quality for white/metallic products."""

from __future__ import annotations

import gc
import io
import os
import threading
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Literal

for _k, _v in (
    ("OMP_NUM_THREADS", "2"),
    ("MKL_NUM_THREADS", "2"),
    ("OPENBLAS_NUM_THREADS", "2"),
    ("NUMEXPR_NUM_THREADS", "2"),
    ("ORT_NUM_THREADS", "2"),
):
    os.environ.setdefault(_k, _v)

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from .model_service import detect_device, get_session, release_memory, warmup

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_OK = True
except Exception:  # noqa: BLE001
    HEIC_OK = False

FREE_PIPELINE_VERSION = "free-v1.14.5"
FREE_MODEL_FAST = "u2net"
FREE_MODEL_QUALITY = "birefnet-general"
FREE_FALLBACK_MODEL = "u2netp"
FREE_MODEL_NAME = FREE_MODEL_FAST

INFER_MAX_SIDE_FAST = 768
INFER_MAX_SIDE_QUALITY = 896
INFER_MAX_SIDE_STRONG = 1024  # strong rescue (BiRefNet / boosted u2net)
INFER_MAX_SIDE_RESCUE = 1024
INFER_MAX_SIDE_ROI = 1280  # ROI crop rescue — higher effective product detail
INFER_MAX_SIDE_OOM_RETRY = 640

WORKING_MAX_SIDE = 2400
WORKING_MAX_SIDE_HEIC = 2048
WORKING_MAX_SIDE_OOM = 1600

REVIEW_DIR_NAME = "Review"
APPROVED_DIR_NAME = "Approved"
DECODE_QUEUE_SIZE = 2
CALIBRATION_DIR_NAME = "calibration"

FreeMode = Literal["fast", "adaptive", "quality"]
OutcomeStatus = Literal["approved", "review", "failed"]
ConfidenceZone = Literal["high_good", "uncertain", "high_bad"]
# Per-image processing state (explicit transitions)
ImageProcState = Literal[
    "pending",
    "decoded",
    "fast_ready",
    "rescue_attempted",
    "rescue_ready",
    "approved",
    "review",
    "failed",
]

_infer_lock = threading.Lock()


@dataclass
class QualityGateConfig:
    """
    Tunable quality thresholds (calibration / production).

    Priority: avoid false Approval, but do not punish clean dark products
    on large white canvases or synthetic contact shadows.
    Metrics are primarily PRODUCT-ROI relative — not full 2000² canvas.
    """

    # Mask (frame-level catastrophic floors only)
    soft_alpha_min: int = 32
    solid_alpha_min: int = 150
    fog_alpha_max: int = 140
    min_soft_cov_frame: float = 0.008  # catastrophic tiny only
    min_solid_cov_frame: float = 0.004
    max_soft_cov_frame: float = 0.55  # product+bg merged / near full-frame
    max_soft_cov_warn: float = 0.45
    # ROI-relative
    min_roi_fill: float = 0.22
    min_roi_fill_difficult: float = 0.28
    min_solid_of_soft: float = 0.30
    fog_ratio_warn: float = 0.50
    fog_ratio_bad: float = 0.65
    min_mean_alpha_soft: float = 100.0
    min_mean_alpha_soft_difficult: float = 115.0
    # Holes — only extreme / mottled (open-frame products are normal)
    hole_frac_catastrophic: float = 0.22
    hole_pixels_catastrophic: int = 25000
    # Components — ignore small legitimate tabs/wheels
    min_sig_comp_frac: float = 0.12  # of solid; below = ignore
    spray_comp_count: int = 5  # many tiny pieces = bad
    # Dark-core split (punched brush frames) — not 1 strong core
    dark_split_main_frac: float = 0.52
    dark_split_warn_frac: float = 0.62
    # Cutout
    cutout_fog_of_fg_warn: float = 0.55
    cutout_fog_of_fg_bad: float = 0.70
    cutout_vis_catastrophic: float = 8.0
    # Studio (product ROI, no synthetic shadow)
    studio_vis_catastrophic: float = 10.0
    dark_core_lum: float = 160.0
    edge_haze_bad: float = 0.55  # light products only
    # Source↔output structural consistency (product ROI / dilated support)
    struct_loss_warn: float = 0.24
    struct_loss_bad: float = 0.38
    edge_drop_warn: float = 0.28
    edge_drop_bad: float = 0.45
    texture_loss_warn: float = 0.28
    texture_loss_bad: float = 0.42
    # Light/grey body wipe (translucent plastic) — only with selective dark survival
    light_body_loss_warn: float = 0.42
    light_body_loss_bad: float = 0.55
    # Multi-signal
    warn_to_uncertain: int = 2
    bad_signal_floor: int = 1  # any catastrophic → high_bad
    score_high_good: float = 72.0
    score_high_bad: float = 38.0


# Module-level defaults — override for calibration runs
GATE_CONFIG = QualityGateConfig()


def set_gate_config(cfg: QualityGateConfig | None = None) -> QualityGateConfig:
    global GATE_CONFIG
    GATE_CONFIG = cfg or QualityGateConfig()
    return GATE_CONFIG


def _fit_max_side(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    m = max(w, h)
    if m <= max_side:
        return img
    scale = max_side / m
    return img.resize(
        (max(1, int(w * scale)), max(1, int(h * scale))),
        Image.Resampling.BILINEAR,
    )


def open_rgb(path: Path | str, *, max_side: int | None = None) -> Image.Image:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in {".heic", ".heif"} and not HEIC_OK:
        raise RuntimeError(
            "HEIC file requires pillow-heif. Run: pip install pillow-heif"
        )

    if max_side is None:
        max_side = (
            WORKING_MAX_SIDE_HEIC
            if suffix in {".heic", ".heif"}
            else WORKING_MAX_SIDE
        )

    last_err: Exception | None = None
    for attempt_side in (max_side, WORKING_MAX_SIDE_OOM, 1280, 1024):
        img = None
        try:
            img = Image.open(path)
            try:
                img.draft("RGB", (attempt_side, attempt_side))
            except Exception:
                pass
            img = ImageOps.exif_transpose(img)
            if max(img.size) > attempt_side:
                img.thumbnail((attempt_side, attempt_side), Image.Resampling.BILINEAR)
            rgb = img.convert("RGB")
            if img is not rgb:
                try:
                    img.close()
                except Exception:
                    pass
            return rgb
        except (MemoryError, OSError, ValueError) as exc:
            last_err = exc
            try:
                if img is not None:
                    img.close()
            except Exception:
                pass
            gc.collect()
            continue
    raise RuntimeError(f"Failed to decode {path.name}: {last_err}") from last_err


def _is_oom(exc: BaseException) -> bool:
    if isinstance(exc, MemoryError):
        return True
    return _is_oom_text(str(exc))


def analyze_scene(rgb: Image.Image) -> dict[str, Any]:
    """Detect difficult scenes: bright, low-contrast, glossy/highlight-heavy."""
    arr = np.asarray(rgb, dtype=np.float32)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    mean_lum = float(lum.mean())
    std_lum = float(lum.std())
    p95 = float(np.percentile(lum, 95))
    p5 = float(np.percentile(lum, 5))
    highlight_frac = float(np.count_nonzero(lum >= 230) / lum.size)
    # Low chroma often = grey/silver/white plastic
    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    chroma = mx - mn
    low_chroma_frac = float(np.count_nonzero(chroma < 18) / chroma.size)

    bright_low_contrast = mean_lum >= 155.0 and std_lum <= 52.0
    mostly_highlights = p95 >= 242.0 and mean_lum >= 140.0
    glossy = highlight_frac >= 0.12 and std_lum >= 35.0
    pale_product = low_chroma_frac >= 0.55 and mean_lum >= 150.0
    narrow_range = (p95 - p5) < 55.0 and mean_lum >= 140.0
    # Grey / translucent packaging (plastic bags, frosted housings)
    grey_packaging = low_chroma_frac >= 0.85 and 90.0 <= mean_lum <= 175.0
    low_contrast_object = std_lum <= 48.0 and mean_lum >= 110.0 and low_chroma_frac >= 0.70

    difficult = bool(
        bright_low_contrast
        or mostly_highlights
        or glossy
        or pale_product
        or narrow_range
        or grey_packaging
        or low_contrast_object
    )
    return {
        "mean_lum": mean_lum,
        "std_lum": std_lum,
        "p95_lum": p95,
        "p5_lum": p5,
        "highlight_frac": highlight_frac,
        "low_chroma_frac": low_chroma_frac,
        "bright_low_contrast": bright_low_contrast,
        "mostly_highlights": mostly_highlights,
        "glossy": glossy,
        "pale_product": pale_product,
        "grey_packaging": grey_packaging,
        "low_contrast_object": low_contrast_object,
        "difficult": difficult,
    }


def prepare_infer_rgb(working: Image.Image, scene: dict[str, Any], *, boost: bool) -> Image.Image:
    """
    Optional infer-only contrast (never applied to final product colors).
    Helps white/silver objects separate from light backgrounds.
    """
    if not boost and not scene.get("difficult"):
        return working
    # Contrast only — do NOT raise exposure/brightness (washes product into bg)
    strength = 1.35 if scene.get("difficult") else 1.18
    out = ImageEnhance.Contrast(working).enhance(strength)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.5, percent=90, threshold=2))
    return out


def _product_bbox(
    binary: np.ndarray, *, margin: float = 0.04
) -> tuple[int, int, int, int] | None:
    """Tight bbox around True pixels + fractional margin. None if empty."""
    rows = np.any(binary, axis=1)
    cols = np.any(binary, axis=0)
    if not rows.any() or not cols.any():
        return None
    ys = np.flatnonzero(rows)
    xs = np.flatnonzero(cols)
    y0, y1 = int(ys[0]), int(ys[-1]) + 1
    x0, x1 = int(xs[0]), int(xs[-1]) + 1
    h, w = binary.shape[:2]
    pad_y = max(1, int((y1 - y0) * margin))
    pad_x = max(1, int((x1 - x0) * margin))
    return (
        max(0, y0 - pad_y),
        min(h, y1 + pad_y),
        max(0, x0 - pad_x),
        min(w, x1 + pad_x),
    )


def evaluate_mask_quality(
    mask: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, float]]:
    """
    Product-ROI mask gate. Returns (ok_enough_for_compose, primary_reason, stats).
    Catastrophic failures → False. Warnings recorded in stats['warn_count'].
    """
    from scipy import ndimage

    cfg = GATE_CONFIG
    difficult = bool(scene and scene.get("difficult"))
    arr = np.asarray(mask if mask.mode == "L" else mask.convert("L"), dtype=np.uint8)
    total = int(arr.size)
    soft = arr >= cfg.soft_alpha_min
    solid = arr >= cfg.solid_alpha_min
    fog = (arr >= cfg.soft_alpha_min) & (arr < cfg.fog_alpha_max)

    soft_n = int(np.count_nonzero(soft))
    solid_n = int(np.count_nonzero(solid))
    fog_n = int(np.count_nonzero(fog))
    soft_cov = soft_n / float(total)
    solid_cov = solid_n / float(total)
    stats: dict[str, float] = {
        "soft_coverage": soft_cov,
        "strong_coverage": solid_cov,
        "fog_ratio": (fog_n / float(soft_n)) if soft_n else 0.0,
        "mean_alpha_soft": float(arr[soft].mean()) if soft_n else 0.0,
        "mean_alpha_solid": float(arr[solid].mean()) if solid_n else 0.0,
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
    }
    warns: list[str] = []
    bads: list[str] = []
    posits: list[str] = []

    if soft_n == 0:
        stats["bad_count"] = 1.0
        return False, "empty_mask", stats
    # Frame-level catastrophic floors only (large white canvas is normal)
    if soft_cov < cfg.min_soft_cov_frame:
        bads.append("weak_mask_small_area")
    if solid_cov < cfg.min_solid_cov_frame:
        bads.append("weak_mask_low_opacity")
    if soft_cov > cfg.max_soft_cov_frame:
        bads.append("mask_near_full_frame")
    elif soft_cov > cfg.max_soft_cov_warn:
        # Boosted infer often swallows grey bags into a giant "solid" mask
        warns.append("mask_near_full_frame")

    solid_of_soft = solid_n / float(soft_n) if soft_n else 0.0
    fog_ratio = stats["fog_ratio"]
    stats["solid_of_soft"] = solid_of_soft

    bbox = _product_bbox(soft, margin=0.02)
    if bbox is None:
        stats["bad_count"] = 1.0
        return False, "empty_mask", stats
    y0, y1, x0, x1 = bbox
    roi_area = float(max(1, (y1 - y0) * (x1 - x0)))
    bbox_frac = roi_area / float(total)
    stats["bbox_frac"] = bbox_frac
    # ROI-relative fill (not full-canvas coverage)
    roi_fill = soft_n / roi_area
    stats["bbox_fill"] = float(roi_fill)
    stats["roi_fill"] = float(roi_fill)
    if soft_cov > 0.42 and roi_fill > 0.72:
        warns.append("mask_near_full_frame")

    min_fill = cfg.min_roi_fill_difficult if difficult else cfg.min_roi_fill
    # Sparse ROI is soft only — small products / kits must not hard-fail
    if roi_fill < 0.08 and soft_cov < 0.015:
        bads.append("foreground_fragmented")
    elif roi_fill < 0.12:
        warns.append("foreground_fragmented")
    elif roi_fill < min_fill:
        warns.append("foreground_fragmented")

    if fog_ratio >= cfg.fog_ratio_bad and solid_of_soft < 0.35:
        bads.append("foggy_soft_mask")
    elif fog_ratio >= cfg.fog_ratio_warn and solid_of_soft < 0.42:
        warns.append("foggy_soft_mask")

    if solid_of_soft < 0.18:
        bads.append("weak_mask_low_opacity")
    elif solid_of_soft < cfg.min_solid_of_soft:
        warns.append("weak_mask_low_opacity")

    min_mean_a = (
        cfg.min_mean_alpha_soft_difficult if difficult else cfg.min_mean_alpha_soft
    )
    if stats["mean_alpha_soft"] < min_mean_a - 25:
        bads.append("weak_mask_mean_alpha")
    elif stats["mean_alpha_soft"] < min_mean_a:
        warns.append("weak_mask_mean_alpha")

    aspect = max(y1 - y0, x1 - x0) / max(1, min(y1 - y0, x1 - x0))
    stats["bbox_aspect"] = float(aspect)
    if aspect > 16.0 and soft_cov < 0.06:
        bads.append("bbox_implausibly_thin")

    # Components: distinguish kit (MULTI_OBJECT) from spray noise
    solid_u8 = solid.astype(np.uint8)
    labeled, nlab = ndimage.label(solid_u8)
    if nlab >= 1 and solid_n > 0:
        sizes = np.asarray(
            ndimage.sum(solid_u8, labeled, index=np.arange(1, nlab + 1)),
            dtype=np.float64,
        )
        main = float(sizes.max()) if sizes.size else 0.0
        main_frac = main / float(solid_n)
        sig_thresh = max(120.0, cfg.min_sig_comp_frac * solid_n)
        significant = int(np.count_nonzero(sizes >= sig_thresh))
        tiny = int(np.count_nonzero((sizes > 0) & (sizes < max(40.0, 0.02 * solid_n))))
        stats["n_solid_components"] = float(nlab)
        stats["main_component_frac"] = main_frac
        stats["n_significant_components"] = float(significant)
        stats["n_tiny_components"] = float(tiny)

        # Legitimate multi-object kit: several sizable pieces
        kit = (
            2 <= significant <= 12
            and tiny <= max(8, significant * 2)
            and main_frac >= 0.08
        )
        # Spray noise: many components, tiny debris dominates
        spray = significant >= cfg.spray_comp_count and main_frac < 0.40 and tiny >= 12
        spray_extreme = nlab >= 25 and significant <= 3 and tiny >= 15

        if kit and not spray and not spray_extreme:
            posits.append("multi_object_ok")
            if significant >= 6 and main_frac < 0.25:
                warns.append("foreground_fragmented")
        elif spray or spray_extreme:
            bads.append("foreground_fragmented")
        elif significant >= 5 and main_frac < 0.22 and tiny >= 14:
            # Severe spray-like fragmentation only
            bads.append("foreground_fragmented")
        elif significant >= 3 and main_frac < 0.30 and tiny >= 8:
            warns.append("foreground_fragmented")
        elif significant >= 4 and main_frac < 0.28:
            warns.append("foreground_fragmented")

        if main_frac >= 0.85 and significant <= 2:
            posits.append("strong_main_component")
        elif kit:
            posits.append("strong_main_component")  # kit coherence

    # Extreme internal holes only — washers/gears are legitimate
    crop_solid = solid[y0:y1, x0:x1]
    if crop_solid.any():
        filled_solid = ndimage.binary_fill_holes(crop_solid)
        holes = filled_solid & (~crop_solid)
        hole_n = int(np.count_nonzero(holes))
        hole_frac = hole_n / float(max(int(np.count_nonzero(filled_solid)), 1))
        stats["hole_frac"] = float(hole_frac)
        stats["hole_pixels"] = float(hole_n)
        # Closed holes with solid ring → legitimate
        if 0.05 <= hole_frac <= 0.55 and hole_n >= 200 and solid_of_soft >= 0.45:
            posits.append("legitimate_holes")
        elif (
            hole_frac >= cfg.hole_frac_catastrophic
            and hole_n >= cfg.hole_pixels_catastrophic
            and solid_of_soft < 0.40
        ):
            # Mottled erase, not a clean washer hole
            bads.append("foreground_fragmented")
        elif hole_frac >= 0.45 and hole_n >= 12000 and solid_of_soft < 0.45:
            warns.append("foreground_fragmented")

    # Positive: solid opaque core
    if solid_of_soft >= 0.70 and stats["mean_alpha_soft"] >= 160:
        posits.append("opaque_core")
    if soft_cov >= 0.04 and soft_cov <= 0.45 and solid_of_soft >= 0.65:
        posits.append("plausible_coverage")

    stats["warn_count"] = float(len(warns))
    stats["bad_count"] = float(len(bads))
    stats["pos_count"] = float(len(posits))
    stats["warn_reasons"] = 0.0  # placeholder; reasons via return
    primary = (bads[0] if bads else (warns[0] if warns else "ok"))
    # ok for compose unless catastrophic empty-ish
    ok = soft_cov >= cfg.min_soft_cov_frame and "empty_mask" not in bads
    if bads and soft_cov < 0.012:
        ok = False
    # Attach reason lists for classify
    stats["_warns"] = warns  # type: ignore[assignment]
    stats["_bads"] = bads  # type: ignore[assignment]
    stats["_posits"] = posits  # type: ignore[assignment]
    return ok, primary, stats


def evaluate_cutout_quality(
    rgba: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
) -> tuple[bool, str, dict[str, float]]:
    """
    Gate on RGBA cutout BEFORE white composite / BEFORE synthetic shadow.
    Uses product ROI — not full-frame white ratio.
    """
    cfg = GATE_CONFIG
    difficult = bool(scene and scene.get("difficult"))
    arr = np.asarray(rgba, dtype=np.uint8)
    if arr.ndim != 3 or arr.shape[2] < 4:
        return False, "segmentation_unreliable", {"bad_count": 1.0}
    rgb = arr[:, :, :3].astype(np.float32)
    a = arr[:, :, 3]
    fg = a >= 40
    solid = a >= 160
    fog = (a >= 40) & (a < 150)
    fg_n = int(np.count_nonzero(fg))
    solid_n = int(np.count_nonzero(solid))
    fog_n = int(np.count_nonzero(fog))
    warns: list[str] = []
    bads: list[str] = []
    posits: list[str] = []
    stats: dict[str, float] = {
        "fg_frac": fg_n / float(a.size),
        "solid_frac": solid_n / float(a.size),
        "fog_of_fg": (fog_n / float(fg_n)) if fg_n else 1.0,
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
    }

    if fg_n < 80:
        bads.append("foreground_too_small")
        stats["bad_count"] = 1.0
        stats["_bads"] = bads  # type: ignore[assignment]
        stats["_warns"] = warns  # type: ignore[assignment]
        stats["_posits"] = posits  # type: ignore[assignment]
        return False, "foreground_too_small", stats

    bbox = _product_bbox(fg, margin=0.03)
    if bbox is None:
        return False, "foreground_too_small", stats
    y0, y1, x0, x1 = bbox
    roi_area = float(max(1, (y1 - y0) * (x1 - x0)))
    stats["roi_fg_fill"] = fg_n / roi_area
    stats["roi_solid_fill"] = solid_n / roi_area

    fog_of_fg = stats["fog_of_fg"]
    solid_of_fg = solid_n / float(fg_n) if fg_n else 0.0
    if fog_of_fg >= cfg.cutout_fog_of_fg_bad and solid_of_fg < 0.30:
        bads.append("foggy_alpha_edges")
    elif fog_of_fg >= cfg.cutout_fog_of_fg_warn and solid_of_fg < 0.38:
        warns.append("foggy_alpha_edges")

    if solid_n < 40:
        bads.append("foggy_alpha_edges")
    else:
        solid_rgb = rgb[solid]
        vis = float((255.0 - solid_rgb).max(axis=1).mean())
        std = float(solid_rgb.std())
        near_white = (
            (solid_rgb[:, 0] >= 245)
            & (solid_rgb[:, 1] >= 245)
            & (solid_rgb[:, 2] >= 245)
        )
        near_white_frac = float(np.count_nonzero(near_white) / solid_n)
        stats["visibility"] = vis
        stats["solid_std"] = std
        stats["near_white_in_solid"] = near_white_frac

        # Ghosted / dissolved — catastrophic
        if vis < cfg.cutout_vis_catastrophic:
            bads.append("product_faded")
        elif vis < 14.0 and near_white_frac >= 0.75:
            bads.append("product_faded")
        elif near_white_frac >= 0.90 and std < 10.0 and vis < 22.0:
            bads.append("product_faded")
        elif difficult and near_white_frac >= 0.85 and vis < 18.0:
            warns.append("product_faded")
        elif difficult and vis < 18.0 and std < 12.0:
            warns.append("low_object_contrast")

        # Dark / high-contrast products are typically excellent on white
        if vis >= 40.0 and solid_of_fg >= 0.55 and fog_of_fg < 0.35:
            posits.append("strong_visibility")
        if vis >= 80.0 and near_white_frac < 0.15:
            posits.append("dark_high_contrast")

    # Edge smoke: soft ring — only flag large milky halos (not rembg AA)
    if solid_n >= 80 and fg_n > solid_n:
        solid_img = Image.fromarray((solid.astype(np.uint8) * 255), mode="L")
        ring = np.asarray(solid_img.filter(ImageFilter.MaxFilter(5)), dtype=np.uint8) >= 128
        edge_band = ring & (~solid) & fg
        edge_n = int(np.count_nonzero(edge_band))
        if edge_n >= 80:
            edge_a = a[edge_band]
            edge_mean = float(edge_a.mean())
            edge_frac = edge_n / float(fg_n)
            stats["edge_band_mean_alpha"] = edge_mean
            stats["edge_band_frac"] = edge_frac
            # Distinguish AA fringe from milky cloud
            if edge_frac >= 0.35 and edge_mean < 85.0:
                bads.append("foggy_alpha_edges")
            elif edge_frac >= 0.28 and edge_mean < 90.0 and fog_of_fg >= 0.45:
                warns.append("foggy_alpha_edges")
            elif edge_frac < 0.15 and edge_mean >= 100:
                posits.append("coherent_edges")

    if stats.get("roi_solid_fill", 0) >= 0.45 and solid_of_fg >= 0.60:
        posits.append("solid_roi")

    stats["warn_count"] = float(len(warns))
    stats["bad_count"] = float(len(bads))
    stats["pos_count"] = float(len(posits))
    stats["_warns"] = warns  # type: ignore[assignment]
    stats["_bads"] = bads  # type: ignore[assignment]
    stats["_posits"] = posits  # type: ignore[assignment]
    primary = bads[0] if bads else (warns[0] if warns else "ok")
    ok = "foreground_too_small" not in bads and fg_n >= 80
    return ok, primary, stats


def evaluate_studio_quality(
    studio: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
    cutout_stats: dict[str, float] | None = None,
) -> tuple[bool, str, dict[str, float]]:
    """
    Final-canvas check on a NO-SHADOW composite only.
    Do NOT use full-canvas white ratio as a fail signal.
    Analyze product ROI; dark high-contrast products are favored.
    """
    from scipy import ndimage

    cfg = GATE_CONFIG
    difficult = bool(scene and scene.get("difficult"))
    arr = np.asarray(
        studio if studio.mode == "RGB" else studio.convert("RGB"), dtype=np.uint8
    )
    # Product = clearly not pure white (shadow must NOT be in this image)
    near_white = (
        (arr[:, :, 0] >= 250) & (arr[:, :, 1] >= 250) & (arr[:, :, 2] >= 250)
    )
    product = ~near_white
    prod_n = int(np.count_nonzero(product))
    frame = float(arr.shape[0] * arr.shape[1])
    warns: list[str] = []
    bads: list[str] = []
    posits: list[str] = []
    stats: dict[str, float] = {
        "product_frac": prod_n / frame,
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
    }
    if cutout_stats:
        stats.update(
            {
                f"cutout_{k}": float(v)
                for k, v in cutout_stats.items()
                if not str(k).startswith("_")
            }
        )

    # Catastrophic empty only — modest product on large canvas is OK
    if prod_n < 200 or stats["product_frac"] < 0.008:
        bads.append("final_too_white_small_product")
        stats["bad_count"] = 1.0
        stats["_bads"] = bads  # type: ignore[assignment]
        stats["_warns"] = warns  # type: ignore[assignment]
        stats["_posits"] = posits  # type: ignore[assignment]
        return False, "final_too_white_small_product", stats

    bbox = _product_bbox(product, margin=0.04)
    if bbox is None:
        return False, "final_too_white_small_product", stats
    y0, y1, x0, x1 = bbox
    roi = product[y0:y1, x0:x1]
    roi_arr = arr[y0:y1, x0:x1]
    roi_area = float(max(1, roi.size))
    roi_fill = float(np.count_nonzero(roi) / roi_area)
    stats["studio_roi_fill"] = roi_fill

    prod_px = arr[product].astype(np.float32)
    mean = float(prod_px.mean())
    std = float(prod_px.std())
    vis = float((255.0 - prod_px).max(axis=1).mean())
    stats["product_mean"] = mean
    stats["product_std"] = std
    stats["product_visibility"] = vis

    if vis < cfg.studio_vis_catastrophic:
        bads.append("final_washed_out")
    elif mean >= 248.0 and std <= 6.0:
        bads.append("final_washed_out")
    elif mean >= 244.0 and std <= 8.0 and vis < 14.0:
        bads.append("final_washed_out")
    elif difficult and vis < 16.0 and std <= 12.0 and roi_fill < 0.25:
        warns.append("final_bright_product_vanished")

    light_grey = (
        (prod_px[:, 0] >= 230)
        & (prod_px[:, 1] >= 230)
        & (prod_px[:, 2] >= 230)
    )
    lg_frac = float(np.count_nonzero(light_grey) / prod_n)
    stats["light_grey_frac"] = lg_frac
    # Ghost cloud in product ROI (not white canvas)
    if lg_frac >= 0.85 and std < 12.0 and vis < 22.0:
        bads.append("product_faded")
    elif lg_frac >= 0.80 and vis < 18.0 and std < 14.0:
        warns.append("product_faded")

    lum = (
        0.299 * arr[:, :, 0].astype(np.float32)
        + 0.587 * arr[:, :, 1].astype(np.float32)
        + 0.114 * arr[:, :, 2].astype(np.float32)
    )
    dark = (lum < cfg.dark_core_lum) & product
    dark_n = int(np.count_nonzero(dark))
    dark_frac = dark_n / frame
    stats["dark_frac"] = float(dark_frac)

    # Dark high-contrast = typically good ecommerce
    if dark_frac >= 0.04 and vis >= 50.0:
        posits.append("dark_on_white")
    if vis >= 40.0 and lg_frac < 0.25 and roi_fill >= 0.30:
        posits.append("readable_product")

    # Fragmentation: spray of tiny pieces — NOT 2–N legitimate kit parts
    if dark_n >= 800:
        dlab, dn = ndimage.label(dark.astype(np.uint8))
        if dn >= 2:
            dsizes = np.asarray(
                ndimage.sum(dark.astype(np.uint8), dlab, index=np.arange(1, dn + 1)),
                dtype=np.float64,
            )
            dmain = float(dsizes.max()) if dsizes.size else 0.0
            dmain_frac = dmain / float(dark_n) if dark_n else 0.0
            dsig_thresh = max(250.0, 0.08 * dark_n)
            dsig = int(np.count_nonzero(dsizes >= dsig_thresh))
            dtiny = int(
                np.count_nonzero((dsizes > 0) & (dsizes < max(80.0, 0.02 * dark_n)))
            )
            stats["n_dark_components"] = float(dsig)
            stats["main_dark_frac"] = dmain_frac
            stats["n_dark_tiny"] = float(dtiny)
            kit = 2 <= dsig <= 12 and dtiny <= max(6, dsig * 2) and dmain_frac >= 0.08
            spray = dsig >= 5 and dmain_frac < 0.35 and dtiny >= 10
            if kit and not spray:
                posits.append("multi_object_ok")
                if dsig <= 3 and dmain_frac >= 0.55:
                    posits.append("coherent_dark_core")
            elif spray or (dsig >= 8 and dmain_frac < 0.30):
                bads.append("foreground_fragmented")
            elif dsig >= 2 and dmain_frac < 0.35 and dtiny >= 12:
                # Broken single object with debris — not a clean kit
                bads.append("foreground_fragmented")
            elif dsig >= 2 and dmain_frac < cfg.dark_split_warn_frac and dtiny >= 6:
                warns.append("foreground_fragmented")
            elif dsig <= 2 and dmain_frac >= 0.70:
                posits.append("coherent_dark_core")

    # Mask-aware background QC: outside dilated product, ignore safety band
    try:
        band_iters = 6
        dilated = ndimage.binary_dilation(product, iterations=band_iters)
        bg_region = ~dilated
        bg_n = int(np.count_nonzero(bg_region))
        if bg_n >= 500:
            bg_rgb = arr[bg_region].astype(np.float32)
            # Dirty = not near-white outside safety band
            clean = (
                (bg_rgb[:, 0] >= 248)
                & (bg_rgb[:, 1] >= 248)
                & (bg_rgb[:, 2] >= 248)
            )
            dirty_frac = float(1.0 - (np.count_nonzero(clean) / bg_n))
            stats["bg_dirty_frac"] = dirty_frac
            # Shadow-like: dark low-sat in outer bg
            bg_lum = (
                0.299 * bg_rgb[:, 0]
                + 0.587 * bg_rgb[:, 1]
                + 0.114 * bg_rgb[:, 2]
            )
            bg_sat = bg_rgb.max(axis=1) - bg_rgb.min(axis=1)
            shadow_like = (bg_lum <= 55.0) & (bg_sat <= 28.0) & (~clean)
            stats["bg_shadow_frac"] = float(np.count_nonzero(shadow_like) / bg_n)
            if dirty_frac >= 0.06:
                warns.append("dirty_background")
            if float(stats["bg_shadow_frac"]) >= 0.045:
                warns.append("large_background_shadow")
        else:
            stats["bg_dirty_frac"] = 0.0
            stats["bg_shadow_frac"] = 0.0
    except Exception:
        stats["bg_dirty_frac"] = -1.0
        stats["bg_shadow_frac"] = -1.0

    # Edge haze for light/grey products only (dark edges vs white look "light")
    if dark_frac < 0.05:
        inner_edge = product & ndimage.binary_dilation(~product, iterations=2)
        edge_n = int(np.count_nonzero(inner_edge))
        if edge_n >= 300:
            edge_px = arr[inner_edge].astype(np.float32)
            light_edge = (
                (edge_px[:, 0] >= 215)
                & (edge_px[:, 1] >= 215)
                & (edge_px[:, 2] >= 215)
            )
            edge_light = float(np.count_nonzero(light_edge) / edge_n)
            stats["edge_inner_light_frac"] = edge_light
            if edge_light >= cfg.edge_haze_bad and lg_frac >= 0.45:
                bads.append("foggy_alpha_edges")
            elif edge_light >= 0.48 and difficult and lg_frac >= 0.40:
                warns.append("foggy_alpha_edges")

    stats["warn_count"] = float(len(warns))
    stats["bad_count"] = float(len(bads))
    stats["pos_count"] = float(len(posits))
    stats["_warns"] = warns  # type: ignore[assignment]
    stats["_bads"] = bads  # type: ignore[assignment]
    stats["_posits"] = posits  # type: ignore[assignment]
    primary = bads[0] if bads else (warns[0] if warns else "ok")
    ok = "final_too_white_small_product" not in bads
    return ok, primary, stats


def _sobel_mag(lum: np.ndarray) -> np.ndarray:
    """Cheap Sobel magnitude (float32)."""
    # pad to avoid border artifacts
    x = np.pad(lum.astype(np.float32), 1, mode="edge")
    gx = (x[1:-1, 2:] - x[1:-1, :-2]) * 0.5
    gy = (x[2:, 1:-1] - x[:-2, 1:-1]) * 0.5
    return np.sqrt(gx * gx + gy * gy)


def _local_std(lum: np.ndarray, win: int = 5) -> np.ndarray:
    """Box-filter local std via integral-like cumulative sums."""
    from scipy import ndimage

    mean = ndimage.uniform_filter(lum.astype(np.float32), size=win, mode="nearest")
    mean_sq = ndimage.uniform_filter(
        lum.astype(np.float32) ** 2, size=win, mode="nearest"
    )
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def evaluate_structure_consistency(
    source_rgb: Image.Image,
    rgba_cutout: Image.Image,
    *,
    scene: dict[str, Any] | None = None,
    features: Any = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Source↔output structural consistency inside product support ROI.

    Detects when segmentation erased substantial product structure
    (grey/translucent parts → white) while dark fragments remain.
    Does NOT compare full-canvas background texture.
    Optional `features` (RawFeatureCache) reuses RAW luma/edge/tex.
    """
    from scipy import ndimage

    cfg = GATE_CONFIG
    if features is not None:
        src = features.rgb
        lum_s = features.lum
        edge = features.edge
        tex = features.tex
    else:
        src = np.asarray(
            source_rgb if source_rgb.mode == "RGB" else source_rgb.convert("RGB"),
            dtype=np.uint8,
        )
        lum_s = (
            0.299 * src[:, :, 0].astype(np.float32)
            + 0.587 * src[:, :, 1].astype(np.float32)
            + 0.114 * src[:, :, 2].astype(np.float32)
        )
        edge = _sobel_mag(lum_s)
        tex = _local_std(lum_s, win=5)
    cut = np.asarray(rgba_cutout, dtype=np.uint8)
    if cut.ndim != 3 or cut.shape[2] < 4 or cut.shape[:2] != src.shape[:2]:
        if cut.shape[:2] != src.shape[:2] and cut.ndim == 3:
            # resize cutout alpha path shouldn't happen — fail soft
            pass
        return True, "ok", {"skipped": 1.0}

    alpha = cut[:, :, 3]
    rgb_out = cut[:, :, :3]
    soft = alpha >= cfg.soft_alpha_min

    warns: list[str] = []
    bads: list[str] = []
    posits: list[str] = []
    stats: dict[str, Any] = {
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
    }

    soft_n0 = int(np.count_nonzero(soft))
    if soft_n0 < 80:
        bads.append("catastrophic_structure_loss")
        stats["structure_loss"] = 1.0
        stats["_bads"] = bads
        stats["_warns"] = warns
        stats["_posits"] = posits
        stats["bad_count"] = 1.0
        return False, "catastrophic_structure_loss", stats

    # Product ROI from mask bbox (generous margin) — do NOT score distant background
    bbox = _product_bbox(soft, margin=0.28)
    if bbox is None:
        return True, "ok", stats
    y0, y1, x0, x1 = bbox
    h, w = soft.shape[:2]
    bh, bw = max(1, y1 - y0), max(1, x1 - x0)
    # Dilate soft so wiped grey neighbors of surviving dark cores are included
    dil_iters = int(min(80, max(18, 0.10 * max(bh, bw) / 3.0)))
    support = ndimage.binary_dilation(soft, iterations=dil_iters)
    roi = np.zeros_like(support)
    roi[y0:y1, x0:x1] = True
    support = support & roi

    near_white_src = (
        (src[:, :, 0] >= 248) & (src[:, :, 1] >= 248) & (src[:, :, 2] >= 248)
    )
    # Thresholds from surviving soft core (stable reference)
    core_ref = soft & roi
    if int(np.count_nonzero(core_ref)) >= 80:
        e_thr = float(np.percentile(edge[core_ref], 50))
        t_thr = float(np.percentile(tex[core_ref], 48))
    elif support.any():
        e_thr = float(np.percentile(edge[support], 58))
        t_thr = float(np.percentile(tex[support], 52))
    else:
        e_thr, t_thr = 8.0, 6.0
    e_thr = max(5.5, e_thr)
    t_thr = max(4.0, t_thr)

    # Structural prior: source edges/texture inside expanded product support
    prior = support & (~near_white_src) & ((edge >= e_thr) | (tex >= t_thr))
    prior_n = int(np.count_nonzero(prior))
    stats["prior_pixels"] = float(prior_n)
    stats["support_frac"] = float(np.count_nonzero(support)) / float(h * w)
    if prior_n < 200:
        # Mask remnants with almost no source structure nearby = collapsed product
        if soft_n0 >= 400:
            bads.append("catastrophic_structure_loss")
            stats["structure_loss"] = 0.85
            stats["edge_drop"] = 1.0
            stats["edge_retention"] = 0.0
            stats["bad_count"] = 1.0
            stats["_bads"] = bads
            stats["_warns"] = warns
            stats["_posits"] = posits
            return False, "catastrophic_structure_loss", stats
        return True, "ok", stats

    deleted = prior & (alpha < 80)
    deleted_n = int(np.count_nonzero(deleted))
    structure_loss = deleted_n / float(prior_n)
    stats["structure_loss"] = float(structure_loss)
    stats["deleted_prior"] = float(deleted_n)

    # Light/grey body (housings, bags) near the solid core — not outer dilation halo
    solid_core = alpha >= cfg.solid_alpha_min
    near_core = ndimage.binary_dilation(
        solid_core, iterations=max(10, min(40, dil_iters // 2))
    )
    light_zone = (
        support
        & near_core
        & (~near_white_src)
        & (lum_s >= 140)
        & (lum_s <= 230)
        & ((tex >= t_thr * 0.65) | (edge >= e_thr * 0.65))
    )
    lz_n = int(np.count_nonzero(light_zone))
    if lz_n >= 400:
        light_body_loss = int(np.count_nonzero(light_zone & (alpha < 80))) / float(lz_n)
    else:
        light_body_loss = 0.0
    stats["light_body_loss"] = float(light_body_loss)
    stats["light_body_pixels"] = float(lz_n)

    # Strong source edges in prior that lose alpha support
    strong_e = prior & (edge >= max(e_thr, float(np.percentile(edge[prior], 70))))
    strong_n = int(np.count_nonzero(strong_e))
    if strong_n >= 80:
        edge_drop = int(np.count_nonzero(strong_e & (alpha < 80))) / float(strong_n)
    else:
        edge_drop = 0.0
    stats["edge_drop"] = float(edge_drop)
    stats["edge_retention"] = float(1.0 - edge_drop)

    # Texture disappearance: textured prior → near-white in output or no alpha
    tex_prior = prior & (tex >= t_thr)
    tex_n = int(np.count_nonzero(tex_prior))
    if tex_n >= 80:
        out_white = (
            (rgb_out[:, :, 0] >= 245)
            & (rgb_out[:, :, 1] >= 245)
            & (rgb_out[:, :, 2] >= 245)
        )
        # On cutout RGB, deleted areas often show source still (pre-compose).
        # Prefer alpha loss; also flag when alpha gone and canvas would be white.
        tex_lost = tex_prior & (alpha < 80)
        texture_loss = int(np.count_nonzero(tex_lost)) / float(tex_n)
        stats["texture_to_white"] = float(
            np.count_nonzero(tex_prior & ((alpha < 80) | out_white))
        ) / float(tex_n)
    else:
        texture_loss = 0.0
        stats["texture_to_white"] = 0.0
    stats["texture_loss"] = float(texture_loss)

    # Grey/light product wipe: mid-luminance prior deleted more than dark prior
    mid = prior & (lum_s >= 90) & (lum_s <= 210)
    dark = prior & (lum_s < 90)
    mid_n = int(np.count_nonzero(mid))
    dark_n = int(np.count_nonzero(dark))
    mid_loss = (
        int(np.count_nonzero(mid & (alpha < 48))) / float(mid_n) if mid_n >= 100 else 0.0
    )
    dark_loss = (
        int(np.count_nonzero(dark & (alpha < 48))) / float(dark_n) if dark_n >= 100 else 0.0
    )
    stats["midtone_loss"] = float(mid_loss)
    stats["dark_loss"] = float(dark_loss)
    # Classic failure: greys wiped, dark fragments remain
    selective_wipe = mid_loss >= 0.40 and dark_loss <= 0.22 and mid_n >= 400
    # Light body wiped while dark core survives — require edge structure loss too
    # (highlights on dark plastics must not alone trip this)
    selective_light_wipe = (
        light_body_loss >= cfg.light_body_loss_bad
        and dark_loss <= 0.20
        and lz_n >= 1500
        and dark_n >= 200
        and structure_loss >= 0.20
        and mid_loss >= 0.28
    )

    # Connected prior blobs with little remaining alpha (shape collapse)
    labeled, nlab = ndimage.label(prior)
    collapsed = 0
    checked = 0
    if nlab > 0:
        sizes = ndimage.sum(prior, labeled, index=np.arange(1, nlab + 1))
        order = np.argsort(sizes)[::-1]
        for idx in order[:8]:
            lab = int(idx) + 1
            sz = float(sizes[idx])
            if sz < max(250.0, 0.04 * prior_n):
                continue
            checked += 1
            region = labeled == lab
            kept = float(np.count_nonzero(region & (alpha >= 80))) / sz
            if kept < 0.35:
                collapsed += 1
    stats["collapsed_regions"] = float(collapsed)
    stats["checked_regions"] = float(checked)
    shape_collapse = checked >= 2 and collapsed >= max(2, (checked + 1) // 2)

    if structure_loss >= cfg.struct_loss_bad or (
        edge_drop >= cfg.edge_drop_bad and texture_loss >= cfg.texture_loss_warn
    ):
        bads.append("catastrophic_structure_loss")
    elif selective_wipe and structure_loss >= cfg.struct_loss_warn:
        bads.append("catastrophic_structure_loss")
    elif selective_light_wipe:
        bads.append("catastrophic_structure_loss")
    elif shape_collapse and structure_loss >= cfg.struct_loss_warn:
        bads.append("catastrophic_structure_loss")
    elif structure_loss >= cfg.struct_loss_warn or edge_drop >= cfg.edge_drop_warn:
        warns.append("catastrophic_structure_loss")
    elif texture_loss >= cfg.texture_loss_bad:
        bads.append("catastrophic_structure_loss")
    elif texture_loss >= cfg.texture_loss_warn:
        warns.append("catastrophic_structure_loss")

    if structure_loss <= 0.12 and edge_drop <= 0.15:
        posits.append("structure_preserved")
    if stats["edge_retention"] >= 0.80 and structure_loss <= 0.18:
        posits.append("edges_retained")
    stats["warn_count"] = float(len(warns))
    stats["bad_count"] = float(len(bads))
    stats["pos_count"] = float(len(posits))
    stats["_warns"] = warns
    stats["_bads"] = bads
    stats["_posits"] = posits
    primary = bads[0] if bads else (warns[0] if warns else "ok")
    ok = "catastrophic_structure_loss" not in bads
    return ok, primary, stats


def classify_quality(
    mask_stats: dict[str, Any],
    cutout_stats: dict[str, Any],
    studio_stats: dict[str, Any],
    structure_stats: dict[str, Any] | None = None,
    *,
    raw_final_stats: dict[str, Any] | None = None,
    after_rescue: bool = False,
    filename: str = "",
) -> tuple[ConfidenceZone, float, list[str]]:
    """
    Weighted commercial QC → ConfidenceZone for Adaptive ladder.

    PASS        → high_good  → Approved
    SECOND_PASS → uncertain  → stronger rescue / re-QC
    REVIEW      → high_bad   → Review after rescue exhausted

    Instant reject only for severe failures (empty/washed/catastrophic structure).
    Soft warnings (centering, mild shadow, structure warn) are score penalties —
    they no longer force Review by themselves.
    Full report attached to studio_stats['_qc_report'] for diagnostics.
    """
    from .qc_engine import build_qc_report

    report = build_qc_report(
        mask_stats,
        cutout_stats,
        studio_stats,
        structure_stats,
        raw_final_stats=raw_final_stats,
        after_rescue=after_rescue,
        filename=filename,
    )
    # Attach for callers (_run_once → meta)
    if studio_stats is not None:
        studio_stats["_qc_report"] = report  # type: ignore[assignment]

    zone: ConfidenceZone = report["zone"]  # type: ignore[assignment]
    score = float(report["final_score"])
    # Reasons: prefer triggered rules + remaining bads/warns (explainable)
    reasons = list(report.get("bads") or []) + [
        t for t in (report.get("triggered_rules") or []) if not str(t).startswith("commercial_")
    ]
    reasons = list(dict.fromkeys(reasons))
    if zone == "high_good":
        return zone, score, []
    return zone, score, reasons or [str(report.get("reason") or "quality_uncertain")]


def segment_mask(
    working_rgb: Image.Image,
    *,
    max_side: int,
    model_name: str,
    infer_boost: bool = False,
    scene: dict[str, Any] | None = None,
) -> tuple[Image.Image, int, int]:
    from rembg import remove

    scene = scene or analyze_scene(working_rgb)

    def _run(name: str, side: int) -> tuple[Image.Image, int, int]:
        base = _fit_max_side(working_rgb, side)
        infer = prepare_infer_rgb(base, scene, boost=infer_boost)
        iw, ih = infer.size
        sess = get_session(name)
        with _infer_lock:
            mask = remove(infer, session=sess, only_mask=True, post_process_mask=False)
        if infer is not base:
            try:
                infer.close()
            except Exception:
                pass
        if base is not working_rgb:
            try:
                base.close()
            except Exception:
                pass
        if not isinstance(mask, Image.Image):
            mask = Image.open(io.BytesIO(mask))
        return mask.convert("L"), iw, ih

    try:
        mask_small, infer_w, infer_h = _run(model_name, max_side)
    except Exception as exc:
        if _is_oom(exc) and max_side > INFER_MAX_SIDE_OOM_RETRY:
            release_memory(empty_cuda_cache=True)
            mask_small, infer_w, infer_h = _run(model_name, INFER_MAX_SIDE_OOM_RETRY)
        else:
            release_memory()
            try:
                mask_small, infer_w, infer_h = _run(
                    FREE_FALLBACK_MODEL, min(max_side, 640)
                )
            except Exception:
                raise exc from None

    tw, th = working_rgb.size
    if mask_small.size != (tw, th):
        # Prefer keeping soft edges for light products (LANCZOS)
        mask = mask_small.resize((tw, th), Image.Resampling.LANCZOS)
        try:
            mask_small.close()
        except Exception:
            pass
    else:
        mask = mask_small
    return mask, infer_w, infer_h


def _expand_bbox(
    box: tuple[int, int, int, int],
    size: tuple[int, int],
    *,
    pad_frac: float = 0.18,
    min_pad: int = 16,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = box
    w, h = size
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    pad_x = max(min_pad, int(bw * pad_frac))
    pad_y = max(min_pad, int(bh * pad_frac))
    return (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(w, x1 + pad_x),
        min(h, y1 + pad_y),
    )


def segment_mask_roi(
    working_rgb: Image.Image,
    guide_mask: Image.Image | None,
    *,
    max_side: int,
    model_name: str,
    infer_boost: bool = True,
    scene: dict[str, Any] | None = None,
) -> tuple[Image.Image, int, int, dict[str, Any]]:
    """
    Strong rescue: crop product ROI → segment at higher effective resolution →
    paste mask back onto full working canvas. Falls back to full-frame on OOM/empty.
    """
    scene = scene or analyze_scene(working_rgb)
    tw, th = working_rgb.size
    meta: dict[str, Any] = {"roi_mode": True}

    box = None
    if guide_mask is not None:
        g_img = guide_mask if guide_mask.mode == "L" else guide_mask.convert("L")
        g = np.asarray(g_img, dtype=np.uint8)
        soft = g >= 24
        if soft.any():
            rows = np.any(soft, axis=1)
            cols = np.any(soft, axis=0)
            ys = np.flatnonzero(rows)
            xs = np.flatnonzero(cols)
            gx0, gy0 = int(xs[0]), int(ys[0])
            gx1, gy1 = int(xs[-1]) + 1, int(ys[-1]) + 1
            gw, gh = g_img.size
            if (gw, gh) != (tw, th) and gw > 0 and gh > 0:
                sx = tw / float(gw)
                sy = th / float(gh)
                box = (
                    int(gx0 * sx),
                    int(gy0 * sy),
                    int(gx1 * sx),
                    int(gy1 * sy),
                )
            else:
                box = (gx0, gy0, gx1, gy1)

    if box is None:
        # Center crop fallback — still better than full tiny downscale
        side = min(tw, th)
        cx, cy = tw // 2, th // 2
        half = side // 2
        box = (cx - half, cy - half, cx + half, cy + half)

    x0, y0, x1, y1 = _expand_bbox(box, (tw, th), pad_frac=0.20)
    meta["roi_box"] = f"{x0},{y0},{x1},{y1}"
    crop = working_rgb.crop((x0, y0, x1, y1))
    meta["roi_size"] = f"{crop.size[0]}x{crop.size[1]}"

    sides = [max_side]
    # Prefer safe sizes first on 4GB; escalate only if requested side is larger
    if max_side >= INFER_MAX_SIDE_ROI:
        sides = [INFER_MAX_SIDE_STRONG, INFER_MAX_SIDE_ROI]
    elif max_side > INFER_MAX_SIDE_STRONG:
        sides = [INFER_MAX_SIDE_STRONG, max_side]
    sides.extend([INFER_MAX_SIDE_QUALITY, INFER_MAX_SIDE_OOM_RETRY])
    sides = list(dict.fromkeys(s for s in sides if s > 0))

    last_exc: Exception | None = None
    mask_crop = None
    iw = ih = 0
    for side in sides:
        try:
            mask_crop, iw, ih = segment_mask(
                crop,
                max_side=side,
                model_name=model_name,
                infer_boost=infer_boost,
                scene=scene,
            )
            meta["roi_infer_side"] = side
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            release_memory(empty_cuda_cache=_is_oom(exc))
            continue

    if mask_crop is None:
        try:
            crop.close()
        except Exception:
            pass
        # Full-frame fallback
        mask, iw, ih = segment_mask(
            working_rgb,
            max_side=min(max_side, INFER_MAX_SIDE_STRONG),
            model_name=model_name,
            infer_boost=infer_boost,
            scene=scene,
        )
        meta["roi_mode"] = False
        meta["roi_fallback"] = str(last_exc or "empty")
        return mask, iw, ih, meta

    # Paste ROI mask into full canvas (prefer preserving uncertain pixels)
    full = Image.new("L", (tw, th), 0)
    if mask_crop.size != (x1 - x0, y1 - y0):
        mask_crop = mask_crop.resize((x1 - x0, y1 - y0), Image.Resampling.LANCZOS)
    full.paste(mask_crop, (x0, y0))
    try:
        mask_crop.close()
        crop.close()
    except Exception:
        pass

    # If prior guide had solid coverage where new ROI is empty, conserve it
    if guide_mask is not None:
        g = guide_mask.convert("L")
        if g.size != (tw, th):
            g = g.resize((tw, th), Image.Resampling.LANCZOS)
        ga = np.asarray(g, dtype=np.uint8)
        fa = np.asarray(full, dtype=np.uint8)
        fill = (fa < 40) & (ga >= 100)
        if fill.any():
            merged = fa.copy()
            merged[fill] = np.maximum(
                merged[fill],
                (ga[fill].astype(np.uint16) * 3 // 4).astype(np.uint8),
            )
            full = Image.fromarray(merged, mode="L")
        try:
            g.close()
        except Exception:
            pass

    return full, iw, ih, meta


def fortify_alpha(mask: Image.Image, *, strong: bool = False) -> Image.Image:
    """
    Preserve more mid-alpha so translucent / metallic edges don't dissolve on white.
    Strong path: mild dilate + lift soft midtones toward readable opacity.
    """
    arr = np.asarray(mask.convert("L"), dtype=np.uint8)
    if strong:
        # Expand 1px then restore soft falloff — keeps brush heads / clear plastic
        expanded = Image.fromarray(arr, mode="L").filter(ImageFilter.MaxFilter(3))
        arr = np.asarray(expanded, dtype=np.uint8)
        soft = (arr >= 28) & (arr < 170)
        if soft.any():
            lifted = arr.astype(np.float32)
            lifted[soft] = np.minimum(255.0, lifted[soft] * 1.22 + 18.0)
            arr = lifted.astype(np.uint8)
    return Image.fromarray(arr, mode="L")


def refine_rescue_alpha(mask: Image.Image) -> Image.Image:
    """
    Strong-rescue edge/alpha refinement: preserve uncertain product pixels,
    avoid erosion. Prefer residual background over deleting half the product.
    """
    arr = np.asarray(mask.convert("L"), dtype=np.float32)
    # Lift very weak product hints near stronger cores
    img = Image.fromarray(arr.astype(np.uint8), mode="L")
    dilated = np.asarray(img.filter(ImageFilter.MaxFilter(5)), dtype=np.float32)
    # Near core (dilated solid) but currently weak → raise alpha conservatively
    near_core = dilated >= 120
    weak = (arr >= 18) & (arr < 140) & near_core
    arr = arr.copy()
    arr[weak] = np.minimum(255.0, arr[weak] * 1.35 + 28.0)
    # Tiny anti-alias blur only on the band, not a global dissolve
    out = Image.fromarray(arr.astype(np.uint8), mode="L")
    out = out.filter(ImageFilter.GaussianBlur(0.45))
    # Re-fortify after blur
    return fortify_alpha(out, strong=True)


def apply_mask(
    rgb: Image.Image,
    mask: Image.Image,
    *,
    preserve_alpha: bool = False,
) -> Image.Image:
    rgba = rgb.convert("RGBA")
    alpha = mask.convert("L")
    if alpha.size != rgba.size:
        alpha = alpha.resize(rgba.size, Image.Resampling.LANCZOS)
    if preserve_alpha:
        alpha = fortify_alpha(alpha, strong=True)
    rgba.putalpha(alpha)
    return rgba


def _alpha_bbox(rgba: Image.Image, threshold: int = 8) -> tuple[int, int, int, int]:
    alpha = rgba.split()[-1]
    mask = alpha.point(lambda a: 255 if a > threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return (0, 0, rgba.width, rgba.height)
    return bbox


def _soft_shadow(
    alpha: Image.Image,
    *,
    blur: int = 28,
    opacity: float = 0.28,
    offset_y: int = 14,
) -> Image.Image:
    blur = max(8, min(int(blur), 36))
    shadow_a = alpha.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    scaled = shadow_a.point(lambda a: int(a * opacity))
    shadow.putalpha(scaled)
    canvas = Image.new("RGBA", (alpha.size[0], alpha.size[1] + offset_y), (0, 0, 0, 0))
    canvas.paste(shadow, (0, offset_y), shadow)
    return canvas


def clean_cutout_edges(rgba: Image.Image, *, gentle: bool = False) -> Image.Image:
    """
    Edge cleanup. Prefer false positives over dissolving the product.
    gentle=True: no MinFilter erosion (safer for white/silver).
    """
    r, g, b, a = rgba.split()
    if gentle:
        # Slightly expand then tiny blur — keep light product regions
        a = a.filter(ImageFilter.MaxFilter(3))
        a = a.filter(ImageFilter.GaussianBlur(0.6))
    else:
        # Mild open: max then min (less destructive than min-first)
        a = a.filter(ImageFilter.MaxFilter(3))
        a = a.filter(ImageFilter.MinFilter(3))
        a = a.filter(ImageFilter.GaussianBlur(0.7))
    out = Image.merge("RGB", (r, g, b)).convert("RGBA")
    out.putalpha(a)
    return out


def enhance_product(rgba: Image.Image, *, conservative: bool = False) -> Image.Image:
    """Conservative tonal tweak — never blow out white/silver midtones."""
    alpha = rgba.split()[-1]
    rgb = rgba.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)
    a = np.asarray(alpha, dtype=np.uint8)
    opaque = a >= 40
    if opaque.any():
        mean_lum = float(
            (
                0.299 * arr[:, :, 0][opaque]
                + 0.587 * arr[:, :, 1][opaque]
                + 0.114 * arr[:, :, 2][opaque]
            ).mean()
        )
    else:
        mean_lum = 128.0

    if conservative or mean_lum >= 195.0:
        # Bright / silver product: skip contrast boost (washes into white bg)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.04)
        rgb = ImageEnhance.Color(rgb).enhance(1.02)
    elif mean_lum >= 160.0:
        rgb = ImageEnhance.Contrast(rgb).enhance(1.04)
        rgb = ImageEnhance.Color(rgb).enhance(1.03)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.06)
    else:
        rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
        rgb = ImageEnhance.Color(rgb).enhance(1.05)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.08)

    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def compose_studio_square(
    rgba: Image.Image,
    *,
    size: int = 2000,
    product_fill: float = 0.84,
    with_shadow: bool = True,
    gentle_edges: bool = False,
    conservative_enhance: bool = False,
) -> Image.Image:
    rgba = rgba.convert("RGBA")
    rgba = clean_cutout_edges(rgba, gentle=gentle_edges)
    # Lower bbox threshold keeps faint bright edges
    bbox = _alpha_bbox(rgba, threshold=6 if gentle_edges else 8)
    cropped = rgba.crop(bbox)

    max_side = int(size * product_fill)
    w, h = cropped.size
    scale = min(max_side / max(1, w), max_side / max(1, h))
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    product = cropped.resize((new_w, new_h), Image.Resampling.LANCZOS)
    product = enhance_product(product, conservative=conservative_enhance)

    pad = 56 if with_shadow else 0
    layer_w = new_w + pad * 2
    layer_h = new_h + pad * 2 + (20 if with_shadow else 0)
    layer = Image.new("RGBA", (layer_w, layer_h), (0, 0, 0, 0))
    px, py = pad, pad
    if with_shadow:
        shadow = _soft_shadow(
            product.split()[-1],
            blur=max(18, new_w // 40),
            opacity=0.22,
            offset_y=max(10, new_h // 80),
        )
        layer.paste(shadow, (px, py), shadow)
    layer.paste(product, (px, py), product)

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    lx, ly = layer.size
    canvas.paste(layer, ((size - lx) // 2, (size - ly) // 2), layer)
    return canvas


def format_perf_block(timings: dict[str, float], meta: dict[str, Any]) -> str:
    lines = [
        "[PERF]",
        f"Decode: {timings.get('decode', 0):.2f}s",
        f"Preprocess: {timings.get('preprocess', 0):.2f}s",
        f"AI inference: {timings.get('infer', 0):.2f}s",
        f"Quality gate: {timings.get('gate', 0):.3f}s",
        f"Fallback infer: {timings.get('fallback_infer', 0):.2f}s",
        f"Mask postprocess: {timings.get('mask', 0):.2f}s",
        f"Composite: {timings.get('composite', 0):.2f}s",
        f"Save: {timings.get('save', 0):.2f}s",
        f"Total: {timings.get('total', 0):.2f}s",
        f"Device: {str(meta.get('device', '?')).upper()}",
        f"Path: {meta.get('path_label', '?')}",
    ]
    if meta.get("gpu_name"):
        lines.append(f"GPU: {meta['gpu_name']}")
    if meta.get("orig_size"):
        lines.append(f"Original size: {meta['orig_size']}")
    if meta.get("working_size"):
        lines.append(f"Working size: {meta['working_size']}")
    if meta.get("infer_size"):
        lines.append(f"AI inference size: {meta['infer_size']}")
    if meta.get("output_size"):
        lines.append(f"Output size: {meta['output_size']}")
    if meta.get("gate_reason"):
        lines.append(f"Gate: {meta['gate_reason']}")
    return "\n".join(lines)


def unique_jpg_path(folder: Path, stem: str) -> Path:
    """Avoid overwriting; never touches source files."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / f"{stem}.jpg"
    if not dest.exists():
        return dest
    n = 2
    while True:
        cand = folder / f"{stem}_{n}.jpg"
        if not cand.exists():
            return cand
        n += 1


def _normalize_reason(reason: str) -> str:
    r = reason.replace("mask_gate:", "").replace("studio_gate:", "").strip()
    low = r.lower()
    if "failed to decode" in low or "cannot identify image" in low:
        return "decode_failed"
    if "unsupported" in low and "format" in low:
        return "unsupported_format"
    if _is_oom_text(low):
        return "inference_oom"
    if "compose_failed" in low:
        return "compose_failed"
    mapping = {
        "weak_mask_small_area": "foreground_too_small",
        "weak_mask_low_opacity": "weak_mask",
        "weak_mask_mean_alpha": "weak_mask",
        "empty_mask": "weak_mask",
        "bbox_too_small": "foreground_too_small",
        "bbox_implausibly_thin": "foreground_fragmented",
        "mask_near_full_frame": "segmentation_unreliable",
        "bright_scene_weak_mask": "weak_mask",
        "foggy_soft_mask": "foggy_alpha_edges",
        "foggy_alpha_edges": "foggy_alpha_edges",
        "foreground_fragmented": "foreground_fragmented",
        "final_too_white_small_product": "product_faded",
        "final_washed_out": "product_faded",
        "final_bright_product_vanished": "product_faded",
        "product_faded": "product_faded",
        "low_object_contrast": "low_object_contrast",
        "catastrophic_structure_loss": "catastrophic_structure_loss",
        "quality_check_error": "quality_check_error",
        "rescue_failed": "rescue_failed",
        "decode_failed": "decode_failed",
        "source_unreadable": "source_unreadable",
        "fast_inference_failed_no_candidate": "fast_inference_failed_no_candidate",
        "final_save_failed": "final_save_failed",
        "unsupported_format": "unsupported_format",
        "no_candidate": "no_candidate",
    }
    if r in mapping:
        return mapping[r]
    if "onnxruntime" in low or "dmlfused" in low or "8007000e" in low:
        return "inference_oom" if _is_oom_text(low) else "inference_runtime_error"
    return (r[:120] if r else "segmentation_unreliable")


def _is_oom_text(text: str) -> bool:
    t = text.lower()
    return any(
        k in t
        for k in (
            "out of memory",
            "oom",
            "8007000e",
            "not enough memory",
            "failed to allocate",
            "bad allocation",
            "cuda_error_out_of_memory",
            "dml committed",
        )
    )


def _precise_fail_reason(exc: BaseException | None, *, stage: str = "") -> str:
    if exc is None:
        return "no_candidate"
    msg = str(exc)
    low = msg.lower()
    if stage == "decode" or "failed to decode" in low:
        if "unsupported" in low:
            return "unsupported_format"
        return "decode_failed"
    if "source not found" in low or "no such file" in low:
        return "source_unreadable"
    if _is_oom_text(low):
        return "inference_oom"
    if "compose_failed" in low:
        return "compose_failed"
    if "permission" in low:
        return "final_save_failed"
    return _normalize_reason(msg)


def _replace_candidate(
    slot: dict[str, Any] | None,
    *,
    studio: Image.Image,
    meta: dict[str, Any],
    reasons: list[str],
    label: str,
    model: str,
) -> dict[str, Any]:
    """Ownership transfer: close previous studio if different object."""
    if slot is not None:
        prev = slot.get("studio")
        if prev is not None and prev is not studio:
            try:
                prev.close()
            except Exception:
                pass
    return {
        "studio": studio,
        "meta": dict(meta),
        "reasons": list(reasons),
        "label": label,
        "model": model,
    }


def _sanitize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Drop internal list keys before cache/manifest."""
    return {k: v for k, v in stats.items() if not str(k).startswith("_")}


def _run_once(
    working: Image.Image,
    *,
    model_name: str,
    infer_max_side: int,
    size: int,
    with_shadow: bool,
    scene: dict[str, Any],
    infer_boost: bool,
    gentle_edges: bool,
    conservative_enhance: bool,
    preserve_alpha: bool = False,
    skip_compose_if_mask_fail: bool = False,
    use_roi: bool = False,
    guide_mask: Image.Image | None = None,
    after_rescue: bool = False,
) -> tuple[Image.Image | None, dict[str, Any], dict[str, float], bool, list[str]]:
    """
    Segment → mask/cutout/structure gates (product ROI, no shadow) → classify →
    compose final (optional contact shadow for presentation only).
    """
    timings: dict[str, float] = {}
    meta: dict[str, Any] = {}
    reasons: list[str] = []

    t0 = time.perf_counter()
    timings["preprocess"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    if use_roi:
        mask, iw, ih, roi_meta = segment_mask_roi(
            working,
            guide_mask,
            max_side=infer_max_side,
            model_name=model_name,
            infer_boost=infer_boost,
            scene=scene,
        )
        meta.update(roi_meta)
        # Conservative alpha on strong rescue
        mask = refine_rescue_alpha(mask)
    else:
        mask, iw, ih = segment_mask(
            working,
            max_side=infer_max_side,
            model_name=model_name,
            infer_boost=infer_boost,
            scene=scene,
        )
        if preserve_alpha:
            mask = fortify_alpha(mask, strong=True)
    timings["infer"] = time.perf_counter() - t0
    meta["infer_size"] = f"{iw}x{ih}"
    meta["model"] = model_name
    meta["use_roi"] = bool(use_roi)

    # Optional second segmentation when primary confidence is weak (non-ROI)
    try:
        from .processing import (
            DEFAULT_PROCESSING,
            score_mask_confidence,
            select_or_ensemble_masks,
        )

        seg_a = score_mask_confidence(mask, model_name=model_name, rgb=working)
        meta["seg_confidence"] = seg_a.confidence
        meta["seg_warnings"] = list(seg_a.warnings)
        cfg_p = DEFAULT_PROCESSING
        if (
            not use_roi
            and model_name == FREE_MODEL_FAST
            and seg_a.confidence < cfg_p.conf_second_model
            and seg_a.confidence >= 0.25
        ):
            t1 = time.perf_counter()
            try:
                mask_b, iw2, ih2 = segment_mask(
                    working,
                    max_side=max(infer_max_side, INFER_MAX_SIDE_QUALITY),
                    model_name=FREE_MODEL_QUALITY,
                    infer_boost=infer_boost or bool(scene.get("difficult")),
                    scene=scene,
                )
                seg_b = score_mask_confidence(
                    mask_b, model_name=FREE_MODEL_QUALITY, rgb=working
                )
                chosen = select_or_ensemble_masks(seg_a, seg_b, cfg=cfg_p)
                if chosen.mask is not mask:
                    try:
                        mask.close()
                    except Exception:
                        pass
                if chosen.mask is not mask_b:
                    try:
                        mask_b.close()
                    except Exception:
                        pass
                mask = chosen.mask
                meta["model"] = chosen.model_name
                meta["second_model_used"] = True
                meta["seg_confidence"] = chosen.confidence
                meta["seg_iou"] = (chosen.metrics or {}).get("iou")
                meta["infer_size"] = f"{iw2}x{ih2}"
                timings["fallback_infer"] = timings.get("fallback_infer", 0.0) + (
                    time.perf_counter() - t1
                )
            except Exception as exc:  # noqa: BLE001
                meta["second_model_error"] = str(exc)
                release_memory(empty_cuda_cache=_is_oom(exc))
    except Exception:
        pass

    # Keep a lightweight guide for subsequent ROI rescue (downscale)
    try:
        gw, gh = mask.size
        side = max(gw, gh)
        if side > 512:
            scale = 512.0 / float(side)
            guide = mask.resize(
                (max(1, int(gw * scale)), max(1, int(gh * scale))),
                Image.Resampling.BILINEAR,
            )
        else:
            guide = mask.copy()
        meta["_guide_mask"] = guide
    except Exception:
        pass

    t0 = time.perf_counter()
    ok_m, reason_m, mstats = evaluate_mask_quality(mask, scene=scene)
    timings["gate"] = time.perf_counter() - t0
    soft_cov = float(mstats.get("soft_coverage") or 0.0)
    if not ok_m and soft_cov < 0.008:
        try:
            mask.close()
        except Exception:
            pass
        raise RuntimeError(f"mask_gate:{reason_m}")
    if not ok_m and skip_compose_if_mask_fail and soft_cov < 0.02:
        reasons.append(_normalize_reason(reason_m))
        try:
            mask.close()
        except Exception:
            pass
        meta["mask_stats"] = _sanitize_stats(mstats)
        meta["gate_reason"] = ",".join(reasons)
        meta["foreground_ratio"] = soft_cov
        meta["confidence_zone"] = "high_bad"
        meta["quality_features"] = {
            "mask": _sanitize_stats(mstats),
            "zone": "high_bad",
        }
        return None, meta, timings, False, reasons

    # Studio engine: mask refine + edge/halo/color (legacy via GHATE_LEGACY_COMPOSE=1)
    use_studio = os.environ.get("GHATE_LEGACY_COMPOSE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }
    studio_profile = None
    studio_report_dict: dict[str, Any] = {}
    t0 = time.perf_counter()
    if use_studio:
        try:
            from .processing import DEFAULT_PROCESSING, build_studio_rgba

            rgba, studio_profile, studio_rep, _refined = build_studio_rgba(
                working,
                mask,
                scene=scene,
                model_name=model_name,
                cfg=DEFAULT_PROCESSING,
                skip_color=False,
            )
            studio_report_dict = studio_rep.to_dict()
            meta["studio_processing"] = studio_report_dict
            meta["product_profile"] = studio_report_dict.get("profile")
            if studio_profile is not None:
                gentle_edges = bool(gentle_edges or studio_profile.gentle_edges)
                conservative_enhance = bool(
                    conservative_enhance or studio_profile.conservative_color
                )
        except Exception as exc:  # noqa: BLE001
            # Fall back to legacy cutout — never fail the image solely on postprocess
            meta["studio_engine_fallback"] = str(exc)
            rgba = apply_mask(working, mask, preserve_alpha=False)
            use_studio = False
    else:
        rgba = apply_mask(working, mask, preserve_alpha=False)
    timings["mask"] = time.perf_counter() - t0
    try:
        mask.close()
    except Exception:
        pass

    t0 = time.perf_counter()
    ok_c, reason_c, cstats = evaluate_cutout_quality(rgba, scene=scene)
    timings["gate"] = timings.get("gate", 0.0) + (time.perf_counter() - t0)
    if not ok_c:
        fg_frac = float(cstats.get("fg_frac") or 0.0)
        if skip_compose_if_mask_fail and fg_frac < 0.02 and soft_cov < 0.025:
            reasons.append(_normalize_reason(reason_c))
            try:
                rgba.close()
            except Exception:
                pass
            meta["mask_stats"] = _sanitize_stats(mstats)
            meta["cutout_stats"] = _sanitize_stats(cstats)
            meta["gate_reason"] = ",".join(reasons)
            meta["foreground_ratio"] = soft_cov
            meta["confidence_zone"] = "high_bad"
            meta["quality_features"] = {
                "mask": _sanitize_stats(mstats),
                "cutout": _sanitize_stats(cstats),
                "zone": "high_bad",
            }
            return None, meta, timings, False, reasons

    # Source↔output structural consistency + studio gates (isolated — never lose cutout)
    t0 = time.perf_counter()
    quality_error: str | None = None
    ststats: dict[str, Any] = {
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
        "_warns": [],
        "_bads": [],
        "_posits": [],
    }
    sstats: dict[str, Any] = {
        "warn_count": 0.0,
        "bad_count": 0.0,
        "pos_count": 0.0,
        "_warns": [],
        "_bads": [],
        "_posits": [],
    }
    ok_st, reason_st = True, "ok"
    ok_s, reason_s = True, "ok"
    zone: ConfidenceZone = "uncertain"
    qscore = 50.0
    zone_reasons: list[str] = []
    qc_report: dict[str, Any] | None = None
    reuse_analysis_as_studio = False
    analysis = None  # type: ignore[assignment]
    try:
        t_st = time.perf_counter()
        # Shared RAW features for structure + RAW↔FINAL (compute once)
        raw_feats = None
        try:
            from .qc_features import build_raw_features

            raw_feats = build_raw_features(working, with_prior=True)
        except Exception:
            raw_feats = None
        ok_st, reason_st, ststats = evaluate_structure_consistency(
            working, rgba, scene=scene, features=raw_feats
        )
        timings["qc_structure"] = time.perf_counter() - t_st

        t_comp_a = time.perf_counter()
        if use_studio and studio_profile is not None:
            from .processing import DEFAULT_PROCESSING, compose_white_square

            analysis, _cinfo = compose_white_square(
                rgba,
                size=size,
                with_shadow=False,
                profile=studio_profile,
                cfg=DEFAULT_PROCESSING,
            )
        else:
            analysis = compose_studio_square(
                rgba,
                size=size,
                with_shadow=False,
                gentle_edges=gentle_edges or preserve_alpha or use_roi,
                conservative_enhance=conservative_enhance or preserve_alpha or use_roi,
            )
        timings["compose_analysis"] = time.perf_counter() - t_comp_a

        try:
            t_studio_q = time.perf_counter()
            ok_s, reason_s, sstats = evaluate_studio_quality(
                analysis, scene=scene, cutout_stats=_sanitize_stats(cstats)
            )
            timings["qc_studio"] = time.perf_counter() - t_studio_q
        finally:
            # Keep analysis for RAW↔FINAL and possibly reuse as final studio
            pass

        # Independent RAW vs FINAL integrity (does not trust processing mask alone)
        rfstats: dict[str, Any] = {}
        try:
            from .qc_raw_final import compute_raw_final_integrity

            t_rf = time.perf_counter()
            rfstats = compute_raw_final_integrity(
                working, rgba, studio_rgb=analysis, cfg=None, features=raw_feats
            )
            timings["qc_raw_final"] = time.perf_counter() - t_rf
            # Ambiguous spatial loss → alternate local segmentation verifier
            if (
                float(rfstats.get("spatial_loss_candidate") or 0.0) >= 0.5
                and str(rfstats.get("spatial_evidence_confidence") or "").upper()
                in {"LOW", "MEDIUM"}
                and float(rfstats.get("large_contiguous_foreground_loss") or 0.0) < 0.5
            ):
                try:
                    from .qc_spatial_verify import verify_ambiguous_spatial_loss

                    t_sv = time.perf_counter()
                    rfstats = verify_ambiguous_spatial_loss(
                        working,
                        rgba,
                        rfstats,
                        primary_model=str(meta.get("model") or ""),
                        max_side=512,
                    )
                    timings["qc_spatial_verify"] = time.perf_counter() - t_sv
                except Exception as sv_exc:  # noqa: BLE001
                    rfstats.setdefault("_triggered", []).append(
                        f"spatial_verifier_skip:{type(sv_exc).__name__}"
                    )
                    rfstats.pop("_lost_grid", None)
                    rfstats.pop("_evidence", None)
                    timings["qc_spatial_verify"] = 0.0
            else:
                rfstats.pop("_lost_grid", None)
                rfstats.pop("_evidence", None)
        except Exception as rf_exc:  # noqa: BLE001
            rfstats = {
                "structure_preservation_score": 70.0,
                "detail_retention_score": 70.0,
                "raw_final_edge_consistency_score": 70.0,
                "foreground_overexposure_score": 75.0,
                "raw_final_integrity": 70.0,
                "_bads": [],
                "_warns": ["raw_final_compute_error"],
                "_posits": [],
                "_triggered": [f"raw_final_error:{rf_exc}"],
            }
            timings["qc_raw_final"] = 0.0
        # If final composite needs no shadow, reuse analysis canvas (identical compose)
        reuse_analysis_as_studio = not with_shadow
        if not reuse_analysis_as_studio:
            try:
                analysis.close()
            except Exception:
                pass
            analysis = None  # type: ignore[assignment]

        t_cls = time.perf_counter()
        zone, qscore, zone_reasons = classify_quality(
            mstats,
            cstats,
            sstats,
            structure_stats=ststats,
            raw_final_stats=rfstats,
            after_rescue=after_rescue or use_roi,
        )
        timings["qc_classify"] = time.perf_counter() - t_cls
        qc_report = (sstats or {}).pop("_qc_report", None)
        meta["raw_final_stats"] = _sanitize_stats(rfstats)
    except Exception as exc:  # noqa: BLE001
        # Quality analysis crashed — keep the cutout; send toward Review
        quality_error = str(exc)
        reuse_analysis_as_studio = False
        ststats = {
            "warn_count": 1.0,
            "bad_count": 0.0,
            "pos_count": 0.0,
            "_warns": ["quality_check_error"],
            "_bads": [],
            "_posits": [],
            "quality_check_error": 1.0,
        }
        sstats = {
            "warn_count": 1.0,
            "bad_count": 0.0,
            "pos_count": 0.0,
            "_warns": ["quality_check_error"],
            "_bads": [],
            "_posits": [],
        }
        zone, qscore, zone_reasons = "uncertain", 40.0, ["quality_check_error"]
        ok_st, reason_st = False, "quality_check_error"
        ok_s, reason_s = False, "quality_check_error"
        qc_report = None
        meta["raw_final_stats"] = {}
        try:
            analysis.close()  # type: ignore[name-defined]
        except Exception:
            pass
        analysis = None  # type: ignore[assignment]
    timings["gate"] = timings.get("gate", 0.0) + (time.perf_counter() - t0)

    meta["mask_stats"] = _sanitize_stats(mstats)
    meta["cutout_stats"] = _sanitize_stats(cstats)
    meta["studio_stats"] = _sanitize_stats(sstats)
    meta["structure_stats"] = _sanitize_stats(ststats)
    meta["confidence_zone"] = zone
    meta["quality_score"] = qscore
    meta["qc_decision"] = (
        (qc_report or {}).get("decision")
        or ("pass" if zone == "high_good" else "second_pass" if zone == "uncertain" else "review")
    )
    if qc_report:
        meta["qc_diagnostics"] = {
            k: v
            for k, v in qc_report.items()
            if k not in ("bads", "warns", "posits")
        }
        # Keep lists too for debugging
        meta["qc_diagnostics"]["bads"] = list(qc_report.get("bads") or [])
        meta["qc_diagnostics"]["warns"] = list(qc_report.get("warns") or [])
        meta["qc_diagnostics"]["posits"] = list(qc_report.get("posits") or [])
    if quality_error:
        meta["quality_check_error"] = quality_error
    # Feature log for future lightweight QC classifier
    meta["quality_features"] = {
        "mask": meta["mask_stats"],
        "cutout": meta["cutout_stats"],
        "studio": meta["studio_stats"],
        "structure": meta["structure_stats"],
        "edge_retention": float(ststats.get("edge_retention") or 0.0),
        "structure_loss": float(ststats.get("structure_loss") or 0.0),
        "mean_alpha_soft": float(mstats.get("mean_alpha_soft") or 0.0),
        "roi_fill": float(mstats.get("roi_fill") or 0.0),
        "zone": zone,
        "score": qscore,
        "qc_decision": meta["qc_decision"],
        "use_roi": bool(use_roi),
        "model": model_name,
        "quality_check_error": 1.0 if quality_error else 0.0,
    }

    gate_ok = zone == "high_good" and not quality_error
    if not gate_ok:
        reasons = [_normalize_reason(r) for r in zone_reasons] or [
            _normalize_reason(
                reason_st
                if not ok_st
                else reason_m
                if not ok_m
                else reason_c
                if not ok_c
                else reason_s
            )
        ]
        if quality_error:
            reasons = list(dict.fromkeys(["quality_check_error"] + reasons))
        reasons = list(dict.fromkeys(reasons))

    # Final presentation composite (shadow is display-only)
    t1 = time.perf_counter()
    try:
        if reuse_analysis_as_studio and analysis is not None:
            studio = analysis
            timings["composite_reused"] = 1.0
            if meta.get("studio_processing"):
                meta["studio_processing"]["composition"] = {
                    "reused_analysis_canvas": True,
                    "with_shadow": False,
                }
        elif use_studio and studio_profile is not None:
            from .processing import DEFAULT_PROCESSING, compose_white_square

            studio, cinfo_final = compose_white_square(
                rgba,
                size=size,
                with_shadow=with_shadow,
                profile=studio_profile,
                cfg=DEFAULT_PROCESSING,
            )
            if meta.get("studio_processing"):
                meta["studio_processing"]["composition"] = cinfo_final
        else:
            studio = compose_studio_square(
                rgba,
                size=size,
                with_shadow=with_shadow,
                gentle_edges=gentle_edges or preserve_alpha or use_roi,
                conservative_enhance=conservative_enhance or preserve_alpha or use_roi,
            )
    except Exception as exc:  # noqa: BLE001
        # Last-resort compose without enhance
        try:
            studio = compose_studio_square(
                rgba,
                size=size,
                with_shadow=False,
                gentle_edges=True,
                conservative_enhance=False,
            )
            reasons = list(
                dict.fromkeys((reasons or []) + ["postprocess_error"])
            )
            gate_ok = False
            meta["postprocess_error"] = str(exc)
        except Exception as exc2:  # noqa: BLE001
            try:
                rgba.close()
            except Exception:
                pass
            raise RuntimeError(f"compose_failed:{exc2}") from exc2
    timings["composite"] = time.perf_counter() - t1
    try:
        rgba.close()
    except Exception:
        pass

    # Optional debug dump
    if os.environ.get("GHATE_DEBUG", "").strip().lower() in {"1", "true", "yes"}:
        try:
            from .processing.debug_io import save_debug_bundle

            dbg = Path(os.environ.get("GHATE_DEBUG_DIR", "output/debug"))
            stem = str(meta.get("review_id") or meta.get("model") or "frame")
            save_debug_bundle(
                dbg / stem,
                final=studio,
                analysis={
                    "studio_processing": meta.get("studio_processing"),
                    "gate_reason": meta.get("gate_reason"),
                    "qc_decision": meta.get("qc_decision"),
                },
            )
            meta["debug_dir"] = str(dbg / stem)
        except Exception:
            pass

    meta["gate_reason"] = "ok" if gate_ok else ",".join(reasons) or "unreliable"
    meta["foreground_ratio"] = float(
        mstats.get("roi_fill")
        or mstats.get("soft_coverage")
        or cstats.get("roi_fg_fill")
        or cstats.get("fg_frac")
        or 0.0
    )
    # Uncertain/high_bad: keep studio for Review candidate / next attempt
    return studio, meta, timings, gate_ok, reasons


def _record_processing_report(
    *,
    output_root: Path,
    filename: str,
    status: str,
    meta: dict[str, Any] | None,
    timings: dict[str, float] | None,
) -> None:
    try:
        from .processing.report import append_jsonl, build_report_row, write_csv_from_jsonl

        row = build_report_row(
            filename=filename,
            status=status,
            meta=meta,
            timings=timings,
            pipeline_version=FREE_PIPELINE_VERSION,
        )
        jl = Path(output_root) / "processing_report.jsonl"
        append_jsonl(jl, row)
        write_csv_from_jsonl(jl, Path(output_root) / "processing_report.csv")
    except Exception:
        pass


def process_free_file(
    src: Path | str,
    dest: Path | str,
    *,
    size: int = 2000,
    with_shadow: bool = True,
    quality: int = 90,
    model_name: str = FREE_MODEL_FAST,
    infer_max_side: int | None = None,
    free_mode: FreeMode = "adaptive",
    review_dir: Path | str | None = None,
    review_id: str | None = None,
    known_review_ids: set[str] | None = None,
    package_review: bool = True,
    working: Image.Image | None = None,
    scene: dict[str, Any] | None = None,
    perf_log: list[str] | None = None,
    status_log: list[str] | None = None,
) -> dict[str, Any]:
    """
    Process one image (streaming-friendly).
    Optional working/scene: skip re-decode when prefetch already loaded the image.
    Saves ONCE to Approved or Review after in-memory gates — never reopen from disk.
    Review: Edited JPG + COPY of original under Review/Original/ + manifest row.
    Source files are never moved/modified.
    """
    from .review_io import finalize_review_package, make_stable_id

    src_path = Path(src)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    review_root = Path(review_dir) if review_dir else dest_path.parent.parent / REVIEW_DIR_NAME
    # If dest is .../Approved/x.jpg, output root is parent of Approved
    output_root = dest_path.parent.parent if dest_path.parent.name.lower() == APPROVED_DIR_NAME.lower() else dest_path.parent
    if review_dir is None:
        review_root = output_root / REVIEW_DIR_NAME
    name = src_path.name
    rid = review_id or make_stable_id(src_path)

    device = detect_device()
    timings_all: dict[str, float] = {
        "decode": 0.0,
        "infer": 0.0,
        "fallback_infer": 0.0,
        "gate": 0.0,
    }
    meta: dict[str, Any] = {
        "device": device.get("device", "cpu"),
        "gpu_name": device.get("gpu_name"),
        "review_id": rid,
    }
    t_all = time.perf_counter()
    own_working = working is None
    studio = None
    last_valid: dict[str, Any] | None = None  # last usable rendered candidate
    proc_state: ImageProcState = "pending"
    fail_stage = ""
    last_err: Exception | None = None
    rescue_crashed = False
    quality_check_errored = False

    if model_name == FREE_MODEL_QUALITY and free_mode == "adaptive":
        free_mode = "quality"

    def _failed_result(reason: str) -> dict[str, Any]:
        timings_all["total"] = time.perf_counter() - t_all
        if status_log is not None and not any("[FAILED]" in s for s in status_log):
            status_log.append(f"[FAILED] {name}\nReason: {reason}")
        _record_processing_report(
            output_root=output_root,
            filename=name,
            status="failed",
            meta={**meta, "fail_reason": reason},
            timings=timings_all,
        )
        return {
            "status": "failed",
            "path": None,
            "reasons": [reason],
            "path_label": "FAILED",
            "fallback_used": False,
            "review_id": rid,
            "error": reason,
            "fail_reason": reason,
            "proc_state": "failed",
            "timings": timings_all,
            "edit_sec": timings_all.get("total", 0.0),
        }

    def _review_from_candidate(
        cand: dict[str, Any],
        *,
        reasons: list[str],
        fallback_used_flag: bool,
        first_failed: bool,
    ) -> dict[str, Any]:
        nonlocal studio
        review_meta = cand.get("meta") or {}
        meta.update(review_meta)
        meta["path_label"] = "REVIEW"
        studio = cand["studio"]
        reasons = list(dict.fromkeys(reasons))
        metrics = {
            "foreground_ratio": review_meta.get("foreground_ratio")
            or meta.get("foreground_ratio"),
            "mask_stats": review_meta.get("mask_stats") or meta.get("mask_stats"),
            "cutout_stats": review_meta.get("cutout_stats")
            or meta.get("cutout_stats"),
            "studio_stats": review_meta.get("studio_stats")
            or meta.get("studio_stats"),
            "structure_stats": review_meta.get("structure_stats")
            or meta.get("structure_stats"),
            "model": cand.get("model") or review_meta.get("model"),
        }
        timings_all["total"] = time.perf_counter() - t_all
        out_path: Path | None = None
        copy_err = None
        manifest_err = None
        if package_review:
            try:
                pkg = finalize_review_package(
                    output_dir=output_root,
                    source_path=src_path,
                    edited_image=studio,
                    review_id=rid,
                    reasons=reasons,
                    processing_mode=free_mode,
                    fallback_used=fallback_used_flag,
                    quality_metrics=metrics,
                    processing_time=timings_all.get("total"),
                    jpeg_quality=quality,
                    known_ids=known_review_ids,
                )
                out_path = Path(pkg["edited_path"])
                copy_err = pkg.get("original_copy_error")
                manifest_err = pkg.get("manifest_error")
            except Exception as exc:  # noqa: BLE001
                # Edited save must still be attempted directly
                try:
                    from .review_io import ensure_output_layout, review_edited_dir

                    ensure_output_layout(output_root)
                    out_path = review_edited_dir(output_root) / f"{rid}.jpg"
                    studio.save(out_path, "JPEG", quality=quality, optimize=False)
                    copy_err = f"review_package_error:{exc}"
                except Exception as exc2:  # noqa: BLE001
                    return _failed_result(_precise_fail_reason(exc2, stage="save"))
        else:
            try:
                out_path = dest_path.parent / f"{rid}_review.jpg"
                studio.save(out_path, "JPEG", quality=quality, optimize=False)
            except Exception as exc:  # noqa: BLE001
                return _failed_result(_precise_fail_reason(exc, stage="save"))

        if copy_err and status_log is not None:
            status_log.append(f"[REVIEW] original_copy_error: {copy_err}")
        if manifest_err and status_log is not None:
            status_log.append(f"[REVIEW] manifest_error: {manifest_err}")
        try:
            from .qc_engine import write_qc_diagnostics

            diag = meta.get("qc_diagnostics") or review_meta.get("qc_diagnostics")
            if isinstance(diag, dict):
                diag = {
                    **diag,
                    "file": name,
                    "folder_status": "review",
                    # Keep engine decision (pass/second_pass/review) for diagnostics
                    "engine_decision": diag.get("decision"),
                    "decision": diag.get("decision") or "review",
                    "review_id": rid,
                    "reasons": reasons,
                }
                write_qc_diagnostics(diag, output_root=output_root, review_id=rid)
        except Exception:
            pass
        if status_log is not None:
            status_log.append(
                f"[REVIEW] {name}\nID: {rid}\nReason: {','.join(reasons)}"
            )
        if perf_log is not None:
            perf_log.append(format_perf_block(timings_all, meta))
        _record_processing_report(
            output_root=output_root,
            filename=name,
            status="review",
            meta=meta,
            timings=timings_all,
        )
        return {
            "status": "review",
            "path": out_path,
            "reasons": reasons,
            "path_label": "REVIEW",
            "fallback_used": fallback_used_flag,
            "fallback_rescued": False,
            "fast_failed": first_failed or True,
            "review_id": rid,
            "review_original_path": None,
            "review_original_copy_error": copy_err,
            "manifest_error": manifest_err,
            "model": cand.get("model") or review_meta.get("model"),
            "foreground_ratio": review_meta.get("foreground_ratio")
            or meta.get("foreground_ratio"),
            "mask_stats": review_meta.get("mask_stats"),
            "studio_stats": review_meta.get("studio_stats"),
            "cutout_stats": review_meta.get("cutout_stats"),
            "structure_stats": review_meta.get("structure_stats")
            or meta.get("structure_stats"),
            "quality_features": review_meta.get("quality_features")
            or meta.get("quality_features"),
            "studio_processing": meta.get("studio_processing")
            or review_meta.get("studio_processing"),
            "product_profile": meta.get("product_profile")
            or review_meta.get("product_profile"),
            "proc_state": "review",
            "timings": timings_all,
            "edit_sec": timings_all.get("total", 0.0),
            "qc_decision": meta.get("qc_decision")
            or review_meta.get("qc_decision")
            or "review",
            "quality_score": meta.get("quality_score")
            or review_meta.get("quality_score"),
            "raw_final_stats": meta.get("raw_final_stats")
            or review_meta.get("raw_final_stats"),
            "qc_diagnostics": meta.get("qc_diagnostics")
            or review_meta.get("qc_diagnostics"),
            "meta": {
                "qc_decision": meta.get("qc_decision") or review_meta.get("qc_decision"),
                "quality_score": meta.get("quality_score")
                or review_meta.get("quality_score"),
                "raw_final_stats": meta.get("raw_final_stats")
                or review_meta.get("raw_final_stats"),
                "qc_diagnostics": meta.get("qc_diagnostics")
                or review_meta.get("qc_diagnostics"),
                "confidence_zone": meta.get("confidence_zone")
                or review_meta.get("confidence_zone"),
                "model": meta.get("model") or review_meta.get("model"),
            },
        }

    # --- DECODE ---
    try:
        if working is None:
            t0 = time.perf_counter()
            working = open_rgb(src_path)
            timings_all["decode"] = time.perf_counter() - t0
        if scene is None:
            scene = analyze_scene(working)
        meta["orig_size"] = f"{working.size[0]}x{working.size[1]}"
        meta["working_size"] = meta["orig_size"]
        proc_state = "decoded"
    except Exception as exc:  # noqa: BLE001
        return _failed_result(_precise_fail_reason(exc, stage="decode"))

    try:
        attempts: list[dict[str, Any]] = []
        difficult = bool(scene.get("difficult"))
        if free_mode == "quality":
            attempts.append(
                {
                    "label": "QUALITY",
                    "model": FREE_MODEL_QUALITY,
                    "side": INFER_MAX_SIDE_QUALITY,
                    "boost": True,
                    "gentle": True,
                    "conservative": True,
                    "preserve_alpha": True,
                    "use_roi": False,
                }
            )
            attempts.append(
                {
                    "label": "FALLBACK",
                    "model": FREE_MODEL_QUALITY,
                    "side": INFER_MAX_SIDE_STRONG,
                    "boost": True,
                    "gentle": True,
                    "conservative": True,
                    "preserve_alpha": True,
                    "use_roi": True,
                }
            )
        elif free_mode == "fast":
            attempts.append(
                {
                    "label": "FAST",
                    "model": FREE_MODEL_FAST,
                    "side": infer_max_side or INFER_MAX_SIDE_FAST,
                    "boost": difficult,
                    "gentle": difficult,
                    "conservative": difficult,
                    "preserve_alpha": difficult,
                    "use_roi": False,
                }
            )
        else:
            # Adaptive: FAST → strong u2net → BiRefNet → ROI BiRefNet
            attempts.append(
                {
                    "label": "FAST",
                    "model": FREE_MODEL_FAST,
                    "side": INFER_MAX_SIDE_FAST,
                    "boost": difficult,
                    "gentle": difficult,
                    "conservative": difficult,
                    "preserve_alpha": difficult,
                    "use_roi": False,
                }
            )
            attempts.append(
                {
                    "label": "FALLBACK",
                    "model": FREE_MODEL_FAST,
                    "side": INFER_MAX_SIDE_STRONG,
                    "boost": True,
                    "gentle": True,
                    "conservative": True,
                    "preserve_alpha": True,
                    "use_roi": False,
                }
            )
            attempts.append(
                {
                    "label": "FALLBACK",
                    "model": FREE_MODEL_QUALITY,
                    "side": INFER_MAX_SIDE_QUALITY,
                    "boost": True,
                    "gentle": True,
                    "conservative": True,
                    "preserve_alpha": True,
                    "use_roi": False,
                }
            )
            attempts.append(
                {
                    "label": "FALLBACK",
                    "model": FREE_MODEL_QUALITY,
                    "side": INFER_MAX_SIDE_STRONG,
                    "boost": True,
                    "gentle": True,
                    "conservative": True,
                    "preserve_alpha": True,
                    "use_roi": True,
                }
            )

        used_label = "FAST"
        fallback_used = False
        n_attempts = len(attempts)
        first_attempt_failed = False
        guide_mask: Image.Image | None = None
        saw_struct_catastrophe = False

        for i, att in enumerate(attempts):
            is_last = i == n_attempts - 1
            is_rescue = i > 0
            if is_rescue:
                fallback_used = True
                proc_state = "rescue_attempted"
                if status_log is not None:
                    reason = ""
                    if last_err is not None:
                        reason = _normalize_reason(str(last_err))
                    elif last_valid:
                        reason = ",".join(last_valid.get("reasons") or []) or "weak_mask"
                    fb = att["model"]
                    if att.get("use_roi"):
                        fb = f"{fb}+ROI@{att['side']}"
                    status_log.append(
                        f"[SECOND_PASS] {name}\nReason: {reason or 'borderline'}\n"
                        f"Fallback: {fb}"
                    )
            try:
                cand, run_meta, run_t, gate_ok, reasons = _run_once(
                    working,
                    model_name=att["model"],
                    infer_max_side=att["side"],
                    size=size,
                    with_shadow=with_shadow,
                    scene=scene,
                    infer_boost=bool(att["boost"]),
                    gentle_edges=bool(att["gentle"]),
                    conservative_enhance=bool(att["conservative"]),
                    preserve_alpha=bool(att.get("preserve_alpha", False)),
                    skip_compose_if_mask_fail=not is_last,
                    use_roi=bool(att.get("use_roi", False)),
                    guide_mask=guide_mask,
                    after_rescue=is_rescue,
                )
                if run_meta.get("quality_check_error"):
                    quality_check_errored = True
                # Update ROI guide from this attempt
                new_guide = run_meta.pop("_guide_mask", None)
                if new_guide is not None:
                    if guide_mask is not None:
                        try:
                            guide_mask.close()
                        except Exception:
                            pass
                    guide_mask = new_guide
                infer_key = "fallback_infer" if is_rescue else "infer"
                timings_all[infer_key] = timings_all.get(infer_key, 0.0) + float(
                    run_t.get("infer", 0.0)
                )
                for k, v in run_t.items():
                    if k == "infer":
                        continue
                    timings_all[k] = timings_all.get(k, 0.0) + float(v)

                st = run_meta.get("structure_stats") or {}
                sl = float(st.get("structure_loss") or 0.0)
                qscore = float(run_meta.get("quality_score") or 0.0)
                from .qc_config import get_qc_config

                qcfg = get_qc_config()
                if (
                    "catastrophic_structure_loss" in (reasons or [])
                    or sl >= qcfg.instant_struct_loss
                ):
                    saw_struct_catastrophe = True

                # Soft veto only for still-catastrophic structure after weighted QC
                if gate_ok and cand is not None:
                    if sl >= qcfg.instant_struct_loss and qscore < qcfg.pass_min_after_rescue:
                        gate_ok = False
                        reasons = list(
                            dict.fromkeys(
                                ["catastrophic_structure_loss"] + list(reasons or [])
                            )
                        )
                    elif (
                        saw_struct_catastrophe
                        and sl >= qcfg.struct_loss_hard
                        and qscore < qcfg.pass_min
                    ):
                        gate_ok = False
                        reasons = list(
                            dict.fromkeys(
                                ["catastrophic_structure_loss"] + list(reasons or [])
                            )
                        )

                # Always preserve a rendered candidate
                if cand is not None:
                    last_valid = _replace_candidate(
                        last_valid,
                        studio=cand,
                        meta=run_meta,
                        reasons=list(reasons) or ["quality_uncertain"],
                        label=att["label"],
                        model=att["model"],
                    )
                    if not is_rescue:
                        proc_state = "fast_ready"
                    else:
                        proc_state = "rescue_ready"

                if gate_ok and cand is not None:
                    used_label = att["label"]
                    meta.update(run_meta)
                    meta["path_label"] = used_label
                    studio = cand
                    # Approved owns studio; detach from last_valid to avoid double-close
                    if last_valid and last_valid.get("studio") is studio:
                        last_valid = None
                    break

                if i == 0:
                    first_attempt_failed = True
                last_err = RuntimeError(
                    ",".join(reasons) or "segmentation_unreliable"
                )
                continue
            except Exception as exc:  # noqa: BLE001
                if i == 0:
                    first_attempt_failed = True
                last_err = exc
                if is_rescue:
                    rescue_crashed = True
                # OOM: cleanup once; do not empty_cache between every attempt
                if _is_oom(exc):
                    release_memory(empty_cuda_cache=True)
                    # One smaller retry for this rescue step only
                    if is_rescue and int(att.get("side") or 0) > INFER_MAX_SIDE_OOM_RETRY:
                        try:
                            smaller = max(
                                INFER_MAX_SIDE_OOM_RETRY,
                                int(att["side"]) - 128,
                            )
                            if smaller < int(att["side"]):
                                cand, run_meta, run_t, gate_ok, reasons = _run_once(
                                    working,
                                    model_name=att["model"],
                                    infer_max_side=smaller,
                                    size=size,
                                    with_shadow=with_shadow,
                                    scene=scene,
                                    infer_boost=bool(att["boost"]),
                                    gentle_edges=True,
                                    conservative_enhance=True,
                                    preserve_alpha=True,
                                    skip_compose_if_mask_fail=False,
                                    use_roi=bool(att.get("use_roi", False)),
                                    guide_mask=guide_mask,
                                    after_rescue=True,
                                )
                                if cand is not None:
                                    last_valid = _replace_candidate(
                                        last_valid,
                                        studio=cand,
                                        meta=run_meta,
                                        reasons=list(reasons)
                                        or ["rescue_failed"],
                                        label=att["label"],
                                        model=att["model"],
                                    )
                                    proc_state = "rescue_ready"
                                    if gate_ok:
                                        used_label = att["label"]
                                        meta.update(run_meta)
                                        studio = cand
                                        if (
                                            last_valid
                                            and last_valid.get("studio") is studio
                                        ):
                                            last_valid = None
                                        break
                                continue
                        except Exception as exc2:  # noqa: BLE001
                            last_err = exc2
                            release_memory(empty_cuda_cache=_is_oom(exc2))
                # Candidate already exists → keep going / fall through to Review
                continue
        else:
            studio = None

        if guide_mask is not None:
            try:
                guide_mask.close()
            except Exception:
                pass
            guide_mask = None

        # --- APPROVED ---
        if studio is not None:
            proc_state = "approved"
            if status_log is not None:
                if used_label == "FALLBACK":
                    status_log.append(f"[OK][FALLBACK] {name}")
                else:
                    status_log.append(f"[OK] {name}")
            try:
                t0 = time.perf_counter()
                out_path = (
                    dest_path
                    if dest_path.suffix.lower() in {".jpg", ".jpeg"}
                    else dest_path.with_suffix(".jpg")
                )
                out_path.parent.mkdir(parents=True, exist_ok=True)
                if out_path.exists() and out_path.stem != rid:
                    out_path = out_path.parent / f"{rid}.jpg"
                studio.save(out_path, "JPEG", quality=quality, optimize=False)
                timings_all["save"] = time.perf_counter() - t0
                try:
                    from .qc_engine import write_qc_diagnostics

                    diag = meta.get("qc_diagnostics")
                    if isinstance(diag, dict):
                        diag = {
                            **diag,
                            "file": name,
                            "decision": "pass",
                            "review_id": rid,
                        }
                        write_qc_diagnostics(diag, output_root=output_root, review_id=rid)
                except Exception:
                    pass
            except Exception as exc:  # noqa: BLE001
                # Approved save failed — demote existing image to Review if possible
                if last_valid is None:
                    last_valid = _replace_candidate(
                        None,
                        studio=studio,
                        meta=meta,
                        reasons=["approved_save_failed"],
                        label=used_label,
                        model=str(meta.get("model") or ""),
                    )
                    studio = None  # owned by last_valid now
                else:
                    # keep last_valid; close orphaned approved studio if different
                    try:
                        if studio is not last_valid.get("studio"):
                            studio.close()
                    except Exception:
                        pass
                    studio = None
                # Fall through to Review below
                last_err = exc
            else:
                meta["output_size"] = f"{studio.size[0]}x{studio.size[1]}"
                timings_all["total"] = time.perf_counter() - t_all
                if perf_log is not None:
                    perf_log.append(format_perf_block(timings_all, meta))
                _record_processing_report(
                    output_root=output_root,
                    filename=name,
                    status="approved",
                    meta=meta,
                    timings=timings_all,
                )
                return {
                    "status": "approved",
                    "path": out_path,
                    "reasons": [],
                    "path_label": used_label,
                    "fallback_used": fallback_used or used_label == "FALLBACK",
                    "fallback_rescued": bool(
                        fallback_used and used_label == "FALLBACK"
                    ),
                    "fast_failed": first_attempt_failed,
                    "review_id": rid,
                    "model": meta.get("model"),
                    "foreground_ratio": meta.get("foreground_ratio"),
                    "mask_stats": meta.get("mask_stats"),
                    "studio_stats": meta.get("studio_stats"),
                    "cutout_stats": meta.get("cutout_stats"),
                    "structure_stats": meta.get("structure_stats"),
                    "quality_features": meta.get("quality_features"),
                    "studio_processing": meta.get("studio_processing"),
                    "product_profile": meta.get("product_profile"),
                    "proc_state": "approved",
                    "timings": timings_all,
                    "edit_sec": timings_all.get("total", 0.0),
                    "qc_decision": meta.get("qc_decision"),
                    "quality_score": meta.get("quality_score"),
                    "raw_final_stats": meta.get("raw_final_stats"),
                    "qc_diagnostics": meta.get("qc_diagnostics"),
                    "meta": {
                        k: v
                        for k, v in meta.items()
                        if k
                        in {
                            "qc_decision",
                            "quality_score",
                            "raw_final_stats",
                            "qc_diagnostics",
                            "confidence_zone",
                            "model",
                            "timings",
                        }
                    },
                }

        # --- REVIEW (any usable candidate) ---
        if last_valid and last_valid.get("studio") is not None:
            reasons = list(last_valid.get("reasons") or [])
            if rescue_crashed:
                reasons = list(dict.fromkeys(["rescue_failed"] + reasons))
            elif quality_check_errored:
                reasons = list(dict.fromkeys(["quality_check_error"] + reasons))
            elif fallback_used and "fallback_failed_quality_check" not in reasons:
                reasons.append("fallback_failed_quality_check")
            if not reasons:
                reasons = ["quality_uncertain"]
            proc_state = "review"
            return _review_from_candidate(
                last_valid,
                reasons=reasons,
                fallback_used_flag=fallback_used or rescue_crashed,
                first_failed=first_attempt_failed,
            )

        # --- FAILED: no candidate at all ---
        reason = _precise_fail_reason(
            last_err,
            stage="infer" if proc_state == "decoded" else fail_stage,
        )
        if reason in ("segmentation_unreliable",) or not reason:
            reason = (
                "fast_inference_failed_no_candidate"
                if not fallback_used
                else "no_candidate"
            )
        return _failed_result(reason)
    except Exception as exc:  # noqa: BLE001
        # Unexpected error — still prefer Review if we have a candidate
        if last_valid and last_valid.get("studio") is not None:
            reasons = list(
                dict.fromkeys(
                    ["rescue_failed"]
                    + list(last_valid.get("reasons") or [])
                    + [_normalize_reason(str(exc))]
                )
            )
            return _review_from_candidate(
                last_valid,
                reasons=reasons,
                fallback_used_flag=True,
                first_failed=True,
            )
        return _failed_result(_precise_fail_reason(exc, stage=fail_stage or "infer"))
    finally:
        if own_working and working is not None:
            try:
                working.close()
            except Exception:
                pass
        if studio is not None:
            try:
                studio.close()
            except Exception:
                pass
        if last_valid and last_valid.get("studio") is not None:
            try:
                if last_valid["studio"] is not studio:
                    last_valid["studio"].close()
            except Exception:
                pass
        release_memory()

def process_free_job(payload: dict) -> dict:
    t0 = time.monotonic()
    perf_lines: list[str] = []
    status_lines: list[str] = []
    mode = payload.get("free_mode", "adaptive")
    model = payload.get("model_name", FREE_MODEL_FAST)
    try:
        warmup(model if mode != "adaptive" else FREE_MODEL_FAST)
        result = process_free_file(
            payload["src"],
            payload["dest"],
            size=payload.get("size", 2000),
            with_shadow=payload.get("with_shadow", True),
            model_name=model,
            free_mode=mode,  # type: ignore[arg-type]
            review_dir=payload.get("review_dir"),
            review_id=payload.get("review_id"),
            perf_log=perf_lines,
            status_log=status_lines,
        )
        result.update(
            {
                "ok": result.get("status") in ("approved", "review"),
                "src_name": payload["src_name"],
                "out_name": payload["out_name"],
                "cache_key": payload["cache_key"],
                "fp": payload["fp"],
                "edit_sec": time.monotonic() - t0,
                "perf": "\n".join(perf_lines),
                "status_log": "\n".join(status_lines),
                "src_path": payload["src"],
            }
        )
        return result
    except Exception as exc:  # noqa: BLE001
        release_memory(empty_cuda_cache=_is_oom(exc))
        return {
            "ok": False,
            "status": "failed",
            "src_name": payload["src_name"],
            "out_name": payload.get("out_name", ""),
            "error": str(exc),
            "reasons": [_normalize_reason(str(exc))],
            "edit_sec": time.monotonic() - t0,
            "perf": "\n".join(perf_lines),
            "status_log": "\n".join(status_lines),
            "src_path": payload.get("src"),
        }
