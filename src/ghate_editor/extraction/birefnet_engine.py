"""Existing rembg BiRefNet quality path as a rescue adapter. No rewrite."""

from __future__ import annotations

import time
from typing import Any

from PIL import Image

from .integrity import PRIMARY_INVALID, cheap_alpha_metrics, classify_primary
from .types import ExtractionResult, ImageContext


class ExistingBiRefNetExtractionEngine:
    name = "birefnet"

    def extract(self, ctx: ImageContext) -> ExtractionResult:
        from ghate_editor.free_pipeline import (
            FREE_MODEL_QUALITY,
            INFER_MAX_SIDE_OOM_RETRY,
            INFER_MAX_SIDE_QUALITY,
            apply_mask,
            segment_mask,
        )
        from ghate_editor.model_service import release_memory

        t0 = time.perf_counter()
        meta: dict[str, Any] = {
            "engine": self.name,
            "model": FREE_MODEL_QUALITY,
        }
        last_err: str | None = None
        alpha: Image.Image | None = None
        infer_wh: tuple[int, int] | None = None
        for side in (INFER_MAX_SIDE_QUALITY, INFER_MAX_SIDE_OOM_RETRY):
            try:
                mask, iw, ih = segment_mask(
                    ctx.working_rgb,
                    max_side=side,
                    model_name=FREE_MODEL_QUALITY,
                    infer_boost=True,
                    scene=ctx.scene,
                )
                alpha = mask.convert("L")
                infer_wh = (iw, ih)
                meta["max_side"] = side
                last_err = None
                break
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                release_memory(empty_cuda_cache=True)
        ms = (time.perf_counter() - t0) * 1000.0
        if alpha is None:
            meta["error"] = last_err or "birefnet_failed"
            meta["gate"] = "FAILED"
            return ExtractionResult(
                alpha=None,
                rgba=None,
                confidence=0.0,
                engine_name=self.name,
                inference_time_ms=round(ms, 1),
                metadata=meta,
                gate="FAILED",
            )
        rgba = apply_mask(ctx.working_rgb, alpha, preserve_alpha=False)
        metrics = cheap_alpha_metrics(alpha)
        gate = classify_primary(metrics, free_mode="adaptive")
        meta["metrics"] = metrics
        meta["gate"] = gate
        meta["infer_wh"] = list(infer_wh) if infer_wh else None
        meta["soft_alpha"] = False
        if last_err:
            meta["last_error"] = last_err
        return ExtractionResult(
            alpha=alpha,
            rgba=rgba,
            confidence=float(metrics.get("score") or 0.0),
            engine_name=self.name,
            inference_time_ms=round(ms, 1),
            metadata=meta,
            gate=gate if gate != PRIMARY_INVALID else PRIMARY_INVALID,
        )
