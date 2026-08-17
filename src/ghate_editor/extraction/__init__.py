"""Adaptive product extraction: engines, integrity gate, candidate selection."""

from .enhancer import ProductEnhancer
from .lock import AlphaMutationError, FinalAlpha, lock_alpha
from .pipeline import run_adaptive_extraction, resolve_extraction_pipeline
from .types import ExtractionEngine, ExtractionResult, ImageContext

__all__ = [
    "AlphaMutationError",
    "ExtractionEngine",
    "ExtractionResult",
    "FinalAlpha",
    "ImageContext",
    "ProductEnhancer",
    "lock_alpha",
    "resolve_extraction_pipeline",
    "run_adaptive_extraction",
]
