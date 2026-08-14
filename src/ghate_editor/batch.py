"""Batch worker: free local pipeline and/or fal Kontext Pro."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import Counter, deque
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from .export import download_url, to_square_white_jpg
from .fal_kontext import edit_image_file, first_image_url
from .free_pipeline import (
    APPROVED_DIR_NAME,
    DECODE_QUEUE_SIZE,
    FREE_MODEL_FAST,
    FREE_MODEL_QUALITY,
    FREE_PIPELINE_VERSION,
    REVIEW_DIR_NAME,
    analyze_scene,
    open_rgb,
    process_free_file,
    process_free_job,
)
from .prompt import PROMPT_VERSION
from .review_io import (
    approved_dir,
    ensure_output_layout,
    load_existing_output_ids,
    load_existing_review_ids,
    make_stable_id,
    normalize_source_path,
    review_dir,
    review_edited_dir,
    review_manifest_path,
    review_original_dir,
)

IMAGE_EXTS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
}
Engine = Literal["free", "pro"]
FreeMode = Literal["fast", "adaptive", "quality"]


@dataclass
class BatchConfig:
    input_dir: Path
    output_dir: Path
    size: int = 2000
    concurrency: int = 1
    max_retries: int = 2
    skip_existing: bool = True
    seed: int | None = None
    engine: Engine = "free"
    with_shadow: bool = True
    free_quality: bool = False  # legacy → maps to free_mode quality
    free_mode: FreeMode = "adaptive"  # recommended default
    # Process pool: only for CPU free path (UI). GPU uses in-process singleton.
    free_use_process: bool | None = None  # None = auto


@dataclass
class BatchState:
    stop_event: threading.Event = field(default_factory=threading.Event)
    processed: int = 0
    succeeded: int = 0  # approved
    reviewed: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0
    log_lines: list[str] = field(default_factory=list)
    _cache_lock: threading.Lock = field(default_factory=threading.Lock)
    started_at: float = 0.0
    edit_seconds: deque[float] = field(default_factory=lambda: deque(maxlen=40))
    last_item_started: float = 0.0
    executor: object | None = None
    failures: list[tuple[str, str]] = field(default_factory=list)
    reviews: list[tuple[str, str]] = field(default_factory=list)
    # Rolling stage timing for batch-end averages (PERF)
    stage_sums: dict[str, float] = field(default_factory=dict)
    stage_count: int = 0
    # Production path metrics
    fast_ok: int = 0
    fallback_attempts: int = 0
    fallback_success: int = 0  # approved after fallback
    review_after_fallback: int = 0
    known_review_ids: set[str] = field(default_factory=set)
    # Reason breakdowns (visible regressions)
    failed_reason_counts: Counter = field(default_factory=Counter)
    review_reason_counts: Counter = field(default_factory=Counter)


LogFn = Callable[[str], None]
ProgressFn = Callable[[float, str, dict], None]


def format_duration(seconds: float) -> str:
    if seconds < 0 or seconds != seconds:
        seconds = 0.0
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_timing_stats(state: BatchState) -> dict:
    now = time.monotonic()
    elapsed = max(0.0, now - state.started_at) if state.started_at else 0.0
    done = state.processed
    left = max(0, state.total - done)
    edited = state.succeeded + state.reviewed + state.failed

    if state.edit_seconds:
        avg_edit = sum(state.edit_seconds) / len(state.edit_seconds)
        eta = left * avg_edit
        sec_per_img = avg_edit
        imgs_per_min = 60.0 / avg_edit if avg_edit > 0 else 0.0
    elif edited > 0 and elapsed > 0:
        sec_per_img = elapsed / edited
        eta = left * sec_per_img
        imgs_per_min = edited / elapsed * 60.0
    elif done > 0 and elapsed > 0:
        sec_per_img = elapsed / done
        eta = left * sec_per_img
        imgs_per_min = done / elapsed * 60.0
    else:
        sec_per_img = 0.0
        eta = 0.0
        imgs_per_min = 0.0

    return {
        "elapsed_sec": elapsed,
        "eta_sec": eta,
        "elapsed": format_duration(elapsed),
        "eta": format_duration(eta) if done > 0 else "--:--",
        "sec_per_img": sec_per_img,
        "imgs_per_min": imgs_per_min,
        "processed": done,
        "total": state.total,
        "succeeded": state.succeeded,
        "approved": state.succeeded,
        "reviewed": state.reviewed,
        "failed": state.failed,
        "skipped": state.skipped,
        "left": left,
        "fast_ok": state.fast_ok,
        "fallback_attempts": state.fallback_attempts,
        "fallback_success": state.fallback_success,
        "review_after_fallback": state.review_after_fallback,
    }


def pipeline_tag(engine: Engine, free_quality: bool = False, free_mode: str | None = None) -> str:
    if engine == "free":
        mode = free_mode or ("quality" if free_quality else "adaptive")
        model = FREE_MODEL_QUALITY if mode == "quality" else FREE_MODEL_FAST
        return f"free:{FREE_PIPELINE_VERSION}:{mode}:{model}"
    return f"pro:{PROMPT_VERSION}"


def file_fingerprint(
    path: Path,
    engine: Engine,
    free_quality: bool = False,
    free_mode: str | None = None,
) -> str:
    h = hashlib.sha256()
    stat = path.stat()
    h.update(
        f"{stat.st_size}:{stat.st_mtime_ns}:{pipeline_tag(engine, free_quality, free_mode)}".encode()
    )
    with path.open("rb") as f:
        h.update(f.read(65536))
    return h.hexdigest()[:16]


def force_stop(state: BatchState) -> None:
    state.stop_event.set()
    ex = state.executor
    if ex is None:
        return
    try:
        ex.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        try:
            ex.shutdown(wait=False)
        except Exception:
            pass
    procs = getattr(ex, "_processes", None) or {}
    for proc in list(procs.values()):
        try:
            proc.kill()
        except Exception:
            try:
                proc.terminate()
            except Exception:
                pass
    state.executor = None


def list_images(folder: Path, *, recursive: bool = True) -> list[Path]:
    """Scan for images; never descend into a Review output folder."""
    out: list[Path] = []
    if recursive:
        for root, dirs, files in os.walk(folder):
            dirs[:] = [
                d
                for d in dirs
                if d.lower()
                not in {
                    REVIEW_DIR_NAME.lower(),
                    APPROVED_DIR_NAME.lower(),
                    "edited",
                    "original",
                }
            ]
            for name in files:
                dot = name.rfind(".")
                if dot < 0:
                    continue
                if name[dot:].lower() in IMAGE_EXTS:
                    out.append(Path(root) / name)
    else:
        with os.scandir(folder) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                name = entry.name
                dot = name.rfind(".")
                if dot < 0:
                    continue
                if name[dot:].lower() in IMAGE_EXTS:
                    out.append(Path(entry.path))
    out.sort(key=lambda p: str(p).lower())
    return out


def _cache_path(output_dir: Path) -> Path:
    return output_dir / ".ghate_cache.json"


def _failures_path(output_dir: Path) -> Path:
    return output_dir / "failures.log"


def scan_output_stems(output_dir: Path) -> set[str]:
    """
    One-shot scan of Approved + Review/Edited (+ legacy) → stable ID set.
    Used for O(1) resume skip checks.
    """
    return load_existing_output_ids(output_dir)


def accumulate_stage_timings(state: BatchState, timings: dict | None) -> None:
    if not timings:
        return
    for k, v in timings.items():
        try:
            fv = float(v)
        except (TypeError, ValueError):
            continue
        state.stage_sums[k] = state.stage_sums.get(k, 0.0) + fv
    state.stage_count += 1


def format_stage_averages(state: BatchState) -> str:
    if state.stage_count <= 0:
        return ""
    n = state.stage_count
    keys = (
        "decode",
        "infer",
        "gate",
        "fallback_infer",
        "mask",
        "composite",
        "save",
        "total",
    )
    parts = [f"[PERF AVG] over {n} images"]
    for k in keys:
        if k in state.stage_sums:
            parts.append(f"{k}={state.stage_sums[k] / n:.3f}s")
    gate = state.stage_sums.get("gate", 0.0) / n
    total = state.stage_sums.get("total", 0.0) / n
    if total > 0:
        parts.append(f"gate_share={100.0 * gate / total:.1f}%")
    return " · ".join(parts)


def format_production_metrics(state: BatchState) -> str:
    """Batch-end production report (no claim of 90% without labeled validation)."""
    attempted = state.succeeded + state.reviewed + state.failed
    if attempted <= 0 and state.total <= 0:
        return ""
    base = attempted if attempted > 0 else state.total
    approved_pct = 100.0 * state.succeeded / base if base else 0.0
    review_pct = 100.0 * state.reviewed / base if base else 0.0
    failed_pct = 100.0 * state.failed / base if base else 0.0
    lines = [
        "=== PRODUCTION METRICS ===",
        f"Total images: {state.total}",
        f"Approved: {state.succeeded} ({approved_pct:.1f}%)",
        f"Review: {state.reviewed} ({review_pct:.1f}%)",
        f"Failed: {state.failed} ({failed_pct:.1f}%)",
        f"Skipped (resume): {state.skipped}",
        f"Fast-path success: {state.fast_ok}",
        f"Fallback attempts: {state.fallback_attempts}",
        f"Fallback success (rescued→Approved): {state.fallback_success}",
        f"Review after fallback: {state.review_after_fallback}",
        "Note: Approved% is auto-gate pass rate — not a labeled ecommerce quality claim.",
    ]
    return "\n".join(lines)


# Re-export for app / scripts
def review_log_path(output_dir: Path) -> Path:
    """Legacy name → new manifest path."""
    return review_manifest_path(output_dir)


def load_cache(output_dir: Path) -> dict:
    path = _cache_path(output_dir)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_cache(output_dir: Path, cache: dict) -> None:
    _cache_path(output_dir).write_text(json.dumps(cache), encoding="utf-8")


def append_failure_log(output_dir: Path, filename: str, reason: str) -> None:
    path = _failures_path(output_dir)
    with path.open("a", encoding="utf-8") as f:
        f.write(f"{filename}\t{reason}\n")


def append_review_log(
    output_dir: Path,
    *,
    filename: str,
    source_path: str,
    output_path: str,
    review_reason: str,
    mode: str,
    fallback_used: bool,
    model: str | None,
    foreground_ratio: float | None,
    processing_time: float | None,
    review_id: str | None = None,
    review_original_path: str | None = None,
) -> None:
    """Compatibility wrapper → review_manifest.csv (preferred)."""
    from .review_io import append_review_manifest

    rid = review_id or make_stable_id(source_path)
    metrics = {"model": model or "", "foreground_ratio": foreground_ratio}
    append_review_manifest(
        output_dir,
        review_id=rid,
        original_filename=filename,
        original_source_path=source_path,
        review_original_path=review_original_path or "",
        review_edited_path=output_path,
        review_reason=review_reason.replace(",", ";"),
        processing_mode=mode,
        fallback_used=fallback_used,
        quality_metrics=metrics,
        processing_time=processing_time,
    )


def _cache_entry_fp(entry: object) -> str | None:
    if isinstance(entry, str):
        return entry.split("|", 1)[0]
    if isinstance(entry, dict):
        return str(entry.get("fp") or "") or None
    return None


def _cache_bucket(entry: object) -> str | None:
    if isinstance(entry, dict):
        return str(entry.get("bucket") or "") or None
    if isinstance(entry, str) and "|" in entry:
        parts = entry.split("|")
        return parts[1] if len(parts) > 1 else "approved"
    if isinstance(entry, str):
        return "approved"
    return None


def _set_cache(cache: dict, key: str, fp: str, bucket: str, rel: str) -> None:
    cache[key] = {"fp": fp, "bucket": bucket, "file": rel}


def _already_done(
    cfg: BatchConfig,
    src: Path,
    cache: dict,
    fp: str,
    cache_key: str,
    *,
    done_ids: set[str] | None = None,
    stable_id: str | None = None,
) -> tuple[bool, str]:
    """Skip using cache + optional one-shot stable-ID set (no per-image dir walks)."""
    if not cfg.skip_existing:
        return False, ""
    sid = stable_id or make_stable_id(src)
    entry = cache.get(cache_key)
    if _cache_entry_fp(entry) != fp:
        # Fingerprint mismatch (pipeline changed) → reprocess even if file exists
        return False, ""
    bucket = _cache_bucket(entry) or "approved"
    if isinstance(entry, dict) and entry.get("file"):
        existing = cfg.output_dir / str(entry["file"])
        if existing.is_file():
            return True, f"skip existing ({bucket}) {existing.name}"
    if done_ids is not None:
        if sid in done_ids:
            return True, f"skip existing ({bucket}) {sid}"
        return False, ""
    # Slow fallback
    approved = approved_dir(cfg.output_dir) / f"{sid}.jpg"
    reviewed = review_edited_dir(cfg.output_dir) / f"{sid}.jpg"
    if bucket == "review" and reviewed.is_file():
        return True, f"skip existing (review) {sid}"
    if approved.is_file():
        return True, f"skip existing {sid}"
    if reviewed.is_file():
        return True, f"skip existing (review) {sid}"
    return False, ""


def _resolve_free_mode(cfg: BatchConfig) -> FreeMode:
    if cfg.free_quality:
        return "quality"
    mode = (cfg.free_mode or "adaptive").lower()
    if mode not in ("fast", "adaptive", "quality"):
        return "adaptive"
    return mode  # type: ignore[return-value]


def _free_model(cfg: BatchConfig) -> str:
    mode = _resolve_free_mode(cfg)
    return FREE_MODEL_QUALITY if mode == "quality" else FREE_MODEL_FAST


def _should_use_process(cfg: BatchConfig) -> bool:
    if cfg.free_use_process is not None:
        return bool(cfg.free_use_process)
    try:
        from .model_service import detect_device

        return detect_device().get("device", "cpu") == "cpu"
    except Exception:
        return True


def _rel_to_output(output_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(output_dir.resolve())).replace("\\", "/")
    except Exception:
        return path.name


def process_one_pro(
    src: Path,
    cfg: BatchConfig,
    cache: dict,
    state: BatchState,
    log: LogFn,
) -> tuple[str, str]:
    out_name = src.stem + ".jpg"
    dest = cfg.output_dir / out_name
    fp = file_fingerprint(src, "pro")
    cache_key = f"pro:{src.name}"

    if cfg.skip_existing and dest.exists() and cache.get(cache_key) == fp:
        return "skip", f"skip existing {out_name}"

    last_err: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        if state.stop_event.is_set():
            return "fail", f"stopped {src.name}"
        try:
            log(f"[pro] {src.name} (attempt {attempt})")
            payload = edit_image_file(src, seed=cfg.seed)
            url = first_image_url(payload)
            tmp = cfg.output_dir / f".tmp_{src.stem}.png"
            download_url(url, tmp)
            to_square_white_jpg(tmp, dest, size=cfg.size)
            tmp.unlink(missing_ok=True)
            with state._cache_lock:
                cache[cache_key] = fp
            return "ok", f"[OK] {out_name}"
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            log(f"retry {src.name}: {exc}")
            time.sleep(min(2**attempt, 6))
    return "fail", f"[FAILED] {src.name} reason={last_err}"


def process_one_free_thread(
    src: Path,
    cfg: BatchConfig,
    cache: dict,
    state: BatchState,
    log: LogFn,
    *,
    done_ids: set[str] | None = None,
    working=None,
    scene=None,
) -> tuple[str, str, float, str, dict | None]:
    rid = make_stable_id(src)
    out_name = f"{rid}.jpg"
    dest = approved_dir(cfg.output_dir) / out_name
    mode = _resolve_free_mode(cfg)
    fp = file_fingerprint(src, "free", cfg.free_quality, mode)
    cache_key = f"free:{normalize_source_path(src)}"

    skip, skip_msg = _already_done(
        cfg, src, cache, fp, cache_key, done_ids=done_ids, stable_id=rid
    )
    if skip:
        return "skip", skip_msg, 0.0, "", None

    if state.stop_event.is_set():
        return "fail", f"stopped {src.name}", 0.0, "", None

    model = _free_model(cfg)
    t0 = time.monotonic()
    status_lines: list[str] = []
    result = process_free_file(
        src,
        dest,
        size=cfg.size,
        with_shadow=cfg.with_shadow,
        model_name=model,
        free_mode=mode,
        review_dir=review_dir(cfg.output_dir),
        review_id=rid,
        known_review_ids=state.known_review_ids,
        working=working,
        scene=scene,
        perf_log=None,
        status_log=status_lines,
    )
    edit_sec = time.monotonic() - t0
    status = result.get("status") or "failed"
    msg = "\n".join(status_lines) if status_lines else f"[{status.upper()}] {src.name}"
    timings = result.get("timings") if isinstance(result.get("timings"), dict) else None
    accumulate_stage_timings(state, timings)
    _record_path_metrics(state, result, status)

    if status == "approved":
        out_p = Path(result["path"]) if result.get("path") else dest
        rel = _rel_to_output(cfg.output_dir, out_p)
        with state._cache_lock:
            _set_cache(cache, cache_key, fp, "approved", rel)
        if done_ids is not None:
            done_ids.add(rid)
        return "ok", msg, edit_sec, "", timings

    if status == "review":
        out_p = (
            Path(result["path"])
            if result.get("path")
            else review_edited_dir(cfg.output_dir) / out_name
        )
        rel = _rel_to_output(cfg.output_dir, out_p)
        reasons = result.get("reasons") or ["segmentation_unreliable"]
        with state._cache_lock:
            _set_cache(cache, cache_key, fp, "review", rel)
            state.reviews.append((src.name, ",".join(reasons)))
            state.known_review_ids.add(rid)
        if done_ids is not None:
            done_ids.add(rid)
        return "review", msg, edit_sec, "", timings

    return "fail", msg, edit_sec, "", timings


def _primary_reason(reasons: list | None, fallback: str = "quality_uncertain") -> str:
    if not reasons:
        return fallback
    # Prefer actionable buckets
    priority = (
        "rescue_failed",
        "quality_check_error",
        "catastrophic_structure_loss",
        "fallback_failed_quality_check",
        "decode_failed",
        "inference_oom",
        "no_candidate",
        "fast_inference_failed_no_candidate",
        "final_save_failed",
    )
    rs = [str(r) for r in reasons if r]
    for p in priority:
        if p in rs:
            return p
    return rs[0] if rs else fallback


def _bucket_review_reason(reason: str) -> str:
    r = (reason or "").lower()
    if "rescue_failed" in r or "inference_oom" in r or "inference_runtime" in r:
        return "rescue_failed"
    if "quality_check_error" in r:
        return "quality_check_error"
    if "catastrophic_structure_loss" in r or "product_faded" in r:
        return "quality_bad"
    if "fallback_failed" in r or "uncertain" in r or "weak_mask" in r:
        return "quality_uncertain"
    if "foggy" in r or "fragmented" in r:
        return "quality_uncertain"
    return reason or "quality_uncertain"


def _record_path_metrics(state: BatchState, result: dict, status: str) -> None:
    label = str(result.get("path_label") or "")
    fallback_used = bool(result.get("fallback_used"))
    if status == "approved":
        if label == "FAST" or (label == "QUALITY" and not fallback_used):
            state.fast_ok += 1
        if result.get("fallback_rescued") or (fallback_used and label == "FALLBACK"):
            state.fallback_attempts += 1
            state.fallback_success += 1
        elif fallback_used:
            state.fallback_attempts += 1
    elif status == "review":
        if fallback_used:
            state.fallback_attempts += 1
            state.review_after_fallback += 1
        elif result.get("fast_failed"):
            state.fallback_attempts += 1
            state.review_after_fallback += 1
        primary = _primary_reason(result.get("reasons"), "quality_uncertain")
        state.review_reason_counts[_bucket_review_reason(primary)] += 1
    elif status == "failed":
        primary = result.get("fail_reason") or _primary_reason(
            result.get("reasons"), "no_candidate"
        )
        state.failed_reason_counts[str(primary)] += 1


def run_batch(
    cfg: BatchConfig,
    state: BatchState,
    log: LogFn | None = None,
    on_progress: ProgressFn | None = None,
) -> BatchState:
    def _log(msg: str) -> None:
        state.log_lines.append(msg)
        if log:
            log(msg)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    ensure_output_layout(cfg.output_dir)
    images = list_images(cfg.input_dir)
    state.total = len(images)
    cache = load_cache(cfg.output_dir)
    state.known_review_ids = load_existing_review_ids(cfg.output_dir)
    model = _free_model(cfg) if cfg.engine == "free" else "pro"
    mode = _resolve_free_mode(cfg) if cfg.engine == "free" else "pro"
    state.started_at = time.monotonic()

    heic_n = sum(1 for p in images if p.suffix.lower() in {".heic", ".heif"})
    _log(
        f"batch start: {state.total} images · engine={cfg.engine} · "
        f"mode={mode} · model={model} · "
        f"{pipeline_tag(cfg.engine, cfg.free_quality, mode if cfg.engine == 'free' else None)}"
    )
    _log(f"Approved folder: {approved_dir(cfg.output_dir)}")
    _log(f"Review folder: {review_dir(cfg.output_dir)}")
    _log(f"  Edited:   {review_edited_dir(cfg.output_dir)}")
    _log(f"  Original: {review_original_dir(cfg.output_dir)}")
    _log(f"  Manifest: {review_manifest_path(cfg.output_dir)}")
    if heic_n:
        _log(f"includes {heic_n} HEIC/HEIF (iPhone) files — converting on the fly")

    if state.total == 0:
        _log(
            "no images found (supported: jpg, jpeg, png, webp, bmp, tif, heic, heif)"
        )
        if on_progress:
            on_progress(100.0, "done", build_timing_stats(state))
        return state

    def _finish_one(
        status: str,
        message: str,
        *,
        edit_sec: float | None = None,
        src_name: str | None = None,
        perf: str = "",
    ) -> None:
        state.processed += 1
        if status == "ok":
            state.succeeded += 1
            if edit_sec is not None and edit_sec > 0:
                state.edit_seconds.append(edit_sec)
        elif status == "review":
            state.reviewed += 1
            if edit_sec is not None and edit_sec > 0:
                state.edit_seconds.append(edit_sec)
        elif status == "skip":
            state.skipped += 1
        else:
            state.failed += 1
            if edit_sec is not None and edit_sec > 0:
                state.edit_seconds.append(edit_sec)
            if src_name:
                state.failures.append((src_name, message))
                try:
                    append_failure_log(cfg.output_dir, src_name, message)
                except Exception:
                    pass
        _log(message)
        if perf:
            _log(perf)
        if state.processed % 5 == 0 or state.processed >= state.total:
            with state._cache_lock:
                save_cache(cfg.output_dir, cache)
        if on_progress:
            on_progress(
                100.0 * state.processed / state.total,
                message,
                build_timing_stats(state),
            )

    if cfg.engine == "free":
        use_process = _should_use_process(cfg)
        if use_process:
            _run_free_process_pool(cfg, state, images, cache, model, _log, _finish_one)
        else:
            _run_free_sequential(cfg, state, images, cache, model, _log, _finish_one)
    else:
        workers = max(1, min(cfg.concurrency, 4))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for src in images:
                if state.stop_event.is_set():
                    break
                futures[pool.submit(process_one_pro, src, cfg, cache, state, _log)] = src
            for fut in as_completed(futures):
                t0 = time.monotonic()
                status, message = fut.result()
                edit_sec = time.monotonic() - t0
                src = futures[fut]
                _finish_one(
                    status,
                    message,
                    edit_sec=edit_sec if status != "skip" else None,
                    src_name=src.name if status == "fail" else None,
                )

    save_cache(cfg.output_dir, cache)
    final_stats = build_timing_stats(state)
    processed = max(1, int(state.succeeded) + int(state.reviewed) + int(state.failed))
    pass_pct = 100.0 * float(state.succeeded) / float(processed)
    review_pct = 100.0 * float(state.reviewed) / float(processed)
    fail_pct = 100.0 * float(state.failed) / float(processed)
    _log(
        "Batch completed\n"
        f"TOTAL: {state.total}\n"
        f"APPROVED: {state.succeeded}\n"
        f"REVIEW: {state.reviewed}\n"
        f"FAILED: {state.failed}\n"
        f"SKIPPED: {state.skipped}\n"
        f"PASS %: {pass_pct:.1f}\n"
        f"REVIEW %: {review_pct:.1f}\n"
        f"FAILED %: {fail_pct:.1f}\n"
        f"Elapsed time: {final_stats['elapsed']}\n"
        f"Average seconds/image: {final_stats['sec_per_img']:.2f}"
    )
    # Diagnostic only — never overrides individual QC decisions
    if processed >= 8 and review_pct > 90.0 and pass_pct < 5.0:
        _log(
            "WARNING possible_qc_regression: REVIEW>90% on an ordinary batch "
            f"(PASS={pass_pct:.1f}% REVIEW={review_pct:.1f}% FAILED={fail_pct:.1f}%). "
            "Inspect QC fatal_errors / raw_prior_frac before retuning thresholds."
        )
    if state.failed_reason_counts:
        parts = [
            f"{k}: {v}" for k, v in sorted(state.failed_reason_counts.items(), key=lambda x: (-x[1], x[0]))
        ]
        _log("FAILED breakdown: " + "; ".join(parts))
    if state.review_reason_counts:
        parts = [
            f"{k}: {v}" for k, v in sorted(state.review_reason_counts.items(), key=lambda x: (-x[1], x[0]))
        ]
        _log("REVIEW breakdown: " + "; ".join(parts))
    prod = format_production_metrics(state)
    if prod:
        _log(prod)
    avg = format_stage_averages(state)
    if avg:
        _log(avg)
    if state.reviewed:
        _log(f"Review manifest: {review_manifest_path(cfg.output_dir)}")
        _log(f"Review Edited: {review_edited_dir(cfg.output_dir)}")
        _log(f"Review Original (copies only): {review_original_dir(cfg.output_dir)}")
    if state.failed:
        _log(f"Failure log: {_failures_path(cfg.output_dir)}")
    if on_progress:
        on_progress(100.0, "done", final_stats)
    return state


def _run_free_sequential(cfg, state, images, cache, model, _log, _finish_one) -> None:
    """Streaming: bounded decode prefetch overlaps with one GPU infer worker."""
    from queue import Empty, Queue

    from .model_service import warmup

    mode = _resolve_free_mode(cfg)
    _log(f"Free engine: mode={mode} · streaming decode+infer (1 GPU worker)...")
    info = warmup(FREE_MODEL_FAST if mode != "quality" else FREE_MODEL_QUALITY)
    _log(
        f"CUDA available: {info.get('cuda_available')} · "
        f"Device: {info.get('device')} · "
        f"GPU: {info.get('gpu_name') or 'n/a'} · "
        f"ORT {info.get('ort_version')} · "
        f"providers={info.get('active_providers') or info.get('providers')}"
    )
    if info.get("warning"):
        _log(info["warning"])
    if mode == "adaptive":
        _log(
            "Adaptive: FAST -> ROI gate -> STRONG rescue if uncertain/bad -> "
            "Approve on high confidence; Review if still poor (shadow excluded from gate)"
        )

    done_ids = scan_output_stems(cfg.output_dir) if cfg.skip_existing else set()
    _log(f"Resume index: {len(done_ids)} existing output ID(s)")

    work: list[tuple[Path, str, str]] = []
    for src in images:
        if state.stop_event.is_set():
            break
        fp = file_fingerprint(src, "free", cfg.free_quality, mode)
        cache_key = f"free:{normalize_source_path(src)}"
        rid = make_stable_id(src)
        skip, skip_msg = _already_done(
            cfg, src, cache, fp, cache_key, done_ids=done_ids, stable_id=rid
        )
        if skip:
            _finish_one("skip", skip_msg)
            continue
        work.append((src, fp, cache_key))

    if not work:
        return

    q: Queue = Queue(maxsize=max(2, DECODE_QUEUE_SIZE))
    sentinel = object()

    def _decoder() -> None:
        for src, fp, cache_key in work:
            if state.stop_event.is_set():
                break
            try:
                t0 = time.perf_counter()
                img = open_rgb(src)
                scene = analyze_scene(img)
                decode_s = time.perf_counter() - t0
                q.put(("ok", src, fp, cache_key, img, scene, decode_s))
            except Exception as exc:  # noqa: BLE001
                q.put(("err", src, fp, cache_key, exc, None, 0.0))
        q.put(sentinel)

    dec_thread = threading.Thread(target=_decoder, daemon=True, name="ghate-decode")
    dec_thread.start()

    while True:
        if state.stop_event.is_set():
            while True:
                try:
                    item = q.get_nowait()
                except Empty:
                    break
                if item is sentinel:
                    break
                if isinstance(item, tuple) and item[0] == "ok" and item[4] is not None:
                    try:
                        item[4].close()
                    except Exception:
                        pass
            break

        item = q.get()
        if item is sentinel:
            break
        kind = item[0]
        src = item[1]
        if kind == "err":
            reason = str(item[4] or "decode_failed")
            # Prefer precise bucket
            low = reason.lower()
            if "decode" in low or "cannot identify" in low:
                bucket = "decode_failed"
            elif "unsupported" in low:
                bucket = "unsupported_format"
            else:
                bucket = "decode_failed"
            state.failed_reason_counts[bucket] += 1
            _finish_one(
                "fail",
                f"[FAILED] {src.name}\nReason: {bucket}",
                src_name=src.name,
            )
            continue

        working, scene, decode_s = item[4], item[5], item[6]
        try:
            status, message, edit_sec, _perf, timings = process_one_free_thread(
                src,
                cfg,
                cache,
                state,
                _log,
                done_ids=done_ids,
                working=working,
                scene=scene,
            )
            if timings is not None and decode_s:
                state.stage_sums["decode"] = state.stage_sums.get("decode", 0.0) + float(
                    decode_s
                )
            _finish_one(
                status,
                message,
                edit_sec=edit_sec if status != "skip" else None,
                src_name=src.name if status == "fail" else None,
                perf="",
            )
        finally:
            if working is not None:
                try:
                    working.close()
                except Exception:
                    pass

    dec_thread.join(timeout=5.0)


def _run_free_process_pool(cfg, state, images, cache, model, _log, _finish_one) -> None:
    _log("Free engine: child process (CPU path — UI stays responsive)...")
    try:
        from .model_service import detect_device

        info = detect_device()
        if info.get("warning"):
            _log(info["warning"])
        _log(
            f"Device probe: {info.get('device')} · "
            f"GPU: {info.get('gpu_name') or 'n/a'}"
        )
    except Exception as exc:  # noqa: BLE001
        _log(f"Device probe failed: {exc}")

    done_ids = scan_output_stems(cfg.output_dir) if cfg.skip_existing else set()
    _log(f"Resume index: {len(done_ids)} existing output ID(s)")

    jobs: deque[dict] = deque()
    mode = _resolve_free_mode(cfg)
    rdir = review_dir(cfg.output_dir)
    for src in images:
        if state.stop_event.is_set():
            break
        rid = make_stable_id(src)
        out_name = f"{rid}.jpg"
        dest = approved_dir(cfg.output_dir) / out_name
        fp = file_fingerprint(src, "free", cfg.free_quality, mode)
        cache_key = f"free:{normalize_source_path(src)}"
        skip, skip_msg = _already_done(
            cfg, src, cache, fp, cache_key, done_ids=done_ids, stable_id=rid
        )
        if skip:
            _finish_one("skip", skip_msg)
            continue
        jobs.append(
            {
                "src": str(src),
                "dest": str(dest),
                "src_name": src.name,
                "out_name": out_name,
                "cache_key": cache_key,
                "fp": fp,
                "size": cfg.size,
                "with_shadow": cfg.with_shadow,
                "model_name": model,
                "free_mode": mode,
                "review_dir": str(rdir),
                "review_id": rid,
            }
        )

    with ProcessPoolExecutor(max_workers=1) as pool:
        state.executor = pool
        while jobs and not state.stop_event.is_set():
            payload = jobs.popleft()
            fut = pool.submit(process_free_job, payload)
            try:
                result = fut.result()
            except Exception as exc:  # noqa: BLE001
                if state.stop_event.is_set():
                    _log("stopped by user")
                    break
                _finish_one(
                    "fail",
                    f"[FAILED] {payload['src_name']}\nReason: {exc}",
                    src_name=payload["src_name"],
                )
                continue
            if state.stop_event.is_set():
                _log("stopped by user")
                break
            edit_sec = float(result.get("edit_sec") or 0.0)
            status_txt = result.get("status_log") or ""
            st = result.get("status") or ("approved" if result.get("ok") else "failed")
            accumulate_stage_timings(state, result.get("timings"))
            _record_path_metrics(state, result, st if st != "approved" else "approved")
            rid = payload.get("review_id") or make_stable_id(payload["src"])

            if st == "approved":
                out_p = Path(result["path"]) if result.get("path") else Path(payload["dest"])
                rel = _rel_to_output(cfg.output_dir, out_p)
                with state._cache_lock:
                    _set_cache(cache, result["cache_key"], result["fp"], "approved", rel)
                done_ids.add(rid)
                _finish_one(
                    "ok",
                    status_txt or f"[OK] {payload['out_name']}",
                    edit_sec=edit_sec,
                    perf="",
                )
            elif st == "review":
                out_p = (
                    Path(result["path"])
                    if result.get("path")
                    else review_edited_dir(cfg.output_dir) / payload["out_name"]
                )
                rel = _rel_to_output(cfg.output_dir, out_p)
                reasons = result.get("reasons") or ["segmentation_unreliable"]
                with state._cache_lock:
                    _set_cache(cache, result["cache_key"], result["fp"], "review", rel)
                    state.reviews.append((payload["src_name"], ",".join(reasons)))
                    state.known_review_ids.add(rid)
                done_ids.add(rid)
                _finish_one(
                    "review",
                    status_txt or f"[REVIEW] {payload['src_name']}",
                    edit_sec=edit_sec,
                    perf="",
                )
            else:
                _finish_one(
                    "fail",
                    status_txt
                    or f"[FAILED] {payload['src_name']} reason={result.get('error')}",
                    edit_sec=edit_sec,
                    src_name=payload["src_name"],
                    perf="",
                )
        state.executor = None
        if state.stop_event.is_set() and jobs:
            _log(f"stop: {len(jobs)} images not started")
