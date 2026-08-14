#!/usr/bin/env python3
"""
Golden QC full-pipeline harness (production path).

Runs the SAME adaptive free pipeline + QC used by the app:
  process_free_file → compute_raw_final_integrity(+spatial verifier) → classify_quality

Place edited finals OR source RAW under:
  tests/qc_golden/good_should_pass/
  tests/qc_golden/bad_should_review/

When a folder entry is a studio JPG, the matching RAW is resolved from
--raw-dir (default: E:\\ghateh iran\\aks kham or $GHATE_RAW_DIR).

Usage:
  python scripts/run_qc_golden.py
  python scripts/run_qc_golden.py --dir tests/qc_golden --raw-dir "E:\\ghateh iran\\aks kham"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.batch import list_images  # noqa: E402
from ghate_editor.free_pipeline import (  # noqa: E402
    FREE_PIPELINE_VERSION,
    process_free_file,
)
from ghate_editor.qc_config import get_qc_config  # noqa: E402

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
RAW_EXT = {".heic", ".heif", ".dng", ".cr2", ".nef", ".arw", ".raf", ".orf", ".rw2"}


def _stem_key(name: str) -> str:
    stem = Path(name).stem
    # Strip content-hash suffix: IMG_4048__7a9ef2 → IMG_4048
    stem = re.sub(r"__[0-9a-f]{4,10}$", "", stem, flags=re.I)
    return stem


def resolve_raw(path: Path, raw_dirs: list[Path]) -> Path | None:
    if path.suffix.lower() in RAW_EXT:
        return path if path.is_file() else None
    key = _stem_key(path.name)
    for d in raw_dirs:
        if not d.is_dir():
            continue
        for ext in sorted(RAW_EXT):
            cand = d / f"{key}{ext}"
            if cand.is_file():
                return cand
            cand2 = d / f"{key}{ext.upper()}"
            if cand2.is_file():
                return cand2
        # Also allow already-decoded JPG sources in raw dir
        for ext in (".jpg", ".jpeg", ".png"):
            cand = d / f"{key}{ext}"
            if cand.is_file():
                return cand
    return None


def _score_one_production(raw_path: Path, work_root: Path, *, free_mode: str = "adaptive") -> dict:
    """Exercise the exact production process_free_file QC path."""
    approved = work_root / "Approved" / f"{raw_path.stem}.jpg"
    approved.parent.mkdir(parents=True, exist_ok=True)
    (work_root / "Review").mkdir(parents=True, exist_ok=True)
    result = process_free_file(
        raw_path,
        approved,
        size=2000,
        with_shadow=False,
        quality=90,
        free_mode=free_mode,  # type: ignore[arg-type]
        review_dir=work_root / "Review",
        package_review=False,
    )
    meta = result.get("meta") or {}
    rf = result.get("raw_final_stats") or meta.get("raw_final_stats") or {}
    diag = result.get("qc_diagnostics") or meta.get("qc_diagnostics") or {}
    decision = (
        result.get("qc_decision")
        or meta.get("qc_decision")
        or (diag.get("decision") if isinstance(diag, dict) else None)
        or (
            "pass"
            if result.get("status") == "approved"
            else "review"
            if result.get("status") == "review"
            else "review"
        )
    )
    score = float(
        result.get("quality_score")
        or meta.get("quality_score")
        or (diag.get("final_score") if isinstance(diag, dict) else 0)
        or 0.0
    )
    return {
        "file": raw_path.name,
        "raw": str(raw_path),
        "decision": decision,
        "score": score,
        "reasons": result.get("reasons") or [],
        "triggered": (diag.get("triggered_rules") if isinstance(diag, dict) else None)
        or [],
        "reason": (diag.get("reason") if isinstance(diag, dict) else None) or "",
        "spatial_confidence": rf.get("spatial_evidence_confidence"),
        "spatial_verified": rf.get("spatial_verified"),
        "large_contig": rf.get("large_contiguous_foreground_loss"),
        "ok_gate": decision == "pass",
        "timings": result.get("timings") or {},
        "status": result.get("status"),
        "path_label": result.get("path_label"),
    }


def _summarize(rows: list[dict], expected: str) -> tuple[int, int, int]:
    subset = [r for r in rows if r.get("expected") == expected]
    if expected == "pass":
        ok = sum(1 for r in subset if r["decision"] == "pass")
        false_rev = sum(1 for r in subset if r["decision"] == "review")
        soft = sum(1 for r in subset if r["decision"] == "second_pass")
        return ok, false_rev, soft
    ok = sum(1 for r in subset if r["decision"] == "review")
    false_pass = sum(1 for r in subset if r["decision"] == "pass")
    soft = sum(1 for r in subset if r["decision"] == "second_pass")
    return ok, false_pass, soft


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", type=Path, default=ROOT / "tests" / "qc_golden")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        action="append",
        default=None,
        help="Directory containing source RAW/HEIC (repeatable)",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--mode",
        choices=("fast", "adaptive", "quality"),
        default="fast",
        help="Segmentation mode (QC path identical; fast avoids DML OOM on 4GB GPUs)",
    )
    args = parser.parse_args()

    raw_dirs: list[Path] = list(args.raw_dir or [])
    env_raw = os.environ.get("GHATE_RAW_DIR", "").strip()
    if env_raw:
        raw_dirs.append(Path(env_raw))
    default_raw = Path(r"E:\ghateh iran\aks kham")
    if default_raw.is_dir():
        raw_dirs.append(default_raw)
    # de-dupe
    seen: set[str] = set()
    uniq: list[Path] = []
    for d in raw_dirs:
        k = str(d.resolve()) if d.exists() else str(d)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    raw_dirs = uniq

    good_dir = args.dir / "good_should_pass"
    bad_dir = args.dir / "bad_should_review"
    if not list_images(good_dir) and (ROOT / "calibration" / "good").is_dir():
        good_dir = ROOT / "calibration" / "good"
    if not list_images(bad_dir) and (ROOT / "calibration" / "bad").is_dir():
        bad_dir = ROOT / "calibration" / "bad"

    goods = list_images(good_dir) if good_dir.is_dir() else []
    bads = list_images(bad_dir) if bad_dir.is_dir() else []
    if args.limit > 0:
        goods = goods[: args.limit]
        bads = bads[: args.limit]

    cfg = get_qc_config()
    print(f"pipeline={FREE_PIPELINE_VERSION} (production process_free_file)", flush=True)
    print(f"free_mode={args.mode}", flush=True)
    print(
        f"QC pass_min={cfg.pass_min} second_pass_min={cfg.second_pass_min} "
        f"instant_struct_loss={cfg.instant_struct_loss}",
        flush=True,
    )
    print(f"raw_dirs={[str(d) for d in raw_dirs]}", flush=True)
    if not goods and not bads:
        print(f"No samples in {args.dir}")
        return 0

    rows: list[dict] = []
    unresolved: list[str] = []

    with tempfile.TemporaryDirectory(prefix="qc_golden_") as tmp:
        work = Path(tmp)
        print("\n=== REAL GOOD (expect PASS) — production pipeline ===", flush=True)
        for p in goods:
            raw = resolve_raw(p, raw_dirs)
            if raw is None:
                unresolved.append(p.name)
                print(f"[SKIP] {p.name} (no RAW found)", flush=True)
                continue
            try:
                from ghate_editor.model_service import release_memory

                release_memory(empty_cuda_cache=True)
            except Exception:
                pass
            print(f"... scoring {p.name}", flush=True)
            r = _score_one_production(raw, work, free_mode=args.mode)
            r["expected"] = "pass"
            r["dataset"] = "real"
            r["golden_file"] = p.name
            rows.append(r)
            ok = r["decision"] == "pass"
            soft = r["decision"] == "second_pass"
            mark = "OK" if ok else ("SECOND_PASS" if soft else "FALSE_REVIEW")
            print(
                f"[{mark}] {p.name} decision={r['decision']} score={r['score']:.0f} "
                f"conf={r.get('spatial_confidence')} triggered={r.get('triggered')}",
                flush=True,
            )

        print("\n=== REAL BAD (expect REVIEW / not PASS) — production pipeline ===", flush=True)
        for p in bads:
            raw = resolve_raw(p, raw_dirs)
            if raw is None:
                unresolved.append(p.name)
                print(f"[SKIP] {p.name} (no RAW found)", flush=True)
                continue
            try:
                from ghate_editor.model_service import release_memory

                release_memory(empty_cuda_cache=True)
            except Exception:
                pass
            print(f"... scoring {p.name}", flush=True)
            r = _score_one_production(raw, work, free_mode=args.mode)
            r["expected"] = "review"
            r["dataset"] = "real"
            r["golden_file"] = p.name
            rows.append(r)
            ok = r["decision"] != "pass"
            mark = "OK" if ok else "FALSE_PASS"
            print(
                f"[{mark}] {p.name} decision={r['decision']} score={r['score']:.0f} "
                f"conf={r.get('spatial_confidence')} triggered={r.get('triggered')}",
                flush=True,
            )

    g_ok, g_false, g_soft = _summarize(rows, "pass")
    b_ok, b_false, b_soft = _summarize(rows, "review")
    g_n = sum(1 for r in rows if r["expected"] == "pass")
    b_n = sum(1 for r in rows if r["expected"] == "review")
    # Bad acceptance: REVIEW preferred; SECOND_PASS counts as caught (not PASS)
    b_caught = sum(1 for r in rows if r["expected"] == "review" and r["decision"] != "pass")
    real_acc = (g_ok + b_caught) / max(1, g_n + b_n)

    print("\n=== REAL DATASET SUMMARY ===")
    print(f"good={g_n} pass_ok={g_ok} false_review={g_false} second_pass={g_soft}")
    print(f"bad={b_n} review_ok={b_ok} false_pass={b_false} second_pass={b_soft}")
    print(f"REAL accuracy (good PASS + bad not-PASS): {real_acc:.1%}")
    if unresolved:
        print(f"unresolved_raw={unresolved}")

    out = args.json_out or (ROOT / "tests" / "qc_golden" / "last_full_pipeline.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "version": FREE_PIPELINE_VERSION,
        "dataset": "real",
        "good_total": g_n,
        "good_pass": g_ok,
        "false_review": g_false,
        "bad_total": b_n,
        "bad_caught": b_caught,
        "false_pass": b_false,
        "real_accuracy": real_acc,
        "unresolved": unresolved,
    }
    out.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    summary_path = out.with_name("last_full_pipeline_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    print(f"wrote {summary_path}")

    return 0 if b_false == 0 and g_false == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
