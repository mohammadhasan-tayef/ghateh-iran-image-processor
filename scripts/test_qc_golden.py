"""
Golden QC regression harness (v3 — RAW-aware integrity).

Folders (place human-verified finals here):
  tests/qc_golden/good_should_pass/   → expect PASS
  tests/qc_golden/bad_should_review/  → expect REVIEW (not PASS)

Also runs synthetic cases covering:
  - false REVIEW: structure warn, multi-object kits
  - false PASS: washed product, selective wipe, white-out with clean bg

Usage:
  python scripts/test_qc_golden.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.qc_config import QCConfig, set_qc_config  # noqa: E402
from ghate_editor.qc_engine import build_qc_report  # noqa: E402
from ghate_editor.qc_raw_final import compute_raw_final_integrity  # noqa: E402

GOOD_DIR = ROOT / "tests" / "qc_golden" / "good_should_pass"
BAD_DIR = ROOT / "tests" / "qc_golden" / "bad_should_review"
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}


def _base_good_mask(**extra):
    d = {
        "soft_coverage": 0.12,
        "solid_of_soft": 0.78,
        "fog_ratio": 0.2,
        "mean_alpha_soft": 180,
        "roi_fill": 0.55,
        "main_component_frac": 0.9,
        "n_significant_components": 1,
        "bbox_frac": 0.15,
        "bbox_aspect": 1.4,
        "_bads": [],
        "_warns": [],
        "_posits": ["opaque_core", "plausible_coverage", "strong_main_component"],
    }
    d.update(extra)
    return d


def _base_good_cutout(**extra):
    d = {
        "fog_of_fg": 0.2,
        "visibility": 70,
        "near_white_in_solid": 0.05,
        "solid_std": 35,
        "edge_band_mean_alpha": 140,
        "_bads": [],
        "_warns": [],
        "_posits": ["strong_visibility"],
    }
    d.update(extra)
    return d


def _base_good_studio(**extra):
    d = {
        "product_mean": 55,
        "product_std": 40,
        "product_visibility": 80,
        "light_grey_frac": 0.05,
        "edge_inner_light_frac": 0.1,
        "bg_dirty_frac": 0.002,
        "bg_shadow_frac": 0.001,
        "studio_roi_fill": 0.5,
        "product_frac": 0.12,
        "_bads": [],
        "_warns": [],
        "_posits": ["dark_on_white", "readable_product"],
    }
    d.update(extra)
    return d


def _rf_good(**extra):
    d = {
        "structure_preservation_score": 92.0,
        "detail_retention_score": 88.0,
        "raw_final_edge_consistency_score": 90.0,
        "foreground_overexposure_score": 94.0,
        "raw_final_integrity": 91.0,
        "prior_wipe_frac": 0.05,
        "_bads": [],
        "_warns": [],
        "_posits": ["raw_final_integrity_ok"],
        "_triggered": [],
    }
    d.update(extra)
    return d


def _rf_destroyed(**extra):
    d = {
        "structure_preservation_score": 28.0,
        "detail_retention_score": 22.0,
        "raw_final_edge_consistency_score": 30.0,
        "foreground_overexposure_score": 18.0,
        "raw_final_integrity": 24.0,
        "prior_wipe_frac": 0.55,
        "whiteout_frac": 0.40,
        "_bads": ["product_structure_destroyed", "product_whiteout", "detail_destroyed"],
        "_warns": [],
        "_posits": [],
        "_triggered": ["severe_prior_wipe", "severe_product_whiteout", "detail_collapse"],
    }
    d.update(extra)
    return d


def _case_structure_warn_good() -> dict:
    return build_qc_report(
        _base_good_mask(
            _warns=["foreground_fragmented", "catastrophic_structure_loss"],
            _posits=[
                "opaque_core",
                "plausible_coverage",
                "strong_visibility",
                "dark_high_contrast",
                "dark_on_white",
            ],
        ),
        _base_good_cutout(),
        _base_good_studio(),
        {
            "structure_loss": 0.26,
            "edge_drop": 0.18,
            "midtone_loss": 0.15,
            "collapsed_regions": 0,
            "_bads": [],
            "_warns": ["catastrophic_structure_loss"],
            "_posits": [],
        },
        raw_final_stats=_rf_good(
            structure_preservation_score=84.0,
            raw_final_integrity=86.0,
        ),
        after_rescue=True,
        filename="synth_structure_warn_good.jpg",
    )


def _case_multi_object_kit() -> dict:
    return build_qc_report(
        _base_good_mask(
            main_component_frac=0.28,
            n_significant_components=5,
            n_solid_components=5,
            n_tiny_components=0,
            bbox_aspect=3.2,
            _bads=["foreground_fragmented"],
            _posits=[
                "multi_object_ok",
                "opaque_core",
                "plausible_coverage",
                "strong_main_component",
                "dark_on_white",
                "structure_preserved",
                "edges_retained",
            ],
        ),
        _base_good_cutout(_posits=["strong_visibility", "dark_high_contrast"]),
        _base_good_studio(
            n_dark_components=5,
            main_dark_frac=0.25,
            _posits=["multi_object_ok", "dark_on_white", "readable_product"],
        ),
        {
            "structure_loss": 0.08,
            "edge_drop": 0.05,
            "midtone_loss": 0.05,
            "collapsed_regions": 0,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved", "edges_retained"],
        },
        raw_final_stats=_rf_good(),
        filename="synth_multi_object_kit.jpg",
    )


def _case_false_pass_washed_product() -> dict:
    """Clean white bg + centered, but product body destroyed — must REVIEW."""
    return build_qc_report(
        _base_good_mask(
            soft_coverage=0.08,
            solid_of_soft=0.55,
            _posits=["opaque_core", "dark_on_white", "plausible_coverage"],
        ),
        _base_good_cutout(visibility=55, near_white_in_solid=0.35, solid_std=18),
        _base_good_studio(
            # Looks "clean" on canvas
            bg_dirty_frac=0.001,
            light_grey_frac=0.15,
            product_visibility=50,
            product_mean=200,
            _posits=["readable_product"],
        ),
        {
            # Old mask-based structure may under-report
            "structure_loss": 0.15,
            "edge_drop": 0.12,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved"],
        },
        raw_final_stats=_rf_destroyed(),
        filename="synth_false_pass_washed.jpg",
    )


def _case_washed_bad() -> dict:
    return build_qc_report(
        _base_good_mask(
            soft_coverage=0.05,
            solid_of_soft=0.2,
            fog_ratio=0.7,
            mean_alpha_soft=60,
            roi_fill=0.2,
            _bads=["product_faded", "foggy_soft_mask"],
            _posits=[],
        ),
        {
            "visibility": 6,
            "near_white_in_solid": 0.95,
            "solid_std": 3,
            "_bads": ["product_faded"],
            "_warns": [],
            "_posits": [],
        },
        {
            "product_mean": 250,
            "product_std": 4,
            "product_visibility": 5,
            "light_grey_frac": 0.95,
            "_bads": ["final_washed_out", "product_faded"],
            "_warns": [],
            "_posits": [],
        },
        {
            "structure_loss": 0.55,
            "_bads": ["catastrophic_structure_loss"],
            "_warns": [],
            "_posits": [],
        },
        raw_final_stats=_rf_destroyed(raw_final_integrity=15.0),
        filename="synth_washed_bad.jpg",
    )


def _case_empty_bad() -> dict:
    return build_qc_report(
        {"soft_coverage": 0.001, "_bads": ["empty_mask"], "_warns": [], "_posits": []},
        {"_bads": ["foreground_too_small"], "_warns": [], "_posits": []},
        {"_bads": ["final_too_white_small_product"], "_warns": [], "_posits": []},
        None,
        raw_final_stats=_rf_destroyed(raw_final_integrity=10.0),
        filename="synth_empty_bad.jpg",
    )


def _case_pixel_whiteout_integrity() -> dict:
    """Pixel-level: RAW dark product, FINAL cutout alpha wipes midtones to white."""
    size = 400
    raw = np.full((size, size, 3), 230, dtype=np.uint8)
    # Dark circular product with midtone ring
    yy, xx = np.ogrid[:size, :size]
    cy, cx = size // 2, size // 2
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    product = r < 120
    mid = (r >= 60) & (r < 120)
    core = r < 60
    raw[product] = (40, 42, 45)
    raw[mid] = (160, 160, 165)  # light-grey body
    # Bad cutout: only dark core kept; midtones wiped
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[core] = 255
    rgba = np.dstack([raw, alpha])
    # Studio: mostly white with tiny dark blob
    studio = np.full((500, 500, 3), 255, dtype=np.uint8)
    studio[200:280, 200:280] = (40, 42, 45)

    rf = compute_raw_final_integrity(
        Image.fromarray(raw, mode="RGB"),
        Image.fromarray(rgba, mode="RGBA"),
        Image.fromarray(studio, mode="RGB"),
    )
    return build_qc_report(
        _base_good_mask(_posits=["dark_on_white", "opaque_core"]),
        _base_good_cutout(),
        _base_good_studio(bg_dirty_frac=0.0, product_frac=0.05),
        {
            "structure_loss": 0.10,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved"],
        },
        raw_final_stats=rf,
        filename="synth_pixel_selective_wipe.jpg",
    )


def run_synthetic():
    set_qc_config(QCConfig())
    good = [
        ("structure_warn_good", "pass", _case_structure_warn_good()),
        ("multi_object_kit", "pass", _case_multi_object_kit()),
    ]
    bad = [
        ("washed_bad", "review", _case_washed_bad()),
        ("empty_bad", "review", _case_empty_bad()),
        ("false_pass_washed", "review", _case_false_pass_washed_product()),
        ("pixel_selective_wipe", "review", _case_pixel_whiteout_integrity()),
    ]
    return (
        [(n, e, r["decision"], r) for n, e, r in good],
        [(n, e, r["decision"], r) for n, e, r in bad],
    )


def _print_miss(name: str, expected: str, actual: str, rep: dict) -> None:
    print(f"\n  MISS: {name}")
    print(f"    Expected: {expected.upper()}  Actual: {actual.upper()}")
    print(
        f"    final={rep.get('final_score')} core={rep.get('core_score')} "
        f"aesthetic={rep.get('aesthetic_score')}"
    )
    print(f"    profile={rep.get('processing_profile')}")
    print(f"    triggered={rep.get('triggered_rules')}")
    print(f"    fatal={rep.get('fatal_errors')}")
    print(f"    reason={rep.get('reason')}")
    subs = rep.get("subscores") or {}
    keys = [
        "structure_preservation",
        "detail_retention",
        "foreground_overexposure",
        "raw_final_edge_consistency",
        "object_completeness",
        "background_purity",
        "composition",
    ]
    scored = [
        (k, float(subs.get(k, 100) or 100)) for k in keys if k in subs or True
    ]
    scored = [(k, float(subs.get(k, 100) or 100)) for k in keys]
    scored.sort(key=lambda x: x[1])
    print(f"    lowest_subscores={scored[:5]}")


def main() -> int:
    print("=== QC Golden Regression v3 (RAW-aware) ===")
    good_out, bad_out = run_synthetic()

    g_pass = sum(1 for _, e, a, _ in good_out if a == "pass")
    g_false_rev = sum(1 for _, e, a, _ in good_out if a == "review")
    g_false_sp = sum(1 for _, e, a, _ in good_out if a == "second_pass")
    b_rev = sum(1 for _, e, a, _ in bad_out if a == "review")
    b_false_pass = sum(1 for _, e, a, _ in bad_out if a == "pass")
    b_false_sp = sum(1 for _, e, a, _ in bad_out if a == "second_pass")

    print("\nGOOD EXPECTED PASS:")
    print(f"  Total: {len(good_out)}")
    print(f"  Correct PASS: {g_pass}")
    print(f"  False REVIEW: {g_false_rev}")
    print(f"  False SECOND_PASS: {g_false_sp}")
    for name, exp, act, rep in good_out:
        if act != "pass":
            _print_miss(name, exp, act, rep)
        else:
            print(
                f"  OK  {name} score={rep['final_score']} core={rep['core_score']} "
                f"profile={rep.get('processing_profile')}"
            )

    print("\nBAD EXPECTED REVIEW:")
    print(f"  Total: {len(bad_out)}")
    print(f"  Correct REVIEW: {b_rev}")
    print(f"  False PASS: {b_false_pass}")
    print(f"  False SECOND_PASS: {b_false_sp}")
    for name, exp, act, rep in bad_out:
        if act != "review":
            _print_miss(name, exp, act, rep)
        else:
            print(
                f"  OK  {name} score={rep['final_score']} "
                f"fatal={rep.get('fatal_errors')} "
                f"integ={((rep.get('raw_final') or {}).get('raw_final_integrity'))}"
            )

    good_files = (
        [p for p in GOOD_DIR.glob("*") if p.suffix.lower() in IMG_EXT]
        if GOOD_DIR.exists()
        else []
    )
    bad_files = (
        [p for p in BAD_DIR.glob("*") if p.suffix.lower() in IMG_EXT]
        if BAD_DIR.exists()
        else []
    )
    if good_files or bad_files:
        print(f"\n=== Folder images: good={len(good_files)} bad={len(bad_files)} ===")
        print("Place paired RAW/FINAL samples and use scripts/run_qc_golden.py for full pipeline.")

    false_review_rate = g_false_rev / max(1, len(good_out))
    false_pass_rate = b_false_pass / max(1, len(bad_out))
    # SECOND_PASS on bad is not ideal but better than PASS
    accuracy = (g_pass + b_rev) / max(1, len(good_out) + len(bad_out))
    print(f"\nFalse Review Rate: {false_review_rate:.1%}")
    print(f"False Pass Rate:   {false_pass_rate:.1%}")
    print(f"Overall Accuracy:  {accuracy:.1%}")

    out = ROOT / "tests" / "qc_golden" / "last_regression.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "version": "qc-v3-raw-final",
                "good_total": len(good_out),
                "good_pass": g_pass,
                "false_review": g_false_rev,
                "bad_total": len(bad_out),
                "bad_review": b_rev,
                "false_pass": b_false_pass,
                "false_second_pass_on_bad": b_false_sp,
                "accuracy": accuracy,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    if g_false_rev or b_false_pass:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
