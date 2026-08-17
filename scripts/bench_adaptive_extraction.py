#!/usr/bin/env python3
"""Real-image benchmark for adaptive extraction (withoutBG primary, BiRefNet rescue).

Saves under tests/ab_adaptive/:
  raw/  primary/  rescue/  final/  legacy/  comparisons/  report.csv  report.json

Usage:
  .\\.venv\\Scripts\\python.exe scripts/bench_adaptive_extraction.py
  .\\.venv\\Scripts\\python.exe scripts/bench_adaptive_extraction.py --limit 50 --with-legacy
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402

from ghate_editor.extraction.pipeline import resolve_extraction_pipeline  # noqa: E402
from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    open_rgb,
    process_free_file,
)
from ghate_editor.model_service import (  # noqa: E402
    release_memory,
    warmup_withoutbg,
    withoutbg_load_sec,
)

IMG_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp"}
CASES = ROOT / "scripts" / "ab_extraction_cases.tsv"


def _vram() -> float | None:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        ).strip()
        return float(out.splitlines()[0].split(",")[0].strip())
    except Exception:
        return None


def _rss() -> float | None:
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD)] + [
                (n, ctypes.c_size_t)
                for n in (
                    "PageFaultCount",
                    "PeakWorkingSetSize",
                    "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage",
                    "QuotaPagedPoolUsage",
                    "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage",
                    "PagefileUsage",
                    "PeakPagefileUsage",
                )
            ]

        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        ok = ctypes.WinDLL("psapi").GetProcessMemoryInfo(
            ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
        )
        return float(c.PeakWorkingSetSize) / (1024 * 1024) if ok else None
    except Exception:
        return None


def _stems_from_cases(limit: int) -> list[str]:
    stems: list[str] = []
    if CASES.is_file():
        for line in CASES.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                stems.append(parts[1].strip())
    return stems[:limit]


def _spread(raw: Path, have: list[Path], need: int) -> list[Path]:
    all_files = sorted(
        p for p in raw.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXT
    )
    have_set = {p.resolve() for p in have}
    rest = [p for p in all_files if p.resolve() not in have_set]
    if need <= 0 or not rest:
        return []
    step = max(1, len(rest) // need)
    return rest[::step][:need]


def _resolve(raw: Path, stem: str) -> Path | None:
    hits = list(raw.glob(f"*{stem}.*"))
    return hits[0] if hits else None


def _white(rgba: Image.Image, dest: Path, size: int = 2000) -> None:
    canvas, _ = compose_white_square(rgba, size=size, with_shadow=False)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "JPEG", quality=90)


def _pct(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    k = min(len(s) - 1, max(0, int(round((p / 100.0) * (len(s) - 1)))))
    return round(s[k], 3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(os.environ.get("GHATE_RAW_DIR", r"E:\ghateh iran\aks kham")),
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", type=Path, default=ROOT / "tests" / "ab_adaptive")
    parser.add_argument("--with-legacy", action="store_true")
    args = parser.parse_args()
    with_legacy = bool(args.with_legacy)

    raw = args.raw_dir
    if not raw.is_dir():
        print("missing raw", raw)
        return 2
    files: list[Path] = []
    for stem in _stems_from_cases(args.limit):
        p = _resolve(raw, stem)
        if p:
            files.append(p)
    files.extend(_spread(raw, files, args.limit - len(files)))
    files = files[: args.limit]
    if not files:
        print("no files")
        return 2

    out = args.out
    for name in ("raw", "primary", "rescue", "final", "legacy", "comparisons"):
        (out / name).mkdir(parents=True, exist_ok=True)

    print(f"pipeline={FREE_PIPELINE_VERSION} extraction={resolve_extraction_pipeline()} n={len(files)}")
    winfo = warmup_withoutbg()
    print("withoutBG load", winfo.get("model_load_sec"), "vram", _vram())

    rows: list[dict] = []
    times: list[float] = []
    peak_vram = _vram() or 0.0
    peak_rss = _rss() or 0.0
    t_batch = time.perf_counter()
    rescue_n = 0
    counts = {"approved": 0, "review": 0, "failed": 0}

    for i, src in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {src.name}", flush=True)
        working = open_rgb(src)
        working.save(out / "raw" / f"{src.stem}.jpg", "JPEG", quality=85)
        dest = out / "final" / f"{src.stem}.jpg"
        t0 = time.perf_counter()
        result = process_free_file(
            src,
            dest,
            size=2000,
            with_shadow=False,
            free_mode="adaptive",
            extraction_pipeline="adaptive",
            package_review=False,
            working=working,
        )
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        status = result.get("status") or "failed"
        counts[status] = counts.get(status, 0) + 1
        saved = result.get("path")
        if saved and Path(saved).is_file() and Path(saved).resolve() != dest.resolve():
            dest.write_bytes(Path(saved).read_bytes())
        em = result.get("extraction") or {}
        rescue_ran = bool(em.get("rescue_ran"))
        if not rescue_ran:
            rescue_ran = float((result.get("timings") or {}).get("fallback_infer") or 0) > 0.08
        if rescue_ran:
            rescue_n += 1
        rec: dict = {
            "file": src.name,
            "status": status,
            "sec": round(elapsed, 3),
            "selected": em.get("selected_engine"),
            "gate": em.get("primary_gate"),
            "rescue_ran": bool(em.get("rescue_ran")),
            "primary_ms": em.get("primary_ms"),
            "rescue_ms": em.get("rescue_ms"),
            "select": (em.get("candidate_select") or {}).get("reason"),
            "qc": result.get("qc_decision") or result.get("quality_score"),
            "infer_sec": (result.get("timings") or {}).get("infer"),
            "rescue_sec": (result.get("timings") or {}).get("fallback_infer"),
        }
        if with_legacy:
            dest_l = out / "legacy" / f"{src.stem}.jpg"
            rleg = process_free_file(
                src,
                dest_l,
                size=2000,
                with_shadow=False,
                free_mode="adaptive",
                extraction_pipeline="legacy",
                package_review=False,
                working=working,
            )
            rec["legacy_status"] = rleg.get("status")
            rec["legacy_sec"] = round(float((rleg.get("timings") or {}).get("total") or 0), 3)
            try:
                release_memory(empty_cuda_cache=True)
            except Exception:
                pass
        v = _vram()
        r = _rss()
        if v:
            peak_vram = max(peak_vram, v)
        if r:
            peak_rss = max(peak_rss, r)
        rec["vram_mb"] = v
        rows.append(rec)
        print(
            f"  {status} {elapsed:.2f}s sel={em.get('selected_engine')} "
            f"gate={em.get('primary_gate')} rescue={em.get('rescue_ran')}",
            flush=True,
        )
        try:
            working.close()
        except Exception:
            pass

    wall = time.perf_counter() - t_batch
    n = max(1, len(times))
    summary = {
        "pipeline": FREE_PIPELINE_VERSION,
        "extraction": "adaptive",
        "primary": "withoutbg",
        "rescue": "birefnet",
        "n": len(rows),
        "wall_sec": round(wall, 2),
        "mean_sec": round(sum(times) / n, 3),
        "p50_sec": _pct(times, 50),
        "p95_sec": _pct(times, 95),
        "withoutbg_load_sec": withoutbg_load_sec(),
        "rescue_n": rescue_n,
        "rescue_rate": round(rescue_n / max(1, len(rows)), 3),
        "peak_vram_mb": peak_vram,
        "peak_rss_mb": peak_rss,
        "counts": counts,
        "rows": rows,
    }
    (out / "report.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    with (out / "report.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["file"])
        w.writeheader()
        w.writerows(rows)
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
