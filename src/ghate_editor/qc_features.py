"""Shared RAW feature cache — compute once, reuse across structure + RAW↔FINAL QC."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class RawFeatureCache:
    rgb: np.ndarray  # uint8 HxWx3
    lum: np.ndarray  # float32
    edge: np.ndarray  # float32 sobel mag
    tex: np.ndarray  # float32 local std
    prior: np.ndarray | None = None  # bool product prior (optional)
    width: int = 0
    height: int = 0
    coordinate_space: str = "working_rgb"  # never "studio_canvas"

    def matches(self, shape_hw: tuple[int, int]) -> bool:
        return self.height == shape_hw[0] and self.width == shape_hw[1]


def luma(rgb: np.ndarray) -> np.ndarray:
    return (
        0.299 * rgb[:, :, 0].astype(np.float32)
        + 0.587 * rgb[:, :, 1].astype(np.float32)
        + 0.114 * rgb[:, :, 2].astype(np.float32)
    )


def sobel_mag(lum: np.ndarray) -> np.ndarray:
    x = np.pad(lum.astype(np.float32), 1, mode="edge")
    gx = (x[1:-1, 2:] - x[1:-1, :-2]) * 0.5
    gy = (x[2:, 1:-1] - x[:-2, 1:-1]) * 0.5
    return np.sqrt(gx * gx + gy * gy)


def local_std(lum: np.ndarray, win: int = 5) -> np.ndarray:
    from scipy import ndimage

    mean = ndimage.uniform_filter(lum.astype(np.float32), size=win, mode="nearest")
    mean_sq = ndimage.uniform_filter(lum.astype(np.float32) ** 2, size=win, mode="nearest")
    return np.sqrt(np.maximum(mean_sq - mean * mean, 0.0))


def estimate_prior_from_features(
    rgb: np.ndarray,
    lum: np.ndarray,
    edge: np.ndarray,
    tex: np.ndarray,
) -> np.ndarray:
    """Delegate to qc_raw_final so prior logic cannot drift between modules."""
    from .qc_raw_final import estimate_raw_product_prior

    return estimate_raw_product_prior(rgb, lum=lum, edge=edge, tex=tex)


def build_raw_features(
    source_rgb: Image.Image | np.ndarray,
    *,
    with_prior: bool = True,
) -> RawFeatureCache:
    if isinstance(source_rgb, Image.Image):
        rgb = np.asarray(
            source_rgb if source_rgb.mode == "RGB" else source_rgb.convert("RGB"),
            dtype=np.uint8,
        )
    else:
        rgb = np.asarray(source_rgb, dtype=np.uint8)
    h, w = rgb.shape[:2]
    lum = luma(rgb)
    edge = sobel_mag(lum)
    tex = local_std(lum, win=5)
    prior = estimate_prior_from_features(rgb, lum, edge, tex) if with_prior else None
    return RawFeatureCache(
        rgb=rgb,
        lum=lum,
        edge=edge,
        tex=tex,
        prior=prior,
        width=w,
        height=h,
        coordinate_space="working_rgb",
    )
