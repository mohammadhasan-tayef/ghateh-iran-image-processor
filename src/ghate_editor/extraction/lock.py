"""Immutable product alpha after candidate selection.

Once locked, geometry must not change. Downstream stages may only *read*
this alpha (composite, zone masks, alignment). Writes fail loudly.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image


class AlphaMutationError(RuntimeError):
    """Raised when FINAL_ALPHA bytes change after lock."""


def _sha256_u8(arr: np.ndarray) -> str:
    contig = np.ascontiguousarray(arr, dtype=np.uint8)
    return hashlib.sha256(contig.tobytes()).hexdigest()


def alpha_checksum(image: Image.Image) -> str:
    arr = np.asarray(image.convert("L"), dtype=np.uint8)
    return _sha256_u8(arr)


@dataclass(frozen=True)
class FinalAlpha:
    """Frozen product boundary. `data` is a read-only HxW uint8 view."""

    data: np.ndarray
    source_engine: str
    checksum: str
    dimensions: tuple[int, int]  # (width, height) PIL convention
    locked: bool = True

    def image(self) -> Image.Image:
        """Copy for gates/QC. Mutating the copy cannot change the lock."""
        return Image.fromarray(np.array(self.data, copy=True, dtype=np.uint8), mode="L")

    def matches(self, other: Image.Image | np.ndarray) -> bool:
        if isinstance(other, Image.Image):
            arr = np.asarray(other.convert("L"), dtype=np.uint8)
        else:
            arr = np.asarray(other, dtype=np.uint8)
        if arr.shape != self.data.shape:
            return False
        return _sha256_u8(arr) == self.checksum

    def verify(
        self,
        other: Image.Image | np.ndarray | None = None,
        *,
        strict: bool | None = None,
        label: str = "",
    ) -> bool:
        """
        Confirm checksum. `other` defaults to the locked buffer itself.
        strict=True (tests/debug) raises AlphaMutationError.
        strict=False logs/returns False so the caller can restore bytes.
        """
        if not self.locked:
            raise AlphaMutationError("FINAL_ALPHA is not locked")
        if other is not None:
            ok = self.matches(other)
        else:
            ok = (not self.data.flags.writeable) and (_sha256_u8(self.data) == self.checksum)
        if ok:
            return True
        msg = f"ALPHA_MUTATION_DETECTED{(' ' + label) if label else ''}"
        if strict is None:
            env = os.environ.get("GHATE_STRICT_ALPHA", "").strip().lower()
            debug = os.environ.get("GHATE_DEBUG", "").strip().lower() in {
                "1",
                "true",
                "yes",
            }
            strict = env in {"1", "true", "yes"} or debug
        if strict:
            raise AlphaMutationError(msg)
        return False

    def to_meta(self) -> dict[str, Any]:
        return {
            "source_engine": self.source_engine,
            "checksum": self.checksum,
            "dimensions": list(self.dimensions),
            "locked": self.locked,
        }


def lock_alpha(
    alpha: Image.Image | np.ndarray,
    *,
    source_engine: str = "unknown",
) -> FinalAlpha:
    if isinstance(alpha, Image.Image):
        arr = np.array(alpha.convert("L"), dtype=np.uint8, copy=True)
    else:
        arr = np.array(np.asarray(alpha), dtype=np.uint8, copy=True)
        if arr.ndim != 2:
            raise ValueError("alpha must be HxW")
    arr = np.ascontiguousarray(arr)
    arr.setflags(write=False)
    h, w = arr.shape
    return FinalAlpha(
        data=arr,
        source_engine=source_engine,
        checksum=_sha256_u8(arr),
        dimensions=(w, h),
        locked=True,
    )


def restore_locked_alpha(rgb: Image.Image, locked: FinalAlpha) -> Image.Image:
    """Original RGB + frozen alpha (straight, un-premultiplied)."""
    rgba = rgb.convert("RGB").convert("RGBA")
    a = locked.image()
    if a.size != rgba.size:
        raise AlphaMutationError(
            f"ALPHA_MUTATION_DETECTED size {a.size} != rgb {rgba.size}"
        )
    rgba.putalpha(a)
    return rgba
