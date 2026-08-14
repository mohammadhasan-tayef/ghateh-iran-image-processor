"""
Golden QC regression harness (v4 — spatial confidence + real/synth split).

Folders (place human-verified finals here):
  tests/qc_golden/good_should_pass/   → expect PASS
  tests/qc_golden/bad_should_review/  → expect REVIEW (not PASS)

Synthetic cases cover:
  - false REVIEW: structure warn, multi-object kits, shadow removal
  - false PASS: washed product, selective wipe, white-out with clean bg

REAL folder images are included in acceptance metrics when paired RAW is found
(via GHATE_RAW_DIR / E:\\ghateh iran\\aks kham). Accuracy is reported separately
for REAL vs SYNTHETIC.

Usage:
  python scripts/test_qc_golden.py
  python scripts/test_qc_golden.py --skip-real
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
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
RAW_EXT = {".heic", ".heif", ".dng", ".cr2", ".nef", ".arw", ".raf", ".orf", ".rw2"}


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
        "spatial_evidence_confidence": "HIGH",
        "large_contiguous_foreground_loss": 0.0,
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
        "prior_kept_frac": 0.30,
        "strong_edge_keep": 0.30,
        "whiteout_frac": 0.40,
        "prior_unreliable": 0.0,
        "destruction_signal_count": 3.0,
        "spatial_evidence_confidence": "HIGH",
        "_bads": ["product_structure_destroyed", "product_whiteout", "detail_destroyed"],
        "_warns": [],
        "_posits": [],
        "_triggered": [
            "severe_prior_wipe",
            "severe_product_whiteout",
            "detail_collapse",
            "destruction_corroborated",
        ],
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


def _case_shadow_removal_good() -> dict:
    """RAW product + soft contact shadow; FINAL keeps product, clears shadow → PASS."""
    size = 420
    rgb = np.full((size, size, 3), 210, dtype=np.uint8)
    y0, y1, x0, x1 = 110, 310, 130, 290
    rgb[y0:y1, x0:x1] = (48, 48, 52)
    # Soft exterior contact shadow (dark, low texture)
    for dy in range(8, 36):
        shade = int(210 - max(8, 55 - dy))
        rgb[y1 : min(size, y1 + dy), x0 + 10 : x1 - 10] = (shade, shade, shade)
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[y0:y1, x0:x1] = 255  # shadow intentionally NOT in alpha
    rf = compute_raw_final_integrity(
        Image.fromarray(rgb, "RGB"),
        Image.fromarray(np.dstack([rgb, alpha]), "RGBA"),
    )
    return build_qc_report(
        _base_good_mask(_posits=["opaque_core", "dark_on_white", "plausible_coverage"]),
        _base_good_cutout(),
        _base_good_studio(bg_shadow_frac=0.0),
        {
            "structure_loss": 0.06,
            "edge_drop": 0.04,
            "_bads": [],
            "_warns": [],
            "_posits": ["structure_preserved", "edges_retained"],
        },
        raw_final_stats=rf,
        after_rescue=True,
        filename="synth_shadow_removal_good.jpg",
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
            bg_dirty_frac=0.001,
            light_grey_frac=0.15,
            product_visibility=50,
            product_mean=200,
            _posits=["readable_product"],
        ),
        {
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
    yy, xx = np.ogrid[:size, :size]
    cy, cx = size // 2, size // 2
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    product = r < 120
    mid = (r >= 60) & (r < 120)
    core = r < 60
    raw[product] = (40, 42, 45)
    raw[mid] = (160, 160, 165)
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[core] = 255
    rgba = np.dstack([raw, alpha])
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
        ("shadow_removal_good", "pass", _case_shadow_removal_good()),
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


def _stem_key(name: str) -> str:
    stem = Path(name).stem
    return re.sub(r"__[0-9a-f]{4,10}$", "", stem, flags=re.I)


def _raw_dirs() -> list[Path]:
    dirs: list[Path] = []
    env = os.environ.get("GHATE_RAW_DIR", "").strip()
    if env:
        dirs.append(Path(env))
    default = Path(r"E:\ghateh iran\aks kham")
    if default.is_dir():
        dirs.append(default)
    return dirs


def _resolve_raw(path: Path, raw_dirs: list[Path]) -> Path | None:
    if path.suffix.lower() in RAW_EXT:
        return path if path.is_file() else None
    key = _stem_key(path.name)
    for d in raw_dirs:
        if not d.is_dir():
            continue
        for ext in list(RAW_EXT) + [".jpg", ".jpeg", ".png"]:
            for cand in (d / f"{key}{ext}", d / f"{key}{ext.upper()}"):
                if cand.is_file():
                    return cand
    return None


def run_real_production(limit: int = 0) -> tuple[list, list]:
    """Score real golden folder images via production process_free_file."""
    from ghate_editor.free_pipeline import process_free_file

    raw_dirs = _raw_dirs()
    goods = (
        [p for p in GOOD_DIR.glob("*") if p.suffix.lower() in IMG_EXT]
        if GOOD_DIR.exists()
        else []
    )
    bads = (
        [p for p in BAD_DIR.glob("*") if p.suffix.lower() in IMG_EXT]
        if BAD_DIR.exists()
        else []
    )
    if limit > 0:
        goods, bads = goods[:limit], bads[:limit]

    good_out: list = []
    bad_out: list = []
    if not goods and not bads:
        return good_out, bad_out

    with tempfile.TemporaryDirectory(prefix="qc_golden_reg_") as tmp:
        work = Path(tmp)
        (work / "Approved").mkdir(parents=True, exist_ok=True)
        (work / "Review").mkdir(parents=True, exist_ok=True)

        def _one(p: Path, expected: str):
            raw = _resolve_raw(p, raw_dirs)
            if raw is None:
                return (
                    p.name,
                    expected,
                    "skip",
                    {"decision": "skip", "reason": "no_raw", "final_score": 0},
                )
            result = process_free_file(
                raw,
                work / "Approved" / f"{raw.stem}.jpg",
                size=2000,
                with_shadow=False,
                free_mode="adaptive",
                review_dir=work / "Review",
                package_review=False,
            )
            diag = result.get("qc_diagnostics") or {}
            decision = (
                result.get("qc_decision")
                or diag.get("decision")
                or ("pass" if result.get("status") == "approved" else "review")
            )
            rep = {
                "decision": decision,
                "final_score": result.get("quality_score") or diag.get("final_score"),
                "core_score": diag.get("core_score"),
                "triggered_rules": diag.get("triggered_rules") or [],
                "fatal_errors": diag.get("fatal_errors") or [],
                "reason": diag.get("reason") or ",".join(result.get("reasons") or []),
                "processing_profile": diag.get("processing_profile"),
                "raw_final": result.get("raw_final_stats") or {},
                "subscores": diag.get("subscores") or {},
            }
            return p.name, expected, decision, rep

        for p in goods:
            good_out.append(_one(p, "pass"))
        for p in bads:
            bad_out.append(_one(p, "review"))
    return good_out, bad_out


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
    scored = [(k, float(subs.get(k, 100) or 100)) for k in keys]
    scored.sort(key=lambda x: x[1])
    print(f"    lowest_subscores={scored[:5]}")


def _report_block(title: str, good_out: list, bad_out: list) -> dict:
    good_eval = [x for x in good_out if x[2] != "skip"]
    bad_eval = [x for x in bad_out if x[2] != "skip"]
    g_pass = sum(1 for _, e, a, _ in good_eval if a == "pass")
    g_false_rev = sum(1 for _, e, a, _ in good_eval if a == "review")
    g_false_sp = sum(1 for _, e, a, _ in good_eval if a == "second_pass")
    b_rev = sum(1 for _, e, a, _ in bad_eval if a == "review")
    b_false_pass = sum(1 for _, e, a, _ in bad_eval if a == "pass")
    b_false_sp = sum(1 for _, e, a, _ in bad_eval if a == "second_pass")
    b_caught = sum(1 for _, e, a, _ in bad_eval if a != "pass")

    print(f"\n=== {title} ===")
    print("GOOD EXPECTED PASS:")
    print(f"  Total: {len(good_eval)} (skipped={len(good_out) - len(good_eval)})")
    print(f"  Correct PASS: {g_pass}")
    print(f"  False REVIEW: {g_false_rev}")
    print(f"  False SECOND_PASS: {g_false_sp}")
    for name, exp, act, rep in good_out:
        if act == "skip":
            print(f"  SKIP {name} ({rep.get('reason')})")
        elif act != "pass":
            _print_miss(name, exp, act, rep)
        else:
            print(
                f"  OK  {name} score={rep.get('final_score')} "
                f"core={rep.get('core_score')}"
            )

    print("\nBAD EXPECTED REVIEW (not PASS):")
    print(f"  Total: {len(bad_eval)} (skipped={len(bad_out) - len(bad_eval)})")
    print(f"  Correct REVIEW: {b_rev}")
    print(f"  False PASS: {b_false_pass}")
    print(f"  False SECOND_PASS: {b_false_sp}")
    for name, exp, act, rep in bad_out:
        if act == "skip":
            print(f"  SKIP {name} ({rep.get('reason')})")
        elif act == "pass":
            _print_miss(name, exp, act, rep)
        else:
            print(
                f"  OK  {name} decision={act} score={rep.get('final_score')} "
                f"fatal={rep.get('fatal_errors')}"
            )

    accuracy = (g_pass + b_caught) / max(1, len(good_eval) + len(bad_eval))
    print(f"\n{title} Accuracy: {accuracy:.1%}")
    return {
        "good_total": len(good_eval),
        "good_pass": g_pass,
        "false_review": g_false_rev,
        "bad_total": len(bad_eval),
        "bad_review": b_rev,
        "false_pass": b_false_pass,
        "false_second_pass_on_bad": b_false_sp,
        "accuracy": accuracy,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-real", action="store_true")
    parser.add_argument("--limit-real", type=int, default=0)
    args = parser.parse_args()

    print("=== QC Golden Regression v4 (spatial confidence + real/synth) ===")
    good_out, bad_out = run_synthetic()
    synth = _report_block("SYNTHETIC", good_out, bad_out)

    real = None
    if not args.skip_real:
        try:
            rg, rb = run_real_production(limit=args.limit_real)
            if rg or rb:
                real = _report_block("REAL (production pipeline)", rg, rb)
            else:
                print("\n=== REAL ===")
                print("No real golden images found under tests/qc_golden/")
        except Exception as exc:  # noqa: BLE001
            print(f"\n=== REAL ===\n  ERROR running production golden: {exc}")

    out = ROOT / "tests" / "qc_golden" / "last_regression.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": "qc-v4-spatial-confidence",
        "synthetic": synth,
        "real": real,
        # Back-compat flat keys = synthetic (explicitly labeled)
        "good_total": synth["good_total"],
        "good_pass": synth["good_pass"],
        "false_review": synth["false_review"],
        "bad_total": synth["bad_total"],
        "bad_review": synth["bad_review"],
        "false_pass": synth["false_pass"],
        "accuracy_synthetic": synth["accuracy"],
        "accuracy_real": None if real is None else real["accuracy"],
    }
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nWrote {out}")
    print(f"SYNTHETIC accuracy: {synth['accuracy']:.1%}")
    if real is not None:
        print(f"REAL accuracy:      {real['accuracy']:.1%}")

    fail = bool(synth["false_review"] or synth["false_pass"])
    if real is not None:
        fail = fail or bool(real["false_review"] or real["false_pass"])
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
