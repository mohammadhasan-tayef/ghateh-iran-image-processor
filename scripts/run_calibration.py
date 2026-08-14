#!/usr/bin/env python3
"""
Validation / calibration harness for Adaptive quality gates.

Runs a limited real batch and reports production metrics.
Does NOT claim 90% ecommerce quality — that requires labeled human review.

Usage:
  python scripts/run_calibration.py --input "E:\\path\\to\\raw" --limit 20
  python scripts/run_calibration.py --input ... --limit 50 --output output_calib
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.batch import (  # noqa: E402
    BatchConfig,
    BatchState,
    format_production_metrics,
    list_images,
    run_batch,
)
from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    GATE_CONFIG,
    QualityGateConfig,
    set_gate_config,
)
from ghate_editor.review_io import (  # noqa: E402
    approved_dir,
    review_edited_dir,
    review_manifest_path,
    review_original_dir,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate calibration batch (real images)")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output_calibration",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--mode",
        choices=("adaptive", "fast", "quality"),
        default="adaptive",
    )
    parser.add_argument(
        "--no-skip",
        action="store_true",
        help="Reprocess even if outputs exist",
    )
    args = parser.parse_args()

    # Ensure defaults are active (edit QualityGateConfig / set_gate_config to tune)
    set_gate_config(GATE_CONFIG)

    images = list_images(args.input)[: args.limit]
    if not images:
        print(f"No images in {args.input}")
        return 1

    args.output.mkdir(parents=True, exist_ok=True)
    stage = args.output / "_calib_input"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for p in images:
        shutil.copy2(p, stage / p.name)

    print(
        f"Calibration: {len(images)} images · mode={args.mode} · "
        f"pipeline={FREE_PIPELINE_VERSION} → {args.output}"
    )
    print(
        f"Gate config: frame_soft_min={GATE_CONFIG.min_soft_cov_frame} "
        f"roi_fill={GATE_CONFIG.min_roi_fill} "
        f"fog_bad={GATE_CONFIG.fog_ratio_bad} "
        f"score_good={GATE_CONFIG.score_high_good}"
    )

    cfg = BatchConfig(
        input_dir=stage,
        output_dir=args.output,
        concurrency=1,
        engine="free",
        free_mode=args.mode,  # type: ignore[arg-type]
        skip_existing=not args.no_skip,
    )
    state = BatchState()
    run_batch(cfg, state, log=print)

    print()
    print(format_production_metrics(state))
    print()
    print(f"Approved dir:  {approved_dir(args.output)}")
    print(f"Review Edited: {review_edited_dir(args.output)}")
    print(f"Review Original copies: {review_original_dir(args.output)}")
    print(f"Manifest: {review_manifest_path(args.output)}")
    print()
    print(
        "NEXT: Manually spot-check Approved vs Review.\n"
        "Measure Approved precision and Review recall on a labeled set "
        "before claiming 90% production quality."
    )
    # Keep QualityGateConfig import visible for tuners
    _ = QualityGateConfig
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
