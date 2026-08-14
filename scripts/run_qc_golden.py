#!/usr/bin/env python3
"""
Golden QC regression harness.

Place representative *edited* studio JPGs (or source HEICs) under:

  tests/qc_samples/good_should_pass/   — expect PASS (high_good / Approved)
  tests/qc_samples/bad_should_review/  — expect REVIEW (high_bad) or SECOND_PASS

Runs the weighted QC engine (segment + score) and reports false PASS / false REVIEW.

Usage:
  python scripts/run_qc_golden.py
  python scripts/run_qc_golden.py --dir tests/qc_samples
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.batch import list_images  # noqa: E402
from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_MODEL_FAST,
    FREE_PIPELINE_VERSION,
    INFER_MAX_SIDE_FAST,
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
)
from ghate_editor.qc_config import get_qc_config  # noqa: E402


def _score_one(path: Path) -> dict:
    working = open_rgb(path)
    scene = analyze_scene(working)
    # If input is already a white-studio JPG, still run mask path for consistency
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
    decision = report.get("decision") or (
        "pass" if zone == "high_good" else "second_pass" if zone == "uncertain" else "review"
    )
    for im in (working, mask, rgba, analysis):
        try:
            im.close()
        except Exception:
            pass
    return {
        "file": path.name,
        "zone": zone,
        "decision": decision,
        "score": score,
        "reasons": reasons,
        "subscores": report.get("subscores"),
        "triggered": report.get("triggered_rules"),
        "reason": report.get("reason"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=ROOT / "tests" / "qc_samples")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    good_dir = args.dir / "good_should_pass"
    bad_dir = args.dir / "bad_should_review"
    # Fallback to calibration folders if golden set empty
    if not list_images(good_dir) and (ROOT / "calibration" / "good").is_dir():
        good_dir = ROOT / "calibration" / "good"
    if not list_images(bad_dir) and (ROOT / "calibration" / "bad").is_dir():
        bad_dir = ROOT / "calibration" / "bad"

    goods = list_images(good_dir) if good_dir.is_dir() else []
    bads = list_images(bad_dir) if bad_dir.is_dir() else []
    cfg = get_qc_config()
    print(f"pipeline={FREE_PIPELINE_VERSION}")
    print(
        f"QC pass_min={cfg.pass_min} second_pass_min={cfg.second_pass_min} "
        f"instant_struct_loss={cfg.instant_struct_loss}"
    )
    if not goods and not bads:
        print(f"No samples in {args.dir}")
        print("Add JPGs/HEICs under good_should_pass/ and bad_should_review/")
        return 0

    false_review = 0
    false_pass = 0
    rows: list[dict] = []

    print("\n=== GOOD (expect PASS) ===")
    for p in goods:
        r = _score_one(p)
        rows.append({**r, "expected": "pass"})
        ok = r["decision"] == "pass"
        # SECOND_PASS on a known-good is a soft miss (rescue may still Approve)
        soft = r["decision"] == "second_pass"
        if not ok and not soft:
            false_review += 1
        mark = "OK" if ok else ("SECOND_PASS" if soft else "FALSE_REVIEW")
        if soft:
            false_review += 0  # count separately? treat as soft miss
        print(
            f"[{mark}] {r['file']} decision={r['decision']} score={r['score']:.0f} "
            f"triggered={r.get('triggered')}"
        )
        if soft:
            false_review += 0.5  # type: ignore[assignment]

    # Recount soft misses as half — for exit code use integer false_review of hard only
    hard_false_review = sum(
        1
        for row in rows
        if row.get("expected") == "pass" and row["decision"] == "review"
    )
    soft_miss = sum(
        1
        for row in rows
        if row.get("expected") == "pass" and row["decision"] == "second_pass"
    )

    print("\n=== BAD (expect REVIEW or at least not PASS) ===")
    for p in bads:
        r = _score_one(p)
        rows.append({**r, "expected": "review"})
        ok = r["decision"] != "pass"
        if not ok:
            false_pass += 1
        mark = "OK" if ok else "FALSE_PASS"
        print(
            f"[{mark}] {r['file']} decision={r['decision']} score={r['score']:.0f} "
            f"triggered={r.get('triggered')}"
        )

    print("\n=== SUMMARY ===")
    print(f"good={len(goods)} false_review(hard)={hard_false_review} second_pass_miss={soft_miss}")
    print(f"bad={len(bads)} false_pass={false_pass}")
    if args.json_out:
        args.json_out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        print(f"wrote {args.json_out}")
    # Fail CI only on false PASS (approving bad) or hard false REVIEW
    return 0 if false_pass == 0 and hard_false_review == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
