"""Fast binary morphology helpers (scipy) — drop-in for PIL Max/MinFilter on masks."""

from __future__ import annotations

import numpy as np

_SQ3 = np.ones((3, 3), dtype=bool)


def binary_dilate(mask: np.ndarray, *, radius: int) -> np.ndarray:
    """
    Dilate boolean mask by Chebyshev radius (≈ PIL MaxFilter(2*radius+1) on binary).
    """
    from scipy import ndimage

    if radius <= 0:
        return mask.astype(bool, copy=False)
    return ndimage.binary_dilation(mask.astype(bool, copy=False), structure=_SQ3, iterations=int(radius))


def binary_erode(mask: np.ndarray, *, radius: int) -> np.ndarray:
    """Erode boolean mask by Chebyshev radius (≈ PIL MinFilter(2*radius+1) on binary)."""
    from scipy import ndimage

    if radius <= 0:
        return mask.astype(bool, copy=False)
    return ndimage.binary_erosion(mask.astype(bool, copy=False), structure=_SQ3, iterations=int(radius))


def max_filter_radius_from_size(size: int) -> int:
    """PIL MaxFilter(size) uses odd size; radius = size // 2."""
    return max(0, int(size) // 2)
