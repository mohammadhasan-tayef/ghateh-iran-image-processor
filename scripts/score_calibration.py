#!/usr/bin/env python3
"""
Score known-good / known-bad calibration images against the weighted QC engine.

Place files in:
  calibration/good/   — should classify as PASS (Approve)
  calibration/bad/    — should NOT classify as PASS

Usage:
  python scripts/score_calibration.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.batch import list_images  # noqa: E402
from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    GATE_CONFIG,
    analyze_scene,
    apply_mask,
    classify_quality,
    compose_studio_square,
    evaluate_cutout_quality,
    evaluate_mask_quality,
    evaluate_structure_consistency,
    evaluate_studio_quality,
    open_rgb,
    segment_mask,
    INFER_MAX_SIDE_FAST,
    FREE_MODEL_FAST,
)
from ghate_editor.qc_config import get_qc_config  # noqa: E402


def _score_one(path: Path) -> dict:
    working = open_rgb(path)
    scene = analyze_scene(working)
    mask, _, _ = segment_mask(
        working,
        max_side=INFER_MAX_SIDE_FAST,
        model_name=FREE_MODEL_FAST,
        infer_boost=bool(scene.get("difficult")),
        scene=scene,
    )
    _, _, mstats = evaluate_mask_quality(mask, scene=scene)
    rgba = apply_mask(working, mask, preserve_alpha=False)
    _, _, cstats = evaluate_cutout_quality(rgba, scene=scene)
    _, _, ststats = evaluate_structure_consistency(working, rgba, scene=scene)
    analysis = compose_studio_square(
        rgba, with_shadow=False, gentle_edges=True, conservative_enhance=True
    )
    _, _, sstats = evaluate_studio_quality(analysis, scene=scene, cutout_stats=cstats)
    zone, score, reasons = classify_quality(
        mstats, cstats, sstats, structure_stats=ststats, filename=path.name
    )
    report = (sstats or {}).get("_qc_report") or {}
    for im in (working, mask, rgba, analysis):
        try:
            im.close()
        except Exception:
            pass
    return {
        "file": path.name,
        "zone": zone,
        "decision": report.get("decision"),
        "score": score,
        "reasons": reasons,
        "structure_loss": float(ststats.get("structure_loss") or 0.0),
        "triggered": report.get("triggered_rules"),
        "reason": report.get("reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=ROOT / "calibration")
    args = parser.parse_args()
    good_dir = args.dir / "good"
    bad_dir = args.dir / "bad"
    goods = list_images(good_dir) if good_dir.is_dir() else []
    bads = list_images(bad_dir) if bad_dir.is_dir() else []
    qcfg = get_qc_config()
    print(f"pipeline={FREE_PIPELINE_VERSION}")
    print(
        f"QC pass_min={qcfg.pass_min} second_pass_min={qcfg.second_pass_min} "
        f"gate score_high_good={GATE_CONFIG.score_high_good}"
    )
    if not goods and not bads:
        print(f"No images in {good_dir} or {bad_dir}")
        return 0

    false_review = 0
    false_ok = 0
    print("\n=== GOOD (expect PASS) ===")
    for p in goods:
        r = _score_one(p)
        ok = r["decision"] == "pass"
        if not ok:
            false_review += 1
        mark = "OK" if ok else "FALSE_REVIEW"
        print(
            f"[{mark}] {r['file']} decision={r['decision']} zone={r['zone']} "
            f"score={r['score']:.0f} struct={r['structure_loss']:.2f} "
            f"reason={r.get('reason')}"
        )

    print("\n=== BAD (expect not PASS) ===")
    for p in bads:
        r = _score_one(p)
        ok = r["decision"] != "pass"
        if not ok:
            false_ok += 1
        mark = "OK" if ok else "FALSE_PASS"
        print(
            f"[{mark}] {r['file']} decision={r['decision']} zone={r['zone']} "
            f"score={r['score']:.0f} struct={r['structure_loss']:.2f} "
            f"triggered={r.get('triggered')}"
        )

    print("\n=== SUMMARY ===")
    print(f"good={len(goods)} false_review={false_review}")
    print(f"bad={len(bads)} false_pass={false_ok}")
    return 0 if false_ok == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
