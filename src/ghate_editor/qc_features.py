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
    """Same logic as qc_raw_final.estimate_raw_product_prior, using precomputed maps."""
    from scipy import ndimage

    h, w = rgb.shape[:2]
    border = np.zeros((h, w), dtype=bool)
    m = max(8, int(0.06 * min(h, w)))
    border[:m, :] = True
    border[-m:, :] = True
    border[:, :m] = True
    border[:, -m:] = True

    bg_lum = float(np.median(lum[border])) if border.any() else 220.0
    bg_std = float(np.std(lum[border])) if border.any() else 15.0
    d_lum = np.abs(lum - bg_lum)
    bg_col = (
        rgb[border].astype(np.float32).mean(axis=0)
        if border.any()
        else np.array([bg_lum, bg_lum, bg_lum], dtype=np.float32)
    )
    d_col = np.linalg.norm(rgb.astype(np.float32) - bg_col[None, None, :], axis=2)

    near_white = (
        (rgb[:, :, 0] >= 248) & (rgb[:, :, 1] >= 248) & (rgb[:, :, 2] >= 248)
    )
    content = (~near_white) & (
        (d_lum >= max(12.0, bg_std * 1.2))
        | (d_col >= 18.0)
        | (edge >= 8.0)
        | (tex >= 5.0)
    )
    content = ndimage.binary_opening(content, iterations=1)
    content = ndimage.binary_closing(content, iterations=2)
    labeled, n = ndimage.label(content)
    if n >= 1:
        sizes = ndimage.sum(content, labeled, index=np.arange(1, n + 1))
        keep = np.zeros(n + 1, dtype=bool)
        total = float(sum(sizes)) if len(sizes) else 0.0
        for i, sz in enumerate(sizes, start=1):
            if sz >= max(80.0, 0.002 * h * w) and (total <= 0 or sz / total >= 0.01):
                keep[i] = True
        if len(sizes):
            keep[int(np.argmax(sizes)) + 1] = True
        content = keep[labeled]
    return content


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
    lum = luma(rgb)
    edge = sobel_mag(lum)
    tex = local_std(lum, win=5)
    prior = estimate_prior_from_features(rgb, lum, edge, tex) if with_prior else None
    return RawFeatureCache(rgb=rgb, lum=lum, edge=edge, tex=tex, prior=prior)
