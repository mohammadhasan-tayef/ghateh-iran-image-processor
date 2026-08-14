"""Transform-invariance + RAW prior reliability tests for QC integrity."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.qc_raw_final import (  # noqa: E402
    PRIOR_RELIABLE_MAX_FRAC,
    compute_raw_final_integrity,
    estimate_raw_product_prior,
)


def _make_dark_product(size: int = 400) -> tuple[Image.Image, Image.Image]:
    """Dark product on light floor + correct cutout (commercially good)."""
    rgb = np.full((size, size, 3), 180, dtype=np.uint8)
    # textured floor variation
    rng = np.random.default_rng(0)
    rgb = np.clip(rgb.astype(np.int16) + rng.integers(-12, 13, rgb.shape), 0, 255).astype(
        np.uint8
    )
    y0, y1, x0, x1 = size // 4, 3 * size // 4, size // 3, 2 * size // 3
    rgb[y0:y1, x0:x1] = (35, 35, 38)
    # slight midtone plastic band (must be kept)
    rgb[y0 + 20 : y0 + 50, x0 + 10 : x1 - 10] = (120, 120, 125)
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[y0:y1, x0:x1] = 255
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgb, "RGB"), Image.fromarray(rgba, "RGBA")


def _make_washed_false_pass(size: int = 400) -> tuple[Image.Image, Image.Image]:
    """Grey body wiped; only dark fragment remains — must stay REVIEW."""
    rgb = np.full((size, size, 3), 245, dtype=np.uint8)
    y0, y1, x0, x1 = size // 5, 4 * size // 5, size // 4, 3 * size // 4
    rgb[y0:y1, x0:x1] = (150, 150, 155)
    rgb[y0 + 40 : y1 - 40, x0 + 40 : x1 - 40] = (40, 40, 42)
    # cutout keeps only dark core
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[y0 + 40 : y1 - 40, x0 + 40 : x1 - 40] = 255
    rgba = np.dstack([rgb, alpha])
    return Image.fromarray(rgb, "RGB"), Image.fromarray(rgba, "RGBA")


def _shift(img: Image.Image, dy: int, dx: int, fill=(255, 255, 255, 0)) -> Image.Image:
    arr = np.asarray(img)
    out = np.zeros_like(arr)
    if img.mode == "RGB":
        out[:] = fill[:3]
    else:
        out[:] = fill
    h, w = arr.shape[:2]
    ys = slice(max(0, dy), min(h, h + dy))
    xs = slice(max(0, dx), min(w, w + dx))
    sy = slice(max(0, -dy), min(h, h - dy))
    sx = slice(max(0, -dx), min(w, w - dx))
    out[ys, xs] = arr[sy, sx]
    return Image.fromarray(out, img.mode)


def test_prior_not_full_frame_on_busy_bg() -> None:
    rgb, _ = _make_dark_product(512)
    prior = estimate_raw_product_prior(np.asarray(rgb, dtype=np.uint8))
    frac = float(prior.mean())
    assert frac <= PRIOR_RELIABLE_MAX_FRAC + 0.05, f"prior still bloated: {frac:.3f}"
    assert frac >= 0.05, f"prior empty: {frac:.3f}"


def test_good_cutout_not_structure_destroyed() -> None:
    rgb, rgba = _make_dark_product(420)
    stats = compute_raw_final_integrity(rgb, rgba)
    assert "product_structure_destroyed" not in (stats.get("_bads") or []), stats
    assert float(stats["structure_preservation_score"]) >= 70.0, stats
    assert float(stats["raw_final_integrity"]) >= 60.0, stats


def test_selective_wipe_still_destroyed() -> None:
    rgb, rgba = _make_washed_false_pass(420)
    stats = compute_raw_final_integrity(rgb, rgba)
    assert "product_structure_destroyed" in (stats.get("_bads") or []), stats


def test_transform_invariance_translate_pad() -> None:
    rgb, rgba = _make_dark_product(360)
    base = compute_raw_final_integrity(rgb, rgba)

    # Translate both RAW and cutout identically (legitimate pipeline motion)
    rgb_t = _shift(rgb, 25, 18, fill=(180, 180, 180))
    rgba_t = _shift(rgba, 25, 18, fill=(180, 180, 180, 0))
    # restore alpha fill correctly
    a = np.asarray(rgba_t)
    # floor RGB where alpha 0
    moved = compute_raw_final_integrity(rgb_t, Image.fromarray(a, "RGBA"))

    for key in (
        "structure_preservation_score",
        "detail_retention_score",
        "raw_final_edge_consistency_score",
    ):
        b, m = float(base[key]), float(moved[key])
        assert abs(b - m) <= 12.0, f"{key} shifted too much: {b} vs {m}"


def test_uniform_resize_invariance() -> None:
    rgb, rgba = _make_dark_product(320)
    base = compute_raw_final_integrity(rgb, rgba)
    rgb2 = rgb.resize((480, 480), Image.Resampling.BILINEAR)
    rgba2 = rgba.resize((480, 480), Image.Resampling.NEAREST)
    scaled = compute_raw_final_integrity(rgb2, rgba2)
    for key in (
        "structure_preservation_score",
        "detail_retention_score",
        "raw_final_edge_consistency_score",
    ):
        b, m = float(base[key]), float(scaled[key])
        assert abs(b - m) <= 20.0, f"{key} resize drift: {b} vs {m}"


def main() -> int:
    tests = [
        test_prior_not_full_frame_on_busy_bg,
        test_good_cutout_not_structure_destroyed,
        test_selective_wipe_still_destroyed,
        test_transform_invariance_translate_pad,
        test_uniform_resize_invariance,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{'All' if not failed else failed} tests {'passed' if not failed else 'failed'}.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
