"""
Profile free-v1.14.0 pipeline stages on calibration images.

Usage:
  python scripts/profile_pipeline.py [--limit N] [--tag baseline|after]
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    analyze_scene,
    open_rgb,
    process_free_file,
)
from ghate_editor.model_service import warmup  # noqa: E402


def _collect_images(limit: int | None) -> list[Path]:
    goods = sorted((ROOT / "calibration" / "good").glob("*"))
    bads = sorted((ROOT / "calibration" / "bad").glob("*"))
    imgs = [p for p in goods + bads if p.suffix.lower() in {".heic", ".heif", ".jpg", ".jpeg", ".png"}]
    if limit:
        imgs = imgs[:limit]
    return imgs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=6)
    ap.add_argument("--tag", default="baseline")
    ap.add_argument("--mode", default="fast", choices=["fast", "adaptive", "quality"])
    args = ap.parse_args()

    imgs = _collect_images(args.limit)
    if not imgs:
        print("No calibration images found")
        return 1

    out_root = ROOT / "tmp_test" / f"profile_{args.tag}"
    out_root.mkdir(parents=True, exist_ok=True)
    approved = out_root / "Approved"
    approved.mkdir(parents=True, exist_ok=True)

    print(f"Pipeline: {FREE_PIPELINE_VERSION}")
    print(f"Warmup u2net...")
    t0 = time.perf_counter()
    info = warmup("u2net")
    print(f"  warmup {time.perf_counter()-t0:.2f}s device={info.get('device')} providers={info.get('active_providers') or info.get('providers')}")

    rows = []
    for i, src in enumerate(imgs, 1):
        dest = approved / f"{src.stem}.jpg"
        print(f"[{i}/{len(imgs)}] {src.name} ...", flush=True)
        t0 = time.perf_counter()
        try:
            result = process_free_file(
                src,
                dest,
                size=2000,
                with_shadow=False,
                quality=90,
                free_mode=args.mode,  # type: ignore[arg-type]
                package_review=True,
                review_dir=out_root / "Review",
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL {exc}")
            rows.append({"file": src.name, "error": str(exc), "total": time.perf_counter() - t0})
            continue
        total = time.perf_counter() - t0
        timings = dict(result.get("timings") or {})
        timings["wall_total"] = total
        timings["status"] = result.get("status")
        timings["file"] = src.name
        timings["model"] = result.get("model")
        timings["path_label"] = result.get("path_label")
        rows.append(timings)
        print(
            f"  {result.get('status')} total={total:.2f}s "
            f"infer={timings.get('infer',0):.2f} mask={timings.get('mask',0):.2f} "
            f"gate={timings.get('gate',0):.2f} composite={timings.get('composite',0):.2f}"
        )

    # Aggregate
    keys = ["decode", "infer", "fallback_infer", "mask", "gate", "composite", "save", "wall_total", "total"]
    print("\n=== AGGREGATE ===")
    summary = {"tag": args.tag, "version": FREE_PIPELINE_VERSION, "mode": args.mode, "n": len(rows), "stages": {}}
    for k in keys:
        vals = [float(r[k]) for r in rows if k in r and isinstance(r.get(k), (int, float))]
        if not vals:
            continue
        summary["stages"][k] = {
            "mean": round(st.mean(vals), 3),
            "median": round(st.median(vals), 3),
            "p95": round(sorted(vals)[max(0, int(0.95 * len(vals)) - 1)], 3),
            "min": round(min(vals), 3),
            "max": round(max(vals), 3),
        }
        print(f"  {k:16s} mean={summary['stages'][k]['mean']:.3f}  med={summary['stages'][k]['median']:.3f}  p95={summary['stages'][k]['p95']:.3f}")

    statuses = {}
    for r in rows:
        s = str(r.get("status") or r.get("error") or "?")
        statuses[s] = statuses.get(s, 0) + 1
    summary["statuses"] = statuses
    summary["rows"] = rows

    out_json = out_root / "profile_summary.json"
    out_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nWrote {out_json}")
    print("statuses", statuses)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
