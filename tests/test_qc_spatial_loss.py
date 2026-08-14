"""Spatial product-loss QC regression (contiguous disappearance)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.qc_engine import build_qc_report  # noqa: E402
from ghate_editor.qc_raw_final import compute_raw_final_integrity  # noqa: E402


def _base_mask(**extra):
    d = {
        "soft_coverage": 0.18,
        "solid_of_soft": 0.85,
        "fog_ratio": 0.1,
        "mean_alpha_soft": 200,
        "roi_fill": 0.5,
        "main_component_frac": 0.95,
        "n_significant_components": 1,
        "bbox_frac": 0.2,
        "bbox_aspect": 1.3,
        "_bads": [],
        "_warns": [],
        "_posits": ["opaque_core", "plausible_coverage", "strong_main_component", "dark_on_white"],
    }
    d.update(extra)
    return d


def _base_cut(**extra):
    d = {
        "fog_of_fg": 0.1,
        "visibility": 160,
        "near_white_in_solid": 0.05,
        "solid_std": 35,
        "edge_band_mean_alpha": 130,
        "_bads": [],
        "_warns": [],
        "_posits": ["strong_visibility"],
    }
    d.update(extra)
    return d


def _base_studio(**extra):
    d = {
        "product_mean": 60,
        "product_std": 40,
        "product_visibility": 170,
        "light_grey_frac": 0.05,
        "bg_dirty_frac": 0.001,
        "bg_shadow_frac": 0.0,
        "studio_roi_fill": 0.45,
        "product_frac": 0.15,
        "_bads": [],
        "_warns": [],
        "_posits": ["dark_on_white", "readable_product"],
    }
    d.update(extra)
    return d


def _product_pair(size: int = 420) -> tuple[np.ndarray, np.ndarray]:
    """Dark product with midtone body on light floor."""
    rgb = np.full((size, size, 3), 185, dtype=np.uint8)
    y0, y1, x0, x1 = size // 5, 4 * size // 5, size // 4, 3 * size // 4
    rgb[y0:y1, x0:x1] = (45, 45, 48)
    rgb[y0 + 30 : y1 - 30, x0 + 20 : x1 - 20] = (130, 130, 135)
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[y0:y1, x0:x1] = 255
    return rgb, alpha


def _qc_from_rgba(rgb: np.ndarray, alpha: np.ndarray) -> dict:
    rgba = np.dstack([rgb, alpha])
    rf = compute_raw_final_integrity(
        Image.fromarray(rgb, "RGB"), Image.fromarray(rgba, "RGBA")
    )
    return build_qc_report(
        _base_mask(),
        _base_cut(),
        _base_studio(),
        {
            "structure_loss": 0.08,
            "edge_drop": 0.05,
            "midtone_loss": 0.08,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved", "edges_retained"],
        },
        raw_final_stats=rf,
        after_rescue=True,
        filename="spatial_case.jpg",
    ), rf


def test_a_translate_scale_ok() -> None:
    rgb, alpha = _product_pair(400)
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert float(rf.get("large_contiguous_foreground_loss") or 0) < 0.5, rf
    assert float(rf.get("largest_missing_region_ratio") or 0) < 0.12, rf
    assert rep["decision"] == "pass", rep


def test_b_minor_5pct_ok() -> None:
    rgb, alpha = _product_pair(400)
    # punch a small hole (not contiguous catastrophe)
    alpha[180:200, 180:200] = 0
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert float(rf.get("largest_missing_region_ratio") or 0) < 0.18, rf
    assert rep["decision"] in ("pass", "second_pass"), rep


def test_c_30pct_contiguous_review() -> None:
    rgb, alpha = _product_pair(420)
    # Remove right ~35% of product body
    alpha[:, 210:] = 0
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert (
        float(rf.get("large_contiguous_foreground_loss") or 0) >= 0.5
        or float(rf.get("largest_missing_region_ratio") or 0) >= 0.18
    ), rf
    assert rep["decision"] == "review", (rep.get("decision"), rep.get("triggered_rules"), rf)


def test_d_arm_removed_review() -> None:
    rgb, alpha = _product_pair(420)
    # Structural arm: top strip of product
    alpha[84:160, 105:315] = 0
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert rep["decision"] == "review", (rep.get("decision"), rep.get("reason"), rf)


def test_e_internal_hole_ok() -> None:
    rgb, alpha = _product_pair(400)
    # RAW already has opening (paint hole into RAW too)
    rgb[170:230, 170:230] = 185
    alpha[170:230, 170:230] = 0
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert float(rf.get("large_contiguous_foreground_loss") or 0) < 0.5, rf
    assert rep["decision"] in ("pass", "second_pass"), rep


def test_f_multi_object_ok() -> None:
    size = 420
    rgb = np.full((size, size, 3), 190, dtype=np.uint8)
    alpha = np.zeros((size, size), dtype=np.uint8)
    rgb[60:180, 60:180] = (40, 40, 42)
    rgb[240:360, 240:360] = (35, 35, 38)
    alpha[60:180, 60:180] = 255
    alpha[240:360, 240:360] = 255
    rgba = np.dstack([rgb, alpha])
    rf = compute_raw_final_integrity(
        Image.fromarray(rgb, "RGB"), Image.fromarray(rgba, "RGBA")
    )
    rep = build_qc_report(
        _base_mask(
            main_component_frac=0.45,
            n_significant_components=2,
            _posits=[
                "multi_object_ok",
                "opaque_core",
                "plausible_coverage",
                "strong_main_component",
                "dark_on_white",
            ],
        ),
        _base_cut(),
        _base_studio(n_dark_components=2),
        {
            "structure_loss": 0.05,
            "edge_drop": 0.04,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved", "edges_retained"],
        },
        raw_final_stats=rf,
        after_rescue=True,
        filename="multi.jpg",
    )
    assert float(rf.get("large_contiguous_foreground_loss") or 0) < 0.5, rf
    assert rep["decision"] == "pass", rep


def test_g_shadow_removal_ok() -> None:
    """Contact shadow in RAW correctly removed in FINAL must not force REVIEW."""
    size = 420
    rgb = np.full((size, size, 3), 208, dtype=np.uint8)
    y0, y1, x0, x1 = 100, 300, 120, 300
    rgb[y0:y1, x0:x1] = (42, 42, 46)
    # Soft penumbra under product (dark + unstructured)
    for i, dy in enumerate(range(6, 40)):
        shade = int(208 - max(6, 48 - i))
        rgb[y1 : min(size, y1 + dy), x0 + 8 : x1 - 8] = (shade, shade, shade)
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[y0:y1, x0:x1] = 255
    rep, rf = _qc_from_rgba(rgb, alpha)
    assert float(rf.get("large_contiguous_foreground_loss") or 0) < 0.5, rf
    assert str(rf.get("spatial_evidence_confidence") or "").upper() in {
        "HIGH",
        "MEDIUM",
        "LOW",
    }, rf
    assert rep["decision"] in ("pass", "second_pass"), (
        rep.get("decision"),
        rep.get("triggered_rules"),
        rf,
    )


def main() -> int:
    tests = [
        test_a_translate_scale_ok,
        test_b_minor_5pct_ok,
        test_c_30pct_contiguous_review,
        test_d_arm_removed_review,
        test_e_internal_hole_ok,
        test_f_multi_object_ok,
        test_g_shadow_removal_ok,
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
