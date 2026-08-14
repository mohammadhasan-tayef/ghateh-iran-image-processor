"""Singleton rembg/ONNX sessions — load once per model; prefer CUDA, then DirectML."""

from __future__ import annotations

import os
import threading
from typing import Any

for _k, _v in (
    ("OMP_NUM_THREADS", "2"),
    ("MKL_NUM_THREADS", "2"),
    ("OPENBLAS_NUM_THREADS", "2"),
    ("NUMEXPR_NUM_THREADS", "2"),
    ("ORT_NUM_THREADS", "2"),
):
    os.environ.setdefault(_k, _v)

_lock = threading.Lock()
_sessions: dict[str, Any] = {}
_device_info: dict[str, Any] | None = None

# Heavy models — on 4GB VRAM keep at most one heavyweight session resident
_HEAVY_MODELS = frozenset({"birefnet-general", "birefnet-general-lite", "sam"})


def _gpu_name_from_smi() -> str | None:
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader",
            ],
            text=True,
            timeout=5,
        ).strip()
        return out.split("\n")[0].strip() if out else None
    except Exception:
        return None


def _probe_cuda_provider() -> bool:
    try:
        import ctypes
        from pathlib import Path

        import onnxruntime as ort

        if "CUDAExecutionProvider" not in ort.get_available_providers():
            return False
        if hasattr(ort, "preload_dlls"):
            try:
                ort.preload_dlls(cuda=True, cudnn=True, msvc=True)
            except Exception:
                pass
        capi = Path(ort.__file__).resolve().parent / "capi"
        dll = capi / "onnxruntime_providers_cuda.dll"
        if not dll.exists():
            return False
        try:
            ctypes.WinDLL(str(dll))
        except OSError:
            return False
        return True
    except Exception:
        return False


def detect_device() -> dict[str, Any]:
    global _device_info
    if _device_info is not None:
        return _device_info

    info: dict[str, Any] = {
        "cuda_available": False,
        "dml_available": False,
        "device": "cpu",
        "gpu_name": None,
        "providers": ["CPUExecutionProvider"],
        "ort_version": None,
        "warning": None,
        "available_providers": [],
    }
    try:
        import onnxruntime as ort

        info["ort_version"] = ort.__version__
        available = list(ort.get_available_providers())
        info["available_providers"] = available
        cuda_listed = "CUDAExecutionProvider" in available
        dml_listed = "DmlExecutionProvider" in available
        info["dml_available"] = dml_listed
        cuda_works = _probe_cuda_provider() if cuda_listed else False
        info["cuda_available"] = cuda_works
        gpu_name = _gpu_name_from_smi()

        if cuda_works:
            info["device"] = "cuda"
            info["providers"] = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            info["gpu_name"] = gpu_name or "NVIDIA GPU (CUDA)"
        elif dml_listed:
            info["device"] = "dml"
            info["providers"] = ["DmlExecutionProvider", "CPUExecutionProvider"]
            info["gpu_name"] = gpu_name or "GPU (DirectML)"
            if cuda_listed and not cuda_works:
                info["warning"] = (
                    "WARNING: CUDA EP listed but CUDA runtime DLLs failed to load. "
                    "Using DirectML GPU instead."
                )
        else:
            info["device"] = "cpu"
            info["providers"] = ["CPUExecutionProvider"]
            info["warning"] = (
                "WARNING: CUDA/DirectML unavailable. "
                "Processing will be significantly slower on CPU."
            )
    except Exception as exc:  # noqa: BLE001
        info["warning"] = f"WARNING: onnxruntime import failed: {exc}"

    _device_info = info
    return info


def _bind_providers(session: Any, info: dict[str, Any]) -> None:
    try:
        used = list(session.inner_session.get_providers())
        info["active_providers"] = used
        if used and used[0] == "CPUExecutionProvider" and info["device"] != "cpu":
            info["device"] = "cpu"
            info["warning"] = (
                "WARNING: GPU provider requested but session fell back to CPU. "
                "Processing will be significantly slower."
            )
        elif used:
            top = used[0]
            if top == "CUDAExecutionProvider":
                info["device"] = "cuda"
            elif top == "DmlExecutionProvider":
                info["device"] = "dml"
    except Exception:
        pass


def get_session(model_name: str = "u2net"):
    """Return a cached rembg session for model_name (created once)."""
    if model_name in _sessions:
        return _sessions[model_name]

    with _lock:
        if model_name in _sessions:
            return _sessions[model_name]

        import onnxruntime as ort
        from rembg import new_session

        info = detect_device()
        sess_opts = ort.SessionOptions()
        sess_opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_opts.intra_op_num_threads = 2
        sess_opts.inter_op_num_threads = 1
        try:
            sess_opts.enable_mem_pattern = True
        except Exception:
            pass

        # Free VRAM before loading a heavy model on 4GB GPUs
        if model_name in _HEAVY_MODELS:
            for key in list(_sessions.keys()):
                if key != model_name:
                    _sessions.pop(key, None)
            release_memory(empty_cuda_cache=True)
        elif len(_sessions) >= 2:
            # Prefer not holding many light models either
            pass

        try:
            session = new_session(
                model_name,
                sess_opts=sess_opts,
                providers=info["providers"],
            )
        except Exception:
            # OOM while loading — drop other sessions and retry once
            _sessions.clear()
            release_memory(empty_cuda_cache=True)
            session = new_session(
                model_name,
                sess_opts=sess_opts,
                providers=info["providers"],
            )

        _sessions[model_name] = session
        _bind_providers(session, info)
        return session


def warmup(model_name: str = "u2net") -> dict[str, Any]:
    info = detect_device()
    get_session(model_name)
    return {**info, "model": model_name, "loaded": True}


def reset_session() -> None:
    with _lock:
        _sessions.clear()


def release_memory(*, empty_cuda_cache: bool = False) -> None:
    import gc

    gc.collect()
    if empty_cuda_cache:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
