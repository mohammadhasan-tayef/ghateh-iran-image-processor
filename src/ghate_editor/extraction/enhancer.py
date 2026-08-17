"""Future product-only enhancement. NO-OP; must never touch FINAL_ALPHA."""

from __future__ import annotations

from typing import Any

from PIL import Image


class ProductEnhancer:
    """
    Future:

        ProductEnhancer.enhance(original_rgb, interior_mask, edge_protection_mask)

    MAY modify: product INTERIOR RGB
    MUST NOT modify: FINAL_ALPHA, EDGE PROTECTION BAND, BACKGROUND
    """

    enabled: bool = False

    def enhance(
        self,
        original_rgb: Image.Image,
        interior_mask: Image.Image | None = None,
        edge_protection_mask: Image.Image | None = None,
        **_: Any,
    ) -> Image.Image:
        if not self.enabled:
            return original_rgb
        # Not implemented this milestone.
        return original_rgb
