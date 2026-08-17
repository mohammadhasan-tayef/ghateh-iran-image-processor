"""withoutBG local Open Weights — CPU ONNX, singleton session."""

from __future__ import annotations

import time
from typing import Any

from PIL import Image

from .integrity import cheap_alpha_metrics, classify_primary
from .types import ExtractionResult, ImageContext


class WithoutBGExtractionEngine:
    name = "withoutbg"

    def extract(self, ctx: ImageContext) -> ExtractionResult:
        from ghate_editor.model_service import get_withoutbg_model

        t0 = time.perf_counter()
        meta: dict[str, Any] = {"engine": self.name, "api": "open_weights"}
        try:
            model = get_withoutbg_model()
            working = ctx.working_rgb.convert("RGB")
            alpha = None
            inner = getattr(model, "model", None)
            if inner is not None and hasattr(inner, "estimate_alpha"):
                alpha = inner.estimate_alpha(working)
            else:
                cut = model.remove_background(working)
                alpha = cut.convert("RGBA").split()[-1]
                try:
                    cut.close()
                except Exception:
                    pass
            if not isinstance(alpha, Image.Image):
                raise TypeError("withoutbg_alpha_missing")
            alpha = alpha.convert("L")
            if alpha.size != working.size:
                alpha = alpha.resize(working.size, Image.Resampling.LANCZOS)
            rgba = working.convert("RGBA")
            rgba.putalpha(alpha)
            ms = (time.perf_counter() - t0) * 1000.0
            metrics = cheap_alpha_metrics(alpha)
            gate = classify_primary(metrics, free_mode=str(ctx.extraction_meta.get("free_mode") or "adaptive"))
            meta["metrics"] = metrics
            meta["gate"] = gate
            meta["soft_alpha"] = True
            meta["canvas_size"] = None
            try:
                sidecar = getattr(inner, "sidecar", None) or {}
                meta["canvas_size"] = sidecar.get("canvas_size")
                meta["model_version"] = sidecar.get("model_version")
            except Exception:
                pass
            return ExtractionResult(
                alpha=alpha,
                rgba=rgba,
                confidence=float(metrics.get("score") or 0.0),
                engine_name=self.name,
                inference_time_ms=round(ms, 1),
                metadata=meta,
                gate=gate,
            )
        except Exception as exc:  # noqa: BLE001
            ms = (time.perf_counter() - t0) * 1000.0
            meta["error"] = f"{type(exc).__name__}: {exc}"
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
