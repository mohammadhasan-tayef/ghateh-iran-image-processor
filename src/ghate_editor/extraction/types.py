"""Shared extraction types. Decode once; reuse working RGB."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from PIL import Image


@dataclass
class ImageContext:
    """Decoded working image plus extraction state. Not re-decoded per stage."""

    working_rgb: Image.Image
    scene: dict[str, Any] = field(default_factory=dict)
    src_path: Path | str | None = None
    selected_alpha: Image.Image | None = None
    product_bbox: tuple[int, int, int, int] | None = None
    extraction_meta: dict[str, Any] = field(default_factory=dict)
    final_rgba: Image.Image | None = None

    @property
    def original_rgb(self) -> Image.Image:
        # Working canvas is already the once-decoded, size-capped original.
        return self.working_rgb


@dataclass
class ExtractionResult:
    alpha: Image.Image | None
    rgba: Image.Image | None
    confidence: float
    engine_name: str
    inference_time_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)
    gate: str = ""  # GOOD | UNCERTAIN | INVALID | FAILED
    locked_alpha: Any = None

    def close_extras(self) -> None:
        """Drop non-selected full copies; keep alpha/rgba for the winner."""
        return


class ExtractionEngine(Protocol):
    name: str

    def extract(self, ctx: ImageContext) -> ExtractionResult: ...
