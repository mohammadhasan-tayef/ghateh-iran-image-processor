#!/usr/bin/env python3
"""Isolated A/B harness: current pipeline vs withoutBG Open Weights vs BiRefNet.

Does NOT change production routing, QC thresholds, or rembg defaults.
withoutBG runs in .venv-withoutbg (CPU onnxruntime) so DirectML is untouched.

Usage:
  .\\.venv\\Scripts\\python.exe scripts/ab_extraction.py
  .\\.venv\\Scripts\\python.exe scripts/ab_extraction.py --raw-dir \"E:\\ghateh iran\\aks kham\" --limit 16
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_MODEL_FAST,
    FREE_MODEL_QUALITY,
    FREE_PIPELINE_VERSION,
    INFER_MAX_SIDE_FAST,
    INFER_MAX_SIDE_OOM_RETRY,
    INFER_MAX_SIDE_QUALITY,
    apply_mask,
    open_rgb,
    segment_mask,
)
from ghate_editor.model_service import (  # noqa: E402
    detect_device,
    release_memory,
    reset_session,
    warmup,
)
from ghate_editor.processing.composition import compose_white_square  # noqa: E402
from ghate_editor.processing.studio_pipeline import build_studio_rgba  # noqa: E402

IMG_EXT = {".heic", ".heif", ".jpg", ".jpeg", ".png", ".webp"}
ENGINES = ("current", "withoutbg", "birefnet")
CASES_TSV = ROOT / "scripts" / "ab_extraction_cases.tsv"
WORKER = ROOT / "scripts" / "_withoutbg_worker.py"
WITHOUTBG_PY = ROOT / ".venv-withoutbg" / "Scripts" / "python.exe"


def _rss_mb() -> float | None:
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ok = ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        )
        if not ok:
            return None
        return float(counters.PeakWorkingSetSize) / (1024 * 1024)
    except Exception:
        return None


def _vram_mb() -> float | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        ).strip()
        if not out:
            return None
        return float(out.splitlines()[0].split(",")[0].strip())
    except Exception:
        return None


class MemSampler:
    def __init__(self) -> None:
        self.peak_rss = 0.0
        self.peak_vram = 0.0
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def start(self) -> None:
        rss = _rss_mb()
        vram = _vram_mb()
        self.peak_rss = float(rss or 0.0)
        self.peak_vram = float(vram or 0.0)
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def _loop(self) -> None:
        while not self._stop.wait(0.4):
            rss = _rss_mb()
            vram = _vram_mb()
            if rss is not None:
                self.peak_rss = max(self.peak_rss, rss)
            if vram is not None:
                self.peak_vram = max(self.peak_vram, vram)

    def snapshot(self) -> dict[str, float | None]:
        rss = _rss_mb()
        vram = _vram_mb()
        if rss is not None:
            self.peak_rss = max(self.peak_rss, rss)
        if vram is not None:
            self.peak_vram = max(self.peak_vram, vram)
        return {
            "peak_ram_mb": round(self.peak_rss, 1) if self.peak_rss else None,
            "peak_vram_mb": round(self.peak_vram, 1) if self.peak_vram else None,
        }

    def stop(self) -> dict[str, float | None]:
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=2.0)
        return self.snapshot()


def _load_cases(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        rows.append(
            {
                "category": parts[0].strip(),
                "stem": parts[1].strip(),
                "notes": parts[2].strip() if len(parts) > 2 else "",
            }
        )
    return rows


def _index_raw(raw_dir: Path) -> dict[str, Path]:
    by_stem: dict[str, Path] = {}
    for p in raw_dir.iterdir():
        if not p.is_file() or p.suffix.lower() not in IMG_EXT:
            continue
        name = p.stem
        by_stem[name] = p
        # Date-prefixed studio names: ..._IMG_4048
        if "_IMG_" in name.upper():
            key = "IMG_" + name.upper().rsplit("_IMG_", 1)[-1]
            by_stem[key] = p
            by_stem[key.upper()] = p
            by_stem[name.upper().rsplit("_IMG_", 1)[-1]] = p
    return by_stem


def _resolve(case: dict[str, str], index: dict[str, Path]) -> Path | None:
    stem = case["stem"]
    for key in (stem, stem.upper(), stem.replace("IMG_", ""), f"IMG_{stem}"):
        hit = index.get(key) or index.get(key.upper())
        if hit is not None:
            return hit
    return None


def _alpha_stats(rgba: Image.Image) -> dict[str, float]:
    alpha = rgba.split()[-1]
    arr = list(alpha.getdata())
    n = max(1, len(arr))
    return {
        "alpha_mean": round(sum(arr) / n / 255.0, 4),
        "fg_ratio": round(sum(1 for v in arr if v > 8) / n, 4),
    }


def _rgb_mae(orig: Image.Image, rgba: Image.Image) -> float | None:
    try:
        import numpy as np

        o = np.asarray(orig.convert("RGB"), dtype=np.int16)
        r = np.asarray(rgba.convert("RGBA"))
        a = r[:, :, 3]
        m = a >= 200
        if int(m.sum()) < 64:
            return None
        diff = np.abs(o[m].astype(np.int16) - r[:, :, :3][m].astype(np.int16))
        return round(float(diff.mean()), 3)
    except Exception:
        return None


def _save_rgba_white(
    rgba: Image.Image,
    dest_dir: Path,
    stem: str,
    *,
    canvas: int,
    profile: Any | None = None,
) -> tuple[Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    p_rgba = dest_dir / f"{stem}_rgba.png"
    p_white = dest_dir / f"{stem}_white.png"
    rgba.save(p_rgba, "PNG")
    white, _ = compose_white_square(
        rgba, size=canvas, with_shadow=False, profile=profile
    )
    white.save(p_white, "PNG")
    return p_rgba, p_white


def _side_by_side(
    paths: dict[str, Path | None],
    dest: Path,
    *,
    labels: dict[str, str],
    order: tuple[str, ...],
    height: int = 720,
) -> None:
    panels: list[tuple[str, Image.Image]] = []
    for key in order:
        p = paths.get(key)
        if p is not None and p.is_file():
            im = Image.open(p).convert("RGB")
        else:
            im = Image.new("RGB", (height, height), (230, 230, 230))
        scale = height / max(1, im.height)
        im = im.resize(
            (max(1, int(im.width * scale)), height), Image.Resampling.LANCZOS
        )
        panels.append((labels.get(key, key), im))
    gap, header = 12, 36
    width = gap + sum(im.width + gap for _, im in panels)
    canvas = Image.new("RGB", (width, height + header + gap), (245, 245, 245))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    x = gap
    for label, im in panels:
        canvas.paste(im, (x, header))
        draw.text((x + 6, 8), label, fill=(20, 20, 20), font=font)
        x += im.width + gap
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, "JPEG", quality=90)


def _empty_engine() -> dict[str, Any]:
    return {
        "ok": False,
        "elapsed_sec": None,
        "error": None,
        "alpha_mean": None,
        "fg_ratio": None,
        "rgb_mae": None,
        "infer_wh": None,
        "model": None,
        "max_side": None,
        "peak_ram_mb": None,
        "peak_vram_mb": None,
    }


def _run_current(
    working: Image.Image, sampler: MemSampler
) -> tuple[Image.Image | None, Any, dict[str, Any]]:
    rec = _empty_engine()
    rec["model"] = FREE_MODEL_FAST
    rec["max_side"] = INFER_MAX_SIDE_FAST
    t0 = time.perf_counter()
    try:
        mask, iw, ih = segment_mask(
            working,
            max_side=INFER_MAX_SIDE_FAST,
            model_name=FREE_MODEL_FAST,
        )
        rec["infer_wh"] = [iw, ih]
        rgba, profile, report, _ = build_studio_rgba(
            working,
            mask,
            model_name=FREE_MODEL_FAST,
            skip_color=True,
        )
        rec.update(_alpha_stats(rgba))
        rec["rgb_mae"] = _rgb_mae(working, rgba)
        rec["ok"] = True
        rec["matting"] = (report.matting or {}).get("used")
        rec["elapsed_sec"] = round(time.perf_counter() - t0, 3)
        rec.update(sampler.snapshot())
        return rgba, profile, rec
    except Exception as exc:  # noqa: BLE001
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["elapsed_sec"] = round(time.perf_counter() - t0, 3)
        rec.update(sampler.snapshot())
        return None, None, rec


def _run_birefnet(
    working: Image.Image, sampler: MemSampler
) -> tuple[Image.Image | None, dict[str, Any]]:
    rec = _empty_engine()
    rec["model"] = FREE_MODEL_QUALITY
    rec["max_side"] = INFER_MAX_SIDE_QUALITY
    t0 = time.perf_counter()
    last_err: Exception | None = None
    for side in (INFER_MAX_SIDE_QUALITY, INFER_MAX_SIDE_OOM_RETRY):
        try:
            mask, iw, ih = segment_mask(
                working,
                max_side=side,
                model_name=FREE_MODEL_QUALITY,
            )
            rec["infer_wh"] = [iw, ih]
            rec["max_side"] = side
            rgba = apply_mask(working, mask)
            rec.update(_alpha_stats(rgba))
            rec["rgb_mae"] = _rgb_mae(working, rgba)
            rec["ok"] = True
            rec["elapsed_sec"] = round(time.perf_counter() - t0, 3)
            rec.update(sampler.snapshot())
            return rgba, rec
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            release_memory(empty_cuda_cache=True)
            rec["error"] = f"{type(exc).__name__}: {exc}"
            if "out of memory" not in str(exc).lower() and "oom" not in str(exc).lower():
                break
    rec["elapsed_sec"] = round(time.perf_counter() - t0, 3)
    rec.update(sampler.snapshot())
    if last_err is not None and rec["error"] is None:
        rec["error"] = f"{type(last_err).__name__}: {last_err}"
    return None, rec


def _csv_fields() -> list[str]:
    fields = [
        "file",
        "stem",
        "category",
        "notes",
        "width",
        "height",
    ]
    for eng in ENGINES:
        fields.extend(
            [
                f"{eng}_ok",
                f"{eng}_sec",
                f"{eng}_error",
                f"{eng}_alpha_mean",
                f"{eng}_fg_ratio",
                f"{eng}_rgb_mae",
                f"{eng}_model",
                f"{eng}_max_side",
                f"{eng}_peak_ram_mb",
                f"{eng}_peak_vram_mb",
            ]
        )
    fields.extend(
        [
            "current_model_load_sec",
            "birefnet_model_load_sec",
            "withoutbg_model_load_sec",
            "withoutbg_model_id",
            "withoutbg_canvas_size",
        ]
    )
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description="A/B extraction: current vs withoutBG vs BiRefNet")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(os.environ.get("GHATE_RAW_DIR", r"E:\ghateh iran\aks kham")),
    )
    parser.add_argument("--out", type=Path, default=ROOT / "tests" / "ab_extraction")
    parser.add_argument("--cases", type=Path, default=CASES_TSV)
    parser.add_argument("--limit", type=int, default=17)
    parser.add_argument("--canvas", type=int, default=2000)
    parser.add_argument("--skip-withoutbg", action="store_true")
    parser.add_argument("--skip-birefnet", action="store_true")
    parser.add_argument(
        "--withoutbg-python",
        type=Path,
        default=WITHOUTBG_PY,
        help="Interpreter for isolated withoutBG venv",
    )
    args = parser.parse_args()

    if not args.raw_dir.is_dir():
        print(f"RAW dir missing: {args.raw_dir}")
        return 2

    compact_cases = _load_cases(args.cases)
    index = _index_raw(args.raw_dir)
    selected: list[dict[str, Any]] = []
    for case in compact_cases:
        src = _resolve(case, index)
        if src is None:
            print(f"skip missing {case['stem']}", flush=True)
            continue
        selected.append({**case, "src": src})
        if len(selected) >= max(1, args.limit):
            break
    if not selected:
        print("No test images resolved.")
        return 2

    out = args.out
    working_dir = out / "_working"
    for name in ("current", "withoutbg", "birefnet", "comparisons", "_working"):
        (out / name).mkdir(parents=True, exist_ok=True)

    device = detect_device()
    print(
        f"pipeline={FREE_PIPELINE_VERSION} n={len(selected)} device={device.get('device')} "
        f"gpu={device.get('gpu_name')} raw={args.raw_dir}",
        flush=True,
    )

    rows: list[dict[str, Any]] = []
    for case in selected:
        src: Path = case["src"]
        print(f"decode {src.name}", flush=True)
        working = open_rgb(src)
        wp = working_dir / f"{case['stem']}.png"
        working.save(wp, "PNG")
        rows.append(
            {
                "file": src.name,
                "stem": case["stem"],
                "category": case["category"],
                "notes": case.get("notes") or "",
                "src": str(src),
                "working": str(wp),
                "width": working.width,
                "height": working.height,
                "current": _empty_engine(),
                "withoutbg": _empty_engine(),
                "birefnet": _empty_engine(),
            }
        )
        working.close()

    loads = {
        "current": None,
        "birefnet": None,
        "withoutbg": None,
    }
    mem_current: dict[str, float | None] = {}
    mem_birefnet: dict[str, float | None] = {}

    # ----- A) current pipeline (u2net fast + studio fidelity, original RGB) -----
    sampler = MemSampler()
    sampler.start()
    t_load = time.perf_counter()
    try:
        warmup(FREE_MODEL_FAST)
        loads["current"] = round(time.perf_counter() - t_load, 3)
        print(f"loaded {FREE_MODEL_FAST} in {loads['current']}s", flush=True)
        for i, row in enumerate(rows, 1):
            print(f"[current {i}/{len(rows)}] {row['stem']}", flush=True)
            working = Image.open(row["working"]).convert("RGB")
            rgba, profile, rec = _run_current(working, sampler)
            row["current"] = rec
            if rgba is not None:
                _save_rgba_white(
                    rgba, out / "current", row["stem"], canvas=args.canvas, profile=profile
                )
            try:
                working.close()
                if rgba is not None:
                    rgba.close()
            except Exception:
                pass
            print(
                f"  ok={rec['ok']} {rec['elapsed_sec']}s fg={rec.get('fg_ratio')} {rec.get('error') or ''}",
                flush=True,
            )
    except Exception as exc:  # noqa: BLE001
        err = f"{type(exc).__name__}: {exc}"
        print(f"current engine failed: {err}", flush=True)
        for row in rows:
            if not row["current"].get("ok"):
                row["current"]["error"] = err
    finally:
        mem_current = sampler.stop()

    # ----- C) BiRefNet quality path (original RGB + mask, no extra enhance) -----
    if not args.skip_birefnet:
        reset_session()
        release_memory(empty_cuda_cache=True)
        sampler = MemSampler()
        sampler.start()
        t_load = time.perf_counter()
        try:
            warmup(FREE_MODEL_QUALITY)
            loads["birefnet"] = round(time.perf_counter() - t_load, 3)
            print(f"loaded {FREE_MODEL_QUALITY} in {loads['birefnet']}s", flush=True)
            for i, row in enumerate(rows, 1):
                print(f"[birefnet {i}/{len(rows)}] {row['stem']}", flush=True)
                working = Image.open(row["working"]).convert("RGB")
                rgba, rec = _run_birefnet(working, sampler)
                row["birefnet"] = rec
                if rgba is not None:
                    _save_rgba_white(
                        rgba, out / "birefnet", row["stem"], canvas=args.canvas
                    )
                try:
                    working.close()
                    if rgba is not None:
                        rgba.close()
                except Exception:
                    pass
                print(
                    f"  ok={rec['ok']} {rec['elapsed_sec']}s fg={rec.get('fg_ratio')} {rec.get('error') or ''}",
                    flush=True,
                )
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            print(f"birefnet engine failed: {err}", flush=True)
            for row in rows:
                if not row["birefnet"].get("ok"):
                    row["birefnet"]["error"] = err
        finally:
            mem_birefnet = sampler.stop()
            reset_session()
            release_memory(empty_cuda_cache=True)

    # ----- B) withoutBG open weights (isolated venv, model kept alive in worker) -----
    wbg_report: dict[str, Any] = {}
    if not args.skip_withoutbg:
        wpy = Path(args.withoutbg_python)
        if not wpy.is_file():
            print(
                f"withoutBG venv missing ({wpy}). Install:\n"
                "  python -m venv .venv-withoutbg\n"
                "  .venv-withoutbg\\Scripts\\pip install withoutbg pillow",
                flush=True,
            )
            for row in rows:
                row["withoutbg"]["error"] = f"missing_interpreter:{wpy}"
        else:
            job_path = out / "_withoutbg_job.json"
            wrep_path = out / "_withoutbg_worker.json"
            job = {
                "report": str(wrep_path),
                "images": [
                    {
                        "stem": row["stem"],
                        "working": row["working"],
                        "out_rgba": str(out / "withoutbg" / f"{row['stem']}_rgba.png"),
                    }
                    for row in rows
                ],
            }
            job_path.write_text(json.dumps(job, indent=2), encoding="utf-8")
            print(f"withoutBG worker {wpy} n={len(rows)}", flush=True)
            proc = subprocess.run(
                [str(wpy), str(WORKER), "--job", str(job_path)],
                cwd=str(ROOT),
            )
            if wrep_path.is_file():
                wbg_report = json.loads(wrep_path.read_text(encoding="utf-8"))
            else:
                wbg_report = {
                    "load_ok": False,
                    "load_error": f"worker_exit_{proc.returncode}",
                    "rows": [],
                }
            loads["withoutbg"] = wbg_report.get("model_load_sec")
            by_stem = {r["stem"]: r for r in (wbg_report.get("rows") or [])}
            for row in rows:
                wr = by_stem.get(row["stem"]) or {}
                rec = row["withoutbg"]
                rec["ok"] = bool(wr.get("ok"))
                rec["elapsed_sec"] = wr.get("elapsed_sec")
                rec["error"] = wr.get("error")
                rec["alpha_mean"] = wr.get("alpha_mean")
                rec["fg_ratio"] = wr.get("fg_ratio")
                rec["model"] = wbg_report.get("model_id") or "withoutbg-open-weights"
                rec["max_side"] = wbg_report.get("canvas_size")
                rec["peak_ram_mb"] = wbg_report.get("peak_ram_mb")
                rec["peak_vram_mb"] = wbg_report.get("peak_vram_mb")
                p_rgba = out / "withoutbg" / f"{row['stem']}_rgba.png"
                if rec["ok"] and p_rgba.is_file():
                    rgba = Image.open(p_rgba).convert("RGBA")
                    working = Image.open(row["working"]).convert("RGB")
                    rec["rgb_mae"] = _rgb_mae(working, rgba)
                    _save_rgba_white(
                        rgba, out / "withoutbg", row["stem"], canvas=args.canvas
                    )
                    try:
                        rgba.close()
                        working.close()
                    except Exception:
                        pass
            if not wbg_report.get("load_ok", True):
                print(f"withoutBG load error: {wbg_report.get('load_error')}", flush=True)

    # Comparisons + CSV
    csv_path = out / "report.csv"
    json_path = out / "report.json"
    fields = _csv_fields()
    csv_rows: list[dict[str, Any]] = []
    for row in rows:
        _side_by_side(
            {
                "original": Path(row["working"]),
                "current": out / "current" / f"{row['stem']}_white.png",
                "withoutbg": out / "withoutbg" / f"{row['stem']}_white.png",
                "birefnet": out / "birefnet" / f"{row['stem']}_white.png",
            },
            out / "comparisons" / f"{row['stem']}.jpg",
            labels={
                "original": "ORIGINAL",
                "current": "A CURRENT",
                "withoutbg": "B withoutBG",
                "birefnet": "C BiRefNet",
            },
            order=("original", "current", "withoutbg", "birefnet"),
        )
        flat: dict[str, Any] = {
            "file": row["file"],
            "stem": row["stem"],
            "category": row["category"],
            "notes": row["notes"],
            "width": row["width"],
            "height": row["height"],
            "current_model_load_sec": loads["current"],
            "birefnet_model_load_sec": loads["birefnet"],
            "withoutbg_model_load_sec": loads["withoutbg"],
            "withoutbg_model_id": wbg_report.get("model_id")
            or "withoutbg/withoutbg-openweights-onnx",
            "withoutbg_canvas_size": wbg_report.get("canvas_size"),
        }
        for eng in ENGINES:
            rec = row[eng]
            if rec.get("peak_ram_mb") is None and eng == "current":
                rec["peak_ram_mb"] = mem_current.get("peak_ram_mb")
                rec["peak_vram_mb"] = mem_current.get("peak_vram_mb")
            if rec.get("peak_ram_mb") is None and eng == "birefnet":
                rec["peak_ram_mb"] = mem_birefnet.get("peak_ram_mb")
                rec["peak_vram_mb"] = mem_birefnet.get("peak_vram_mb")
            flat[f"{eng}_ok"] = rec.get("ok")
            flat[f"{eng}_sec"] = rec.get("elapsed_sec")
            flat[f"{eng}_error"] = rec.get("error")
            flat[f"{eng}_alpha_mean"] = rec.get("alpha_mean")
            flat[f"{eng}_fg_ratio"] = rec.get("fg_ratio")
            flat[f"{eng}_rgb_mae"] = rec.get("rgb_mae")
            flat[f"{eng}_model"] = rec.get("model")
            flat[f"{eng}_max_side"] = rec.get("max_side")
            flat[f"{eng}_peak_ram_mb"] = rec.get("peak_ram_mb")
            flat[f"{eng}_peak_vram_mb"] = rec.get("peak_vram_mb")
        csv_rows.append(flat)

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows)

    def _mean_sec(eng: str) -> float | None:
        vals = [
            r[eng]["elapsed_sec"]
            for r in rows
            if r[eng].get("ok") and r[eng].get("elapsed_sec") is not None
        ]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 3)

    summary = {
        "pipeline": FREE_PIPELINE_VERSION,
        "n": len(rows),
        "raw_dir": str(args.raw_dir),
        "out": str(out),
        "device": device,
        "engines": {
            "current": {
                "description": "u2net FAST + current studio fidelity (original RGB, no enhance, no shadow)",
                "model": FREE_MODEL_FAST,
                "max_side": INFER_MAX_SIDE_FAST,
                "model_load_sec": loads["current"],
                "mean_sec": _mean_sec("current"),
                "peak_ram_mb": mem_current.get("peak_ram_mb"),
                "peak_vram_mb": mem_current.get("peak_vram_mb"),
                "ok": sum(1 for r in rows if r["current"].get("ok")),
            },
            "withoutbg": {
                "description": "withoutBG local Open Weights, alpha only on original RGB",
                "package": wbg_report.get("package"),
                "model_id": wbg_report.get("model_id"),
                "model_path": wbg_report.get("model_path"),
                "canvas_size": wbg_report.get("canvas_size"),
                "onnx_providers": wbg_report.get("onnx_providers"),
                "model_load_sec": loads["withoutbg"],
                "mean_sec": _mean_sec("withoutbg"),
                "peak_ram_mb": wbg_report.get("peak_ram_mb"),
                "peak_vram_mb": wbg_report.get("peak_vram_mb"),
                "ok": sum(1 for r in rows if r["withoutbg"].get("ok")),
                "load_error": wbg_report.get("load_error"),
            },
            "birefnet": {
                "description": "birefnet-general QUALITY mask + original RGB (no studio matting)",
                "model": FREE_MODEL_QUALITY,
                "max_side": INFER_MAX_SIDE_QUALITY,
                "model_load_sec": loads["birefnet"],
                "mean_sec": _mean_sec("birefnet"),
                "peak_ram_mb": mem_birefnet.get("peak_ram_mb"),
                "peak_vram_mb": mem_birefnet.get("peak_vram_mb"),
                "ok": sum(1 for r in rows if r["birefnet"].get("ok")),
            },
        },
        "note": (
            "Visual review is the primary criterion. CSV times/RAM are measurements only. "
            "withoutBG is NOT wired into production routing."
        ),
        "rows": rows,
    }
    json_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "rows"}, indent=2, default=str))
    print(f"wrote {csv_path}")
    print(f"wrote {json_path}")
    print(f"comparisons: {out / 'comparisons'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
