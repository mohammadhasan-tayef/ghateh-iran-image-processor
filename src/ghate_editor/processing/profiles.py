"""Lightweight product-type profiles for adaptive processing rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from PIL import Image

from .analyzer import ImageAnalysis
from .config import ProcessingConfig


class ProductProfile(str, Enum):
    NORMAL = "NORMAL"
    DARK_OBJECT = "DARK_OBJECT"
    WHITE_OBJECT = "WHITE_OBJECT"
    METALLIC = "METALLIC"
    REFLECTIVE = "REFLECTIVE"
    TRANSLUCENT = "TRANSLUCENT"
    MESH = "MESH"
    THIN_COMPLEX_EDGES = "THIN_COMPLEX_EDGES"
    HOSE = "HOSE"
    CYLINDRICAL_FILTER = "CYLINDRICAL_FILTER"
    PACKAGING = "PACKAGING"


@dataclass
class ProfileDecision:
    primary: ProductProfile
    tags: list[ProductProfile] = field(default_factory=list)
    gentle_edges: bool = False
    preserve_holes: bool = False
    conservative_color: bool = False
    product_fill: float = 0.84
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary.value,
            "tags": [t.value for t in self.tags],
            "gentle_edges": self.gentle_edges,
            "preserve_holes": self.preserve_holes,
            "conservative_color": self.conservative_color,
            "product_fill": self.product_fill,
            "reasons": list(self.reasons),
        }


def select_profile(
    analysis: ImageAnalysis,
    mask: Image.Image | None = None,
    scene: dict[str, Any] | None = None,
    cfg: ProcessingConfig | None = None,
) -> ProfileDecision:
    """Heuristic multi-label profile from measurable signals (+ optional mask)."""
    cfg = cfg or ProcessingConfig()
    scene = scene or {}
    tags: list[ProductProfile] = []
    reasons: list[str] = []

    # Aspect from mask bbox
    aspect = 1.0
    hole_frac = 0.0
    elong = 1.0
    if mask is not None:
        a = np.asarray(mask.convert("L"), dtype=np.uint8)
        solid = a >= 128
        soft = a >= 40
        if soft.any():
            ys, xs = np.where(soft)
            h = int(ys.max() - ys.min() + 1)
            w = int(xs.max() - xs.min() + 1)
            aspect = max(h, w) / max(1, min(h, w))
            elong = aspect
            # Internal holes: soft bbox fill vs solid
            y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
            roi = soft[y0 : y1 + 1, x0 : x1 + 1]
            sol = solid[y0 : y1 + 1, x0 : x1 + 1]
            if roi.any():
                hole_frac = float(1.0 - (sol.sum() / max(1, roi.sum())))

    if analysis.mean_luma <= 85.0 or analysis.shadow_clip > 0.08:
        tags.append(ProductProfile.DARK_OBJECT)
        reasons.append("low_fg_luma")
    if analysis.mean_luma >= 175.0 or scene.get("pale_product"):
        tags.append(ProductProfile.WHITE_OBJECT)
        reasons.append("high_fg_luma")
    if analysis.saturation_mean < 0.12 and 90 <= analysis.mean_luma <= 190:
        tags.append(ProductProfile.METALLIC)
        reasons.append("low_chroma_mid")
    if scene.get("glossy") or analysis.highlight_clip > 0.06:
        tags.append(ProductProfile.REFLECTIVE)
        reasons.append("highlights")
    if scene.get("grey_packaging") or (
        analysis.saturation_mean < 0.08 and analysis.background_uniformity < 0.55
    ):
        tags.append(ProductProfile.TRANSLUCENT)
        reasons.append("low_sat_uneven_bg")
    if analysis.edge_complexity >= 0.18 or hole_frac >= 0.12:
        tags.append(ProductProfile.MESH)
        reasons.append("edge_or_holes")
    if analysis.edge_complexity >= 0.16 and elong < 2.2:
        tags.append(ProductProfile.THIN_COMPLEX_EDGES)
        reasons.append("complex_edges")
    if elong >= 2.4:
        tags.append(ProductProfile.HOSE)
        reasons.append("elongated")
    if 1.15 <= elong <= 2.0 and analysis.edge_complexity >= 0.12:
        tags.append(ProductProfile.CYLINDRICAL_FILTER)
        reasons.append("cylinder_like")
    if scene.get("difficult") and analysis.saturation_mean > 0.18:
        tags.append(ProductProfile.PACKAGING)
        reasons.append("colorful_difficult")

    if not tags:
        tags = [ProductProfile.NORMAL]
        reasons.append("default")

    # Primary priority
    priority = [
        ProductProfile.MESH,
        ProductProfile.HOSE,
        ProductProfile.WHITE_OBJECT,
        ProductProfile.DARK_OBJECT,
        ProductProfile.TRANSLUCENT,
        ProductProfile.METALLIC,
        ProductProfile.REFLECTIVE,
        ProductProfile.THIN_COMPLEX_EDGES,
        ProductProfile.CYLINDRICAL_FILTER,
        ProductProfile.PACKAGING,
        ProductProfile.NORMAL,
    ]
    primary = ProductProfile.NORMAL
    for p in priority:
        if p in tags:
            primary = p
            break

    gentle = primary in {
        ProductProfile.WHITE_OBJECT,
        ProductProfile.METALLIC,
        ProductProfile.REFLECTIVE,
        ProductProfile.TRANSLUCENT,
    }
    preserve_holes = ProductProfile.MESH in tags or ProductProfile.THIN_COMPLEX_EDGES in tags
    conservative_color = primary in {
        ProductProfile.WHITE_OBJECT,
        ProductProfile.DARK_OBJECT,
        ProductProfile.METALLIC,
        ProductProfile.PACKAGING,
    }

    fill = cfg.product_fill_default
    if ProductProfile.HOSE in tags:
        fill = min(cfg.product_fill_max, 0.90)
    elif ProductProfile.MESH in tags or ProductProfile.CYLINDRICAL_FILTER in tags:
        fill = 0.82
    elif ProductProfile.DARK_OBJECT in tags:
        fill = 0.86

    fill = float(np.clip(fill, cfg.product_fill_min, cfg.product_fill_max))

    return ProfileDecision(
        primary=primary,
        tags=tags,
        gentle_edges=gentle,
        preserve_holes=preserve_holes,
        conservative_color=conservative_color,
        product_fill=fill,
        reasons=reasons,
    )
