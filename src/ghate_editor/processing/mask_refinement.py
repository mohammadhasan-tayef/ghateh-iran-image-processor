"""Mask refinement — preserve fine structure; avoid aggressive erosion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from .config import ProcessingConfig
from .profiles import ProductProfile, ProfileDecision


@dataclass
class SegmentationResult:
    mask: Image.Image
    confidence: float
    model_name: str
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence": self.confidence,
            "model_name": self.model_name,
            "warnings": list(self.warnings),
            "metrics": dict(self.metrics),
        }


def mask_iou(a: Image.Image, b: Image.Image, thresh: int = 128) -> float:
    aa = np.asarray(a.convert("L"), dtype=np.uint8) >= thresh
    bb = np.asarray(b.convert("L"), dtype=np.uint8) >= thresh
    if aa.shape != bb.shape:
        bb_img = b.convert("L").resize(a.size, Image.Resampling.NEAREST)
        bb = np.asarray(bb_img, dtype=np.uint8) >= thresh
    inter = np.logical_and(aa, bb).sum()
    union = np.logical_or(aa, bb).sum()
    return float(inter / max(1, union))


def score_mask_confidence(
    mask: Image.Image,
    *,
    model_name: str = "unknown",
    rgb: Image.Image | None = None,
) -> SegmentationResult:
    """Heuristic confidence from continuity, size, fragmentation, border clip."""
    arr = np.asarray(mask.convert("L"), dtype=np.uint8)
    h, w = arr.shape
    soft = arr >= 40
    solid = arr >= 128
    soft_frac = float(soft.mean())
    solid_frac = float(solid.mean())
    warnings: list[str] = []
    score = 1.0

    if soft_frac < 0.01:
        score -= 0.55
        warnings.append("tiny_foreground")
    elif soft_frac > 0.55:
        score -= 0.35
        warnings.append("full_frame_mask")

    # Border clipping
    border = np.concatenate(
        [soft[0, :], soft[-1, :], soft[:, 0], soft[:, -1]]
    )
    border_hit = float(border.mean())
    if border_hit > 0.15:
        score -= 0.18
        warnings.append("border_clipping")

    # Fragmentation via connected components on solid
    n_comp = _count_components(solid)
    if n_comp >= 8:
        score -= 0.22
        warnings.append("fragmented")
    elif n_comp >= 4:
        score -= 0.10
        warnings.append("multi_component")

    # Internal holes (can be legitimate mesh)
    if soft.any() and solid.any():
        hole_ratio = float(1.0 - solid.sum() / max(1, soft.sum()))
        if hole_ratio > 0.45:
            score -= 0.08
            warnings.append("many_holes")

    # Soft fog band
    fog = (arr >= 40) & (arr < 140)
    fog_ratio = float(fog.sum() / max(1, soft.sum())) if soft.any() else 0.0
    if fog_ratio > 0.55:
        score -= 0.15
        warnings.append("foggy_alpha")

    # Mean alpha of soft
    mean_a = float(arr[soft].mean()) if soft.any() else 0.0
    if mean_a < 95:
        score -= 0.12
        warnings.append("weak_alpha")

    score = float(np.clip(score, 0.0, 1.0))
    metrics = {
        "soft_frac": soft_frac,
        "solid_frac": solid_frac,
        "border_hit": border_hit,
        "n_components": float(n_comp),
        "fog_ratio": fog_ratio,
        "mean_alpha_soft": mean_a,
    }
    return SegmentationResult(
        mask=mask,
        confidence=score,
        model_name=model_name,
        warnings=warnings,
        metrics=metrics,
    )


def _count_components(binary: np.ndarray) -> int:
    """Fast connected-component count via scipy (fallback: downsample scan)."""
    try:
        from scipy import ndimage

        _, n = ndimage.label(binary.astype(np.uint8))
        return int(n)
    except Exception:
        # Extremely coarse fallback — sample every 4th pixel for speed
        small = binary[::4, ::4]
        return int(min(64, small.sum() // 50 + (1 if small.any() else 0)))


def _label_components(binary: np.ndarray) -> tuple[np.ndarray, list[int]]:
    """Return label map (0=bg) and list of sizes per label id starting at 1."""
    try:
        from scipy import ndimage

        labels, n = ndimage.label(binary.astype(np.uint8))
        if n <= 0:
            return labels.astype(np.int32), []
        # bincount: index 0 is background
        counts = np.bincount(labels.ravel())
        sizes = [int(counts[i]) for i in range(1, n + 1)]
        return labels.astype(np.int32), sizes
    except Exception:
        # No scipy path — skip island removal (return single blob label)
        labels = binary.astype(np.int32)
        return labels, [int(binary.sum())] if binary.any() else []


def refine_mask(
    mask: Image.Image,
    *,
    profile: ProfileDecision | None = None,
    cfg: ProcessingConfig | None = None,
) -> tuple[Image.Image, dict[str, Any]]:
    """
    Remove tiny islands, optionally fill micro-holes, edge-aware soft AA.
    Never aggressively erode — mesh/holes preserved when profile asks.
    """
    cfg = cfg or ProcessingConfig()
    profile = profile or ProfileDecision(primary=ProductProfile.NORMAL)
    arr = np.asarray(mask.convert("L"), dtype=np.float32)
    h, w = arr.shape
    soft = arr >= 28.0
    solid = arr >= 120.0

    info: dict[str, Any] = {"removed_islands": 0, "filled_micro_holes": 0}

    # Keep largest components; drop tiny islands
    labels, sizes = _label_components(soft)
    if sizes:
        total = float(sum(sizes))
        keep = np.zeros(len(sizes) + 1, dtype=bool)
        max_size = max(sizes)
        for i, sz in enumerate(sizes, start=1):
            if sz >= cfg.min_component_px and sz / max(1.0, total) >= cfg.tiny_component_max_frac:
                keep[i] = True
            elif sz >= max_size * 0.35:
                keep[i] = True
        removed = int(sum(1 for i, sz in enumerate(sizes, start=1) if not keep[i]))
        info["removed_islands"] = removed
        if removed:
            drop = ~keep[labels]
            arr = arr.copy()
            arr[drop] = 0.0
            soft = arr >= 28.0
            solid = arr >= 120.0

    # Fill only micro holes inside solid core (not mesh)
    if not profile.preserve_holes:
        inv = ~solid
        hole_labels, hole_sizes = _label_components(inv)
        # Holes that don't touch border and are tiny
        filled = 0
        if hole_sizes:
            for i, sz in enumerate(hole_sizes, start=1):
                if sz > cfg.preserve_holes_min_px * 4:
                    continue
                region = hole_labels == i
                # Touches border?
                if (
                    region[0, :].any()
                    or region[-1, :].any()
                    or region[:, 0].any()
                    or region[:, -1].any()
                ):
                    continue
                # Must be surrounded by soft FG
                if soft[region].mean() < 0.02 and (~soft)[region].all():
                    # Interior hole in solid: fill
                    ys, xs = np.where(region)
                    if ys.size and soft.any():
                        # Only if neighbors are mostly FG
                        dil = Image.fromarray((solid.astype(np.uint8) * 255), mode="L").filter(
                            ImageFilter.MaxFilter(3)
                        )
                        dil_a = np.asarray(dil, dtype=np.uint8) > 0
                        if float(dil_a[region].mean()) > 0.5:
                            arr[region] = 220.0
                            filled += 1
            info["filled_micro_holes"] = filled

    out = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="L")

    # Mild edge AA — lighter for mesh
    sigma = cfg.mesh_feather_sigma if profile.preserve_holes else cfg.edge_feather_sigma
    if profile.gentle_edges:
        # Expand slightly then blur — prefer leftover bg over cutting white product
        out = out.filter(ImageFilter.MaxFilter(3))
        out = out.filter(ImageFilter.GaussianBlur(max(0.35, sigma)))
    else:
        out = out.filter(ImageFilter.GaussianBlur(sigma))

    return out, info


def select_or_ensemble_masks(
    primary: SegmentationResult,
    secondary: SegmentationResult | None,
    *,
    cfg: ProcessingConfig | None = None,
) -> SegmentationResult:
    """Prefer higher-confidence mask; conservative union only when high IoU."""
    cfg = cfg or ProcessingConfig()
    if secondary is None:
        return primary
    iou = mask_iou(primary.mask, secondary.mask)
    warnings = list(primary.warnings) + [f"second_model:{secondary.model_name}", f"iou:{iou:.3f}"]

    if iou >= cfg.iou_agree_min:
        # Conservative: take max alpha (union of soft edges) — keeps detail
        a = np.asarray(primary.mask.convert("L"), dtype=np.uint8)
        b = np.asarray(secondary.mask.convert("L").resize(primary.mask.size, Image.Resampling.LANCZOS), dtype=np.uint8)
        merged = np.maximum(a, b)
        # Where both solid, average slightly toward stronger
        both = (a >= 128) & (b >= 128)
        merged = merged.astype(np.float32)
        merged[both] = 0.5 * a[both] + 0.5 * b[both]
        mask = Image.fromarray(merged.astype(np.uint8), mode="L")
        conf = max(primary.confidence, secondary.confidence) * 0.5 + 0.5 * min(
            primary.confidence, secondary.confidence
        )
        return SegmentationResult(
            mask=mask,
            confidence=float(conf),
            model_name=f"{primary.model_name}+{secondary.model_name}",
            warnings=warnings + ["ensemble_max"],
            metrics={"iou": iou, **primary.metrics},
        )

    # Disagreement — pick higher confidence
    best = primary if primary.confidence >= secondary.confidence else secondary
    return SegmentationResult(
        mask=best.mask,
        confidence=best.confidence * 0.9,  # disagreement penalty
        model_name=best.model_name,
        warnings=warnings + ["selected_by_confidence"],
        metrics={"iou": iou, **best.metrics},
    )
