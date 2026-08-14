#!/usr/bin/env python3
"""Pilot harness: process up to N images from an input folder (needs FAL_KEY)."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from ghate_editor.batch import BatchConfig, BatchState, list_images, run_batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Pilot batch (50–100 images)")
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT / "golden" / "raw",
        help="Input folder (default: golden/raw for smoke pilot)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output_pilot",
        help="Output folder",
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument(
        "--engine",
        choices=("free", "pro"),
        default="free",
        help="free = local BiRefNet ($0); pro = fal Kontext",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    images = list_images(args.input)[: args.limit]
    if not images:
        print(f"No images in {args.input}")
        return 1

    # Stage limited set into a temp input so batch only sees pilot files
    stage = args.output / "_pilot_input"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for p in images:
        shutil.copy2(p, stage / p.name)

    print(f"Pilot: {len(images)} images · engine={args.engine} → {args.output}")
    cfg = BatchConfig(
        input_dir=stage,
        output_dir=args.output,
        concurrency=args.concurrency,
        engine=args.engine,
    )
    state = BatchState()
    run_batch(cfg, state, log=print)
    accept = state.succeeded
    total = state.succeeded + state.failed
    rate = (100.0 * accept / total) if total else 0.0
    print(f"Accept rate (ok/attempted): {rate:.1f}%  target ≥90%")
    print(f"ok={state.succeeded} fail={state.failed} skip={state.skipped}")
    return 0 if state.failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
