"""Adaptive extraction orchestrator: withoutBG primary → cheap gate → optional BiRefNet."""

from __future__ import annotations

import os
import time
from typing import Any, Literal

from .integrity import needs_rescue
from .select import select_candidate
from .types import ExtractionResult, ImageContext

ExtractionPipeline = Literal["adaptive", "legacy"]


def resolve_extraction_pipeline(explicit: str | None = None) -> ExtractionPipeline:
    raw = (explicit or os.environ.get("GHATE_EXTRACTION_PIPELINE") or "").strip().lower()
    if raw in {"legacy", "legacy_rembg", "u2net"}:
        return "legacy"
    if raw in {"adaptive", "withoutbg", ""}:
        if raw == "":
            try:
                from ghate_editor.processing.config import DEFAULT_PROCESSING

                val = str(getattr(DEFAULT_PROCESSING, "extraction_pipeline", "adaptive")).lower()
                if val in {"legacy", "legacy_rembg"}:
                    return "legacy"
            except Exception:
                pass
        return "adaptive"
    return "adaptive"


def run_adaptive_extraction(
    ctx: ImageContext,
    *,
    free_mode: str = "adaptive",
    primary_engine: str = "withoutbg",
    rescue_engine: str = "birefnet",
) -> ExtractionResult:
    """
    Primary withoutBG (CPU). BiRefNet rescue only if the cheap gate says so.
    Never loads BiRefNet when primary is clearly good.
    """
    ctx.extraction_meta["free_mode"] = free_mode
    t_all = time.perf_counter()
    primary = _run_engine(primary_engine, ctx)
    gate = primary.gate or (primary.metadata or {}).get("gate") or "UNCERTAIN"
    rescue: ExtractionResult | None = None
    rescue_ran = False
    if needs_rescue(str(gate), free_mode=free_mode):
        rescue_ran = True
        rescue = _run_engine(rescue_engine, ctx)
        try:
            from ghate_editor.model_service import release_memory

            # Free GPU after the one rescue inference; keep withoutBG (CPU) resident.
            release_memory(empty_cuda_cache=True)
        except Exception:
            pass

    chosen, sel_meta = select_candidate(primary, rescue)
    if chosen.alpha is not None:
        from .lock import lock_alpha

        chosen.locked_alpha = lock_alpha(
            chosen.alpha, source_engine=chosen.engine_name
        )
        # Expose a copy; the lock buffer is the source of truth.
        chosen.alpha = chosen.locked_alpha.image()
        meta_lock = chosen.locked_alpha.to_meta()
    else:
        meta_lock = None
    # Drop the unused full RGBA to keep RAM bounded.
    if rescue is not None and chosen is not rescue and rescue.rgba is not None:
        try:
            rescue.rgba.close()
        except Exception:
            pass
        rescue.rgba = None
    if primary is not chosen and primary.rgba is not None and chosen is rescue:
        try:
            primary.rgba.close()
        except Exception:
            pass
        primary.rgba = None

    meta: dict[str, Any] = dict(chosen.metadata or {})
    meta.update(
        {
            "pipeline": "adaptive",
            "primary_engine": primary.engine_name,
            "rescue_engine": rescue.engine_name if rescue else None,
            "selected_engine": chosen.engine_name,
            "primary_gate": gate,
            "rescue_ran": rescue_ran,
            "candidate_select": sel_meta,
            "primary_ms": primary.inference_time_ms,
            "rescue_ms": rescue.inference_time_ms if rescue else None,
            "total_extract_ms": round((time.perf_counter() - t_all) * 1000.0, 1),
            "primary_candidate": primary.engine_name,
            "rescue_candidate": rescue.engine_name if rescue else None,
            "selected_candidate": chosen.engine_name,
            "alpha_lock": meta_lock,
        }
    )
    chosen.metadata = meta
    ctx.selected_alpha = chosen.alpha
    ctx.extraction_meta.update(meta)
    if chosen.locked_alpha is not None:
        ctx.extraction_meta["alpha_checksum"] = chosen.locked_alpha.checksum
    return chosen


def _run_engine(name: str, ctx: ImageContext) -> ExtractionResult:
    key = (name or "withoutbg").lower()
    if key in {"withoutbg", "without_bg", "open_weights"}:
        from .withoutbg_engine import WithoutBGExtractionEngine

        return WithoutBGExtractionEngine().extract(ctx)
    if key in {"birefnet", "birefnet-general", "quality"}:
        from .birefnet_engine import ExistingBiRefNetExtractionEngine

        return ExistingBiRefNetExtractionEngine().extract(ctx)
    raise ValueError(f"unknown extraction engine: {name}")
