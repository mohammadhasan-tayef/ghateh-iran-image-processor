#!/usr/bin/env python3
"""Isolated withoutBG Open Weights worker (CPU ONNX in .venv-withoutbg).

Never imported by the production app. Load the model once, process a JSON job
of pre-decoded working RGB images, write RGBA PNGs using ORIGINAL RGB + model
alpha only (no enhancement, no shadow, no withoutBG RGB recast).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")


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
        import subprocess

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


class _Sampler:
    def __init__(self) -> None:
        self.peak_rss = 0.0
        self.peak_vram = 0.0
        self._stop = threading.Event()
        self._th: threading.Thread | None = None

    def _loop(self) -> None:
        while not self._stop.wait(0.4):
            rss = _rss_mb()
            vram = _vram_mb()
            if rss is not None:
                self.peak_rss = max(self.peak_rss, rss)
            if vram is not None:
                self.peak_vram = max(self.peak_vram, vram)

    def start(self) -> None:
        rss = _rss_mb()
        vram = _vram_mb()
        self.peak_rss = float(rss or 0.0)
        self.peak_vram = float(vram or 0.0)
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self) -> dict[str, float | None]:
        self._stop.set()
        if self._th is not None:
            self._th.join(timeout=2.0)
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))
    items = job.get("images") or []
    report_path = Path(job["report"])

    from PIL import Image
    from withoutbg import WithoutBG

    sampler = _Sampler()
    sampler.start()
    t_load = time.perf_counter()
    sidecar: dict = {}
    model_path = os.environ.get("WITHOUTBG_MODEL_PATH") or None
    try:
        model = WithoutBG.open_weights()
        model.preload()  # download+ORT load once; do not reload per image
        load_ok = True
        load_error = None
        inner = getattr(model, "model", None)
        if inner is not None:
            sidecar = dict(getattr(inner, "sidecar", None) or {})
            if getattr(inner, "model_path", None):
                model_path = str(inner.model_path)
    except Exception as exc:  # noqa: BLE001
        model = None
        load_ok = False
        load_error = f"{type(exc).__name__}: {exc}"
    load_sec = time.perf_counter() - t_load

    model_id = "withoutbg/withoutbg-openweights-onnx"
    hf_filename = "withoutbg-open-weights.onnx"

    rows: list[dict] = []
    for item in items:
        stem = item["stem"]
        working = Path(item["working"])
        out_rgba = Path(item["out_rgba"])
        rec: dict = {
            "stem": stem,
            "ok": False,
            "elapsed_sec": None,
            "error": None,
            "alpha_mean": None,
            "fg_ratio": None,
            "out_size": None,
        }
        t0 = time.perf_counter()
        try:
            if model is None:
                raise RuntimeError(load_error or "model_load_failed")
            orig = Image.open(working).convert("RGB")
            cut = model.remove_background(orig)
            if not isinstance(cut, Image.Image):
                raise TypeError(f"unexpected result type {type(cut)}")
            cut = cut.convert("RGBA")
            alpha = cut.split()[-1]
            if alpha.size != orig.size:
                alpha = alpha.resize(orig.size, Image.Resampling.LANCZOS)
            rgba = orig.convert("RGBA")
            rgba.putalpha(alpha)
            out_rgba.parent.mkdir(parents=True, exist_ok=True)
            rgba.save(out_rgba, "PNG")
            a = list(alpha.getdata())
            n = max(1, len(a))
            rec["alpha_mean"] = round(sum(a) / n / 255.0, 4)
            rec["fg_ratio"] = round(sum(1 for v in a if v > 8) / n, 4)
            rec["out_size"] = [rgba.width, rgba.height]
            rec["ok"] = True
            try:
                orig.close()
                cut.close()
                rgba.close()
            except Exception:
                pass
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["elapsed_sec"] = round(time.perf_counter() - t0, 3)
        rows.append(rec)
        print(
            f"[withoutbg] {stem} ok={rec['ok']} {rec['elapsed_sec']}s {rec.get('error') or ''}",
            flush=True,
        )

    mem = sampler.stop()
    report = {
        "engine": "withoutbg_open_weights",
        "package": "withoutbg==1.1.1",
        "model_id": model_id,
        "hf_filename": hf_filename,
        "model_path": model_path,
        "canvas_size": sidecar.get("canvas_size"),
        "output_canvas_size": sidecar.get("output_canvas_size")
        or (sidecar.get("output_shape") or [None, None, None, None])[2],
        "sidecar": {
            k: sidecar.get(k)
            for k in (
                "canvas_size",
                "output_canvas_size",
                "input_name",
                "output_name",
                "input_shape",
                "output_shape",
                "model_version",
                "size_mb",
                "sha256",
                "precision",
                "variant",
                "depth_variant",
            )
            if k in sidecar
        },
        "onnx_providers": ["CPUExecutionProvider"],
        "load_ok": load_ok,
        "load_error": load_error,
        "model_load_sec": round(load_sec, 3),
        "python": sys.executable,
        "peak_ram_mb": mem.get("peak_ram_mb"),
        "peak_vram_mb": mem.get("peak_vram_mb"),
        "n": len(rows),
        "rows": rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0 if load_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
