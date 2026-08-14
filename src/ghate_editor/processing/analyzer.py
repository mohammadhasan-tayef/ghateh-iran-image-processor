"""Per-image analysis before adaptive editing."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from PIL import Image


@dataclass
class ImageAnalysis:
    exposure_score: float  # 0=dark, 0.5=balanced, 1=bright
    mean_luma: float
    std_luma: float
    highlight_clip: float
    shadow_clip: float
    contrast: float
    color_cast: tuple[float, float, float]  # mean R-G, G-B, R-B deltas
    wb_tendency: str  # neutral|warm|cool|green|magenta
    sharpness: float
    noise_level: float
    background_brightness: float
    background_uniformity: float
    object_size_hint: float  # rough fg guess from center-weighted dark/chroma
    edge_complexity: float
    saturation_mean: float

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["color_cast"] = list(self.color_cast)
        return d


def _sobel_mag(lum: np.ndarray) -> np.ndarray:
    # Simple Sobel via finite differences
    gy, gx = np.gradient(lum.astype(np.float32))
    return np.sqrt(gx * gx + gy * gy)


def analyze_image(rgb: Image.Image, mask: Image.Image | None = None) -> ImageAnalysis:
    """
    Extract adaptive signals from RGB (optionally masked by soft alpha).
    Does not mutate the image.
    """
    arr = np.asarray(rgb.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]

    if mask is not None:
        a = np.asarray(mask.convert("L"), dtype=np.float32)
        if a.shape[:2] != (h, w):
            a = np.asarray(
                mask.convert("L").resize((w, h), Image.Resampling.BILINEAR),
                dtype=np.float32,
            )
        fg = a >= 40.0
        bg = a < 20.0
    else:
        # Approximate: border ring = background, center = object hint
        yy, xx = np.mgrid[0:h, 0:w]
        cy, cx = h / 2.0, w / 2.0
        dist = np.sqrt(((yy - cy) / max(h, 1)) ** 2 + ((xx - cx) / max(w, 1)) ** 2)
        border = (yy < h * 0.08) | (yy > h * 0.92) | (xx < w * 0.08) | (xx > w * 0.92)
        fg = dist < 0.35
        bg = border

    mean_luma = float(lum[fg].mean()) if fg.any() else float(lum.mean())
    std_luma = float(lum[fg].std()) if fg.any() else float(lum.std())
    highlight_clip = float(np.count_nonzero(lum[fg] >= 250) / max(1, int(fg.sum()))) if fg.any() else 0.0
    shadow_clip = float(np.count_nonzero(lum[fg] <= 8) / max(1, int(fg.sum()))) if fg.any() else 0.0
    contrast = float(np.clip(std_luma / 64.0, 0.0, 2.0))

    # Exposure score: map mean luma to 0..1 around target ~120
    exposure_score = float(np.clip(mean_luma / 255.0, 0.0, 1.0))

    r_m = float(arr[:, :, 0][fg].mean()) if fg.any() else float(arr[:, :, 0].mean())
    g_m = float(arr[:, :, 1][fg].mean()) if fg.any() else float(arr[:, :, 1].mean())
    b_m = float(arr[:, :, 2][fg].mean()) if fg.any() else float(arr[:, :, 2].mean())
    color_cast = (r_m - g_m, g_m - b_m, r_m - b_m)

    rg, gb, rb = color_cast
    if abs(rg) < 6 and abs(gb) < 6:
        wb_tendency = "neutral"
    elif rg > 8 and rb > 8:
        wb_tendency = "warm"
    elif rb < -8 and gb < -4:
        wb_tendency = "cool"
    elif gb > 8:
        wb_tendency = "green"
    elif rg < -8:
        wb_tendency = "magenta"
    else:
        wb_tendency = "neutral"

    edge = _sobel_mag(lum)
    sharpness = float(edge[fg].mean() / 40.0) if fg.any() else float(edge.mean() / 40.0)
    sharpness = float(np.clip(sharpness, 0.0, 3.0))

    # Noise: high-frequency residual via box filter (same 3x3 mean as sliding window)
    from scipy import ndimage

    local = ndimage.uniform_filter(lum.astype(np.float32), size=3, mode="nearest")
    residual = np.abs(lum - local)
    noise_level = (
        float(residual[fg].mean() / 255.0) if fg.any() else float(residual.mean() / 255.0)
    )

    bg_lum = float(lum[bg].mean()) if bg.any() else float(lum.mean())
    bg_std = float(lum[bg].std()) if bg.any() else float(lum.std())
    background_uniformity = float(np.clip(1.0 - bg_std / 40.0, 0.0, 1.0))

    object_size_hint = float(np.count_nonzero(fg) / max(1, h * w)) if mask is not None else 0.25

    # Edge complexity: fraction of strong edges in FG
    if fg.any():
        edge_complexity = float(np.count_nonzero(edge[fg] > 25.0) / max(1, int(fg.sum())))
    else:
        edge_complexity = float(np.count_nonzero(edge > 25.0) / max(1, edge.size))

    mx = arr.max(axis=2)
    mn = arr.min(axis=2)
    sat = np.where(mx > 1e-3, (mx - mn) / np.maximum(mx, 1e-3), 0.0)
    saturation_mean = float(sat[fg].mean()) if fg.any() else float(sat.mean())

    return ImageAnalysis(
        exposure_score=exposure_score,
        mean_luma=mean_luma,
        std_luma=std_luma,
        highlight_clip=highlight_clip,
        shadow_clip=shadow_clip,
        contrast=contrast,
        color_cast=color_cast,
        wb_tendency=wb_tendency,
        sharpness=sharpness,
        noise_level=noise_level,
        background_brightness=bg_lum,
        background_uniformity=background_uniformity,
        object_size_hint=object_size_hint,
        edge_complexity=edge_complexity,
        saturation_mean=saturation_mean,
    )
