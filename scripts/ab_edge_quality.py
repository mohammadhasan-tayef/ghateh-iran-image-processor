#!/usr/bin/env python3
"""
A/B: CURRENT (legacy edges + color + optional shadow) vs NEW fidelity extraction.

Saves:
  tests/ab_edges/legacy/*.jpg
  tests/ab_edges/new/*.jpg
  tests/ab_edges/side_by_side/*.jpg
  tests/ab_edges/report.json

Usage:
  python scripts/ab_edge_quality.py
  python scripts/ab_edge_quality.py --raw-dir "E:\\ghateh iran\\aks kham" --limit 20
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    process_free_file,
)
from ghate_editor.model_service import release_memory  # noqa: E402

IMG_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp"}


def _list_raws(raw_dir: Path, limit: int) -> list[Path]:
    files = [
        p
        for p in sorted(raw_dir.iterdir())
        if p.is_file() and p.suffix.lower() in IMG_EXT
    ]
    return files[: max(1, limit)]


def _side_by_side(a: Path, b: Path, dest: Path, label_a: str, label_b: str) -> None:
    ia = Image.open(a).convert("RGB")
    ib = Image.open(b).convert("RGB")
    h = 900
    ia = ia.resize((int(ia.width * h / ia.height), h), Image.Resampling.LANCZOS)
    ib = ib.resize((int(ib.width * h / ib.height), h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (ia.width + ib.width + 24, h + 36), (240, 240, 240))
    canvas.paste(ia, (8, 28))
    canvas.paste(ib, (ia.width + 16, 28))
    canvas.save(dest, "JPEG", quality=88)


def _one(src: Path, dest: Path, *, legacy: bool, with_shadow: bool) -> dict:
    import shutil

    if legacy:
        os.environ["GHATE_LEGACY_EDGES"] = "1"
    else:
        os.environ.pop("GHATE_LEGACY_EDGES", None)
    t0 = time.perf_counter()
    result = process_free_file(
        src,
        dest,
        size=2000,
        with_shadow=with_shadow,
        free_mode="fast",
        package_review=False,
        review_dir=dest.parent.parent / ("Review_legacy" if legacy else "Review_new"),
    )
    elapsed = time.perf_counter() - t0
    saved = result.get("path")
    if saved and Path(saved).is_file() and Path(saved).resolve() != dest.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(saved, dest)
    studio = result.get("studio_processing") or {}
    return {
        "file": src.name,
        "legacy": legacy,
        "decision": result.get("qc_decision") or result.get("status"),
        "score": result.get("quality_score"),
        "elapsed_sec": round(elapsed, 3),
        "path": str(dest if dest.is_file() else (saved or dest)),
        "status": result.get("status"),
        "studio": {
            k: studio.get(k)
            for k in ("matting", "uncomposite", "decontam", "shadow", "enhance")
        },
        "shadow_opt": with_shadow,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(os.environ.get("GHATE_RAW_DIR", r"E:\ghateh iran\aks kham")),
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=ROOT / "tests" / "ab_edges")
    args = parser.parse_args()

    files = _list_raws(args.raw_dir, args.limit) if args.raw_dir.is_dir() else []
    if not files:
        print(f"No source images in {args.raw_dir}")
        return 2

    out = args.out
    (out / "legacy").mkdir(parents=True, exist_ok=True)
    (out / "new").mkdir(parents=True, exist_ok=True)
    (out / "side_by_side").mkdir(parents=True, exist_ok=True)

    print(f"pipeline={FREE_PIPELINE_VERSION} n={len(files)} raw={args.raw_dir}", flush=True)
    rows: list[dict] = []
    t_all = time.perf_counter()
    for i, src in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {src.name}", flush=True)
        try:
            release_memory(empty_cuda_cache=True)
        except Exception:
            pass
        dest_l = out / "legacy" / f"{src.stem}.jpg"
        dest_n = out / "new" / f"{src.stem}.jpg"
        rec_l = _one(src, dest_l, legacy=True, with_shadow=True)
        rec_n = _one(src, dest_n, legacy=False, with_shadow=False)
        pair = {
            "file": src.name,
            "legacy": rec_l,
            "new": rec_n,
        }
        # Prefer saved approved/review path if different
        pa = Path(rec_l["path"]) if rec_l.get("path") else dest_l
        pb = Path(rec_n["path"]) if rec_n.get("path") else dest_n
        if not pa.is_file():
            pa = dest_l
        if not pb.is_file():
            pb = dest_n
        if pa.is_file() and pb.is_file():
            _side_by_side(
                pa,
                pb,
                out / "side_by_side" / f"{src.stem}.jpg",
                "LEGACY",
                "NEW",
            )
        rows.append(pair)
        print(
            f"  legacy {rec_l.get('decision')} {rec_l['elapsed_sec']}s | "
            f"new {rec_n.get('decision')} {rec_n['elapsed_sec']}s "
            f"matting={rec_n.get('studio', {}).get('matting')}",
            flush=True,
        )

    elapsed_all = time.perf_counter() - t_all
    mem = {}
    try:
        import subprocess

        smi = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        ).strip()
        mem["nvidia_smi"] = smi
    except Exception:
        mem["nvidia_smi"] = None

    n = max(1, len(rows))
    report = {
        "pipeline": FREE_PIPELINE_VERSION,
        "n": len(rows),
        "legacy_mean_sec": round(sum(r["legacy"]["elapsed_sec"] for r in rows) / n, 3),
        "new_mean_sec": round(sum(r["new"]["elapsed_sec"] for r in rows) / n, 3),
        "wall_sec": round(elapsed_all, 2),
        "memory": mem,
        "legacy_path": "GHATE_LEGACY_EDGES=1, with_shadow=True, color/enhance on",
        "new_path": "fidelity matting + original RGB, with_shadow=False",
        "rows": rows,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
