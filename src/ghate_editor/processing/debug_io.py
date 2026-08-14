"""Optional debug artifact dumps for diagnosing bad outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image


def save_debug_bundle(
    out_dir: Path | str,
    *,
    original: Image.Image | None = None,
    mask_raw: Image.Image | None = None,
    mask_refined: Image.Image | None = None,
    foreground: Image.Image | None = None,
    edge_debug: Image.Image | None = None,
    final: Image.Image | None = None,
    analysis: dict[str, Any] | None = None,
) -> Path:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    if original is not None:
        original.convert("RGB").save(root / "original.jpg", quality=92)
    if mask_raw is not None:
        mask_raw.convert("L").save(root / "mask_raw.png")
    if mask_refined is not None:
        mask_refined.convert("L").save(root / "mask_refined.png")
    if foreground is not None:
        foreground.convert("RGBA").save(root / "foreground.png")
    if edge_debug is not None:
        edge_debug.convert("RGBA").save(root / "edge_debug.png")
    if final is not None:
        final.convert("RGB").save(root / "final.jpg", quality=92)
    if analysis is not None:
        (root / "analysis.json").write_text(
            json.dumps(analysis, indent=2, default=str),
            encoding="utf-8",
        )
    return root
