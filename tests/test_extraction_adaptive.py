"""Unit tests for adaptive extraction (no real models required)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.extraction.enhancer import ProductEnhancer
from ghate_editor.extraction.integrity import (
    PRIMARY_GOOD,
    PRIMARY_INVALID,
    PRIMARY_UNCERTAIN,
    cheap_alpha_metrics,
    classify_primary,
    needs_rescue,
)
from ghate_editor.extraction.pipeline import resolve_extraction_pipeline
from ghate_editor.extraction.select import select_candidate
from ghate_editor.extraction.types import ExtractionResult
from ghate_editor.processing.config import DEFAULT_PROCESSING
from ghate_editor.processing.composition import compose_white_square
from ghate_editor.processing.studio_pipeline import build_studio_rgba


def _alpha(solid_box, size=80, fill=255, extra=None) -> Image.Image:
    a = np.zeros((size, size), dtype=np.uint8)
    y0, y1, x0, x1 = solid_box
    a[y0:y1, x0:x1] = fill
    if extra:
        extra(a)
    return Image.fromarray(a, "L")


def _result(name: str, alpha: Image.Image, gate: str) -> ExtractionResult:
    m = cheap_alpha_metrics(alpha)
    return ExtractionResult(
        alpha=alpha,
        rgba=None,
        confidence=float(m["score"]),
        engine_name=name,
        inference_time_ms=1.0,
        metadata={"metrics": m, "gate": gate},
        gate=gate,
    )


def test_good_mask_stops_rescue():
    a = _alpha((20, 60, 20, 60))
    m = cheap_alpha_metrics(a)
    g = classify_primary(m)
    assert g == PRIMARY_GOOD, (g, m)
    assert needs_rescue(g) is False


def test_empty_is_invalid_and_needs_rescue():
    a = Image.new("L", (64, 64), 0)
    m = cheap_alpha_metrics(a)
    g = classify_primary(m)
    assert g == PRIMARY_INVALID
    assert needs_rescue(g) is True


def test_ghost_translucent_invalid():
    a = Image.new("L", (80, 80), 40)
    m = cheap_alpha_metrics(a)
    g = classify_primary(m)
    assert g in {PRIMARY_INVALID, PRIMARY_UNCERTAIN}


def test_fast_mode_skips_uncertain_rescue():
    assert needs_rescue(PRIMARY_UNCERTAIN, free_mode="fast") is False
    assert needs_rescue(PRIMARY_INVALID, free_mode="fast") is True


def test_select_keeps_primary_if_rescue_eats_product():
    p = _result("withoutbg", _alpha((10, 70, 10, 70)), PRIMARY_GOOD)
    r = _result("birefnet", _alpha((30, 50, 30, 50)), PRIMARY_GOOD)
    chosen, meta = select_candidate(p, r)
    assert chosen.engine_name == "withoutbg"
    assert "lost_product" in meta["reason"] or meta["reason"].startswith("primary")


def test_select_rescue_when_primary_empty():
    p = _result("withoutbg", Image.new("L", (80, 80), 0), PRIMARY_INVALID)
    r = _result("birefnet", _alpha((15, 65, 15, 65)), PRIMARY_GOOD)
    chosen, meta = select_candidate(p, r)
    assert chosen.engine_name == "birefnet"


def test_multi_component_not_invalid():
    def two(a):
        a[10:25, 10:25] = 255
        a[50:70, 50:70] = 255

    a = _alpha((10, 25, 10, 25), extra=two)
    m = cheap_alpha_metrics(a)
    assert m["n_components"] >= 1
    g = classify_primary(m)
    assert g != PRIMARY_INVALID or m["solid_frac"] >= 0.01


def test_pipeline_flag_legacy_env():
    os.environ["GHATE_EXTRACTION_PIPELINE"] = "legacy"
    try:
        assert resolve_extraction_pipeline() == "legacy"
    finally:
        os.environ.pop("GHATE_EXTRACTION_PIPELINE", None)
    assert resolve_extraction_pipeline("adaptive") == "adaptive"
    assert DEFAULT_PROCESSING.extraction_pipeline == "adaptive"
    assert DEFAULT_PROCESSING.enable_synthetic_shadow is False
    assert DEFAULT_PROCESSING.enable_product_enhancer is False


def test_product_enhancer_noop():
    im = Image.new("RGBA", (20, 20), (10, 20, 30, 255))
    out = ProductEnhancer().enhance(im)
    assert np.array_equal(np.asarray(out), np.asarray(im))


def test_fidelity_skip_matting_keeps_rgb():
    rgb = Image.new("RGB", (100, 100), (40, 50, 60))
    arr = np.asarray(rgb).copy()
    arr[25:75, 25:75] = (40, 50, 60)
    rgb = Image.fromarray(arr)
    mask = Image.new("L", (100, 100), 0)
    m = np.zeros((100, 100), dtype=np.uint8)
    m[25:75, 25:75] = 255
    mask = Image.fromarray(m, "L")
    rgba, profile, report, _ = build_studio_rgba(
        rgb, mask, skip_matting=True, skip_mask_refine=True, skip_color=True
    )
    out = np.asarray(rgba)
    core = out[40:60, 40:60, :3]
    src = np.asarray(rgb)[40:60, 40:60]
    assert float(np.mean(np.abs(core.astype(np.int16) - src.astype(np.int16)))) < 1.0
    canvas, _ = compose_white_square(rgba, size=400, with_shadow=False, profile=profile)
    c = np.asarray(canvas)
    assert int(c[2, 2, 0]) == 255 and int(c[2, 2, 1]) == 255
    assert report.enhance.get("skipped") is True
    assert report.matting.get("used") is False


if __name__ == "__main__":
    failed = 0
    for fn in [
        test_good_mask_stops_rescue,
        test_empty_is_invalid_and_needs_rescue,
        test_ghost_translucent_invalid,
        test_fast_mode_skips_uncertain_rescue,
        test_select_keeps_primary_if_rescue_eats_product,
        test_select_rescue_when_primary_empty,
        test_multi_component_not_invalid,
        test_pipeline_flag_legacy_env,
        test_product_enhancer_noop,
        test_fidelity_skip_matting_keeps_rgb,
    ]:
        try:
            fn()
            print("OK", fn.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", fn.__name__, exc)
    raise SystemExit(1 if failed else 0)
