"""Optional sticker/label removal — DISABLED by default.

Printed packaging graphics must never be removed by the normal pipeline.
This module is a placeholder architecture only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass
class LabelRemovalResult:
    image: Image.Image
    applied: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"applied": self.applied, "reason": self.reason}


def maybe_remove_labels(
    rgba: Image.Image,
    *,
    enabled: bool = False,
) -> LabelRemovalResult:
    """No-op unless explicitly enabled; even then requires confident detection (TODO)."""
    if not enabled:
        return LabelRemovalResult(image=rgba, applied=False, reason="disabled")
    return LabelRemovalResult(
        image=rgba,
        applied=False,
        reason="detection_not_implemented_route_to_review",
    )
