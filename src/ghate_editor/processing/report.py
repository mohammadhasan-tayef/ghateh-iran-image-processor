"""Append per-image processing reports (JSONL + optional CSV rollup)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


REPORT_FIELDS = [
    "filename",
    "status",
    "profile",
    "segmentation_model",
    "segmentation_confidence",
    "second_model_used",
    "mask_warnings",
    "exposure_correction",
    "white_balance_correction",
    "color_drift",
    "sharpness_adjustment",
    "second_pass_used",
    "processing_time",
    "qc_decision",
    "pipeline_version",
]


def build_report_row(
    *,
    filename: str,
    status: str,
    meta: dict[str, Any] | None,
    timings: dict[str, float] | None = None,
    pipeline_version: str = "",
) -> dict[str, Any]:
    meta = meta or {}
    studio = meta.get("studio_processing") or {}
    seg = studio.get("segmentation") or {}
    exp = studio.get("exposure_wb") or {}
    cpres = studio.get("color_preserve") or {}
    enh = studio.get("enhance") or {}
    profile = (studio.get("profile") or meta.get("product_profile") or {}).get(
        "primary", ""
    )
    warnings = seg.get("warnings") or []
    return {
        "filename": filename,
        "status": status,
        "profile": profile,
        "segmentation_model": meta.get("model") or seg.get("model_name") or "",
        "segmentation_confidence": seg.get("confidence", ""),
        "second_model_used": bool(meta.get("use_roi") or "+" in str(meta.get("model") or "")),
        "mask_warnings": ";".join(str(w) for w in warnings),
        "exposure_correction": exp.get("exposure_gain", 1.0),
        "white_balance_correction": exp.get("wb_applied", False),
        "color_drift": cpres.get("delta_e", ""),
        "sharpness_adjustment": enh.get("sharpen", 0.0),
        "second_pass_used": bool(meta.get("after_rescue") or meta.get("use_roi")),
        "processing_time": round(float((timings or {}).get("total") or 0.0), 3),
        "qc_decision": meta.get("qc_decision") or "",
        "pipeline_version": pipeline_version,
    }


def append_jsonl(path: Path | str, row: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def write_csv_from_jsonl(jsonl_path: Path | str, csv_path: Path | str) -> None:
    jsonl_path = Path(jsonl_path)
    csv_path = Path(csv_path)
    if not jsonl_path.exists():
        return
    rows: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    if not rows:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in REPORT_FIELDS})
