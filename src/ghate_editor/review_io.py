"""Review packaging: stable IDs, Edited/Original pairs, manifest. Source files are never modified."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_DIR_NAME = "Review"
APPROVED_DIR_NAME = "Approved"
REVIEW_EDITED_DIR = "Edited"
REVIEW_ORIGINAL_DIR = "Original"
REVIEW_MANIFEST_NAME = "review_manifest.csv"

MANIFEST_COLUMNS = [
    "review_id",
    "original_filename",
    "original_source_path",
    "review_original_path",
    "review_edited_path",
    "review_reason",
    "processing_mode",
    "fallback_used",
    "quality_metrics",
    "processing_time",
    "timestamp",
]


def normalize_source_path(path: Path | str) -> str:
    """Stable path key (case-folded, forward slashes) for hashing across resumes."""
    p = Path(path)
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p.absolute()
    return str(resolved).replace("\\", "/").casefold()


def make_stable_id(source_path: Path | str, *, digest_len: int = 6) -> str:
    """
    Deterministic review/output ID: {stem}__{sha256[:6]} of normalized source path.
    Same source path → same ID across processes/resumes. Different folders with
    identical filenames get different digests.
    """
    path = Path(source_path)
    stem = path.stem.strip() or "image"
    # Windows-safe stem
    for ch in '<>:"/\\|?*':
        stem = stem.replace(ch, "_")
    digest = hashlib.sha256(normalize_source_path(path).encode("utf-8")).hexdigest()[
        : max(4, digest_len)
    ]
    return f"{stem}__{digest}"


def approved_dir(output_dir: Path) -> Path:
    return Path(output_dir) / APPROVED_DIR_NAME


def review_dir(output_dir: Path) -> Path:
    return Path(output_dir) / REVIEW_DIR_NAME


def review_edited_dir(output_dir: Path) -> Path:
    return review_dir(output_dir) / REVIEW_EDITED_DIR


def review_original_dir(output_dir: Path) -> Path:
    return review_dir(output_dir) / REVIEW_ORIGINAL_DIR


def review_manifest_path(output_dir: Path) -> Path:
    return review_dir(output_dir) / REVIEW_MANIFEST_NAME


def ensure_output_layout(output_dir: Path) -> None:
    """Create Approved/ and Review/{Edited,Original}/. Never touches sources."""
    approved_dir(output_dir).mkdir(parents=True, exist_ok=True)
    review_edited_dir(output_dir).mkdir(parents=True, exist_ok=True)
    review_original_dir(output_dir).mkdir(parents=True, exist_ok=True)


def load_existing_review_ids(output_dir: Path) -> set[str]:
    """In-memory set of review IDs already present (Edited JPGs + manifest)."""
    ids: set[str] = set()
    edited = review_edited_dir(output_dir)
    try:
        for p in edited.glob("*.jpg"):
            ids.add(p.stem)
        for p in edited.glob("*.JPG"):
            ids.add(p.stem)
    except FileNotFoundError:
        pass
    manifest = review_manifest_path(output_dir)
    if manifest.is_file():
        try:
            with manifest.open("r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rid = (row.get("review_id") or "").strip()
                    if rid:
                        ids.add(rid)
        except Exception:
            pass
    return ids


def load_existing_output_ids(output_dir: Path) -> set[str]:
    """Approved + Review IDs for resume skip (stable IDs, not raw stems)."""
    ids = load_existing_review_ids(output_dir)
    adir = approved_dir(output_dir)
    try:
        for p in adir.glob("*.jpg"):
            ids.add(p.stem)
        for p in adir.glob("*.JPG"):
            ids.add(p.stem)
    except FileNotFoundError:
        pass
    # Legacy: JPGs sitting directly in output root (pre-Approved/ layout)
    try:
        with __import__("os").scandir(output_dir) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".jpg"):
                    ids.add(Path(entry.name).stem)
    except FileNotFoundError:
        pass
    # Legacy flat Review/*.jpg
    rdir = review_dir(output_dir)
    try:
        with __import__("os").scandir(rdir) as it:
            for entry in it:
                if entry.is_file() and entry.name.lower().endswith(".jpg"):
                    ids.add(Path(entry.name).stem)
    except FileNotFoundError:
        pass
    return ids


def copy_source_for_review(
    source_path: Path,
    *,
    output_dir: Path,
    review_id: str,
) -> Path:
    """
    COPY source into Review/Original/{review_id}{ext}.
    Never moves/renames/modifies the original. Skips if dest already exists.
    """
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source not found for Review copy: {src}")
    dest_dir = review_original_dir(output_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{review_id}{src.suffix}"
    if dest.is_file():
        return dest
    # copy2 preserves metadata; source untouched
    shutil.copy2(src, dest)
    return dest


def append_review_manifest(
    output_dir: Path,
    *,
    review_id: str,
    original_filename: str,
    original_source_path: str,
    review_original_path: str,
    review_edited_path: str,
    review_reason: str,
    processing_mode: str,
    fallback_used: bool,
    quality_metrics: str | dict[str, Any] | None,
    processing_time: float | None,
    known_ids: set[str] | None = None,
) -> bool:
    """
    Append one manifest row. Returns False if review_id already recorded (no dup).
    """
    if known_ids is not None and review_id in known_ids:
        # May already be in Edited from prior partial write — still skip duplicate row
        return False

    path = review_manifest_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Double-check file for this ID
    if path.is_file():
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if (row.get("review_id") or "").strip() == review_id:
                        if known_ids is not None:
                            known_ids.add(review_id)
                        return False
        except Exception:
            pass

    metrics_str = ""
    if isinstance(quality_metrics, dict):
        try:
            metrics_str = json.dumps(quality_metrics, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            metrics_str = str(quality_metrics)
    elif quality_metrics is not None:
        metrics_str = str(quality_metrics)

    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(
            {
                "review_id": review_id,
                "original_filename": original_filename,
                "original_source_path": original_source_path,
                "review_original_path": review_original_path,
                "review_edited_path": review_edited_path,
                "review_reason": review_reason,
                "processing_mode": processing_mode,
                "fallback_used": "yes" if fallback_used else "no",
                "quality_metrics": metrics_str,
                "processing_time": (
                    f"{processing_time:.2f}" if processing_time is not None else ""
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
    if known_ids is not None:
        known_ids.add(review_id)
    return True


def finalize_review_package(
    *,
    output_dir: Path,
    source_path: Path,
    edited_image: Any,
    review_id: str,
    reasons: list[str],
    processing_mode: str,
    fallback_used: bool,
    quality_metrics: dict[str, Any] | None,
    processing_time: float | None,
    jpeg_quality: int = 90,
    known_ids: set[str] | None = None,
) -> dict[str, Any]:
    """
    Single-shot Review write: Edited JPG first, then best-effort Original copy + manifest.
    Copy/manifest failures are logged in the return dict — they must NOT fail the image.
    """
    ensure_output_layout(output_dir)
    edited_dir = review_edited_dir(output_dir)
    edited_path = edited_dir / f"{review_id}.jpg"
    if not edited_path.is_file():
        edited_image.save(edited_path, "JPEG", quality=jpeg_quality, optimize=False)

    original_copy_path: Path | None = None
    original_copy_error: str | None = None
    for attempt in range(2):
        try:
            original_copy_path = copy_source_for_review(
                source_path, output_dir=output_dir, review_id=review_id
            )
            original_copy_error = None
            break
        except Exception as exc:  # noqa: BLE001
            original_copy_error = str(exc)
            if attempt == 0:
                continue

    manifest_error: str | None = None
    try:
        append_review_manifest(
            output_dir,
            review_id=review_id,
            original_filename=Path(source_path).name,
            original_source_path=str(Path(source_path).resolve()),
            review_original_path=(
                str(original_copy_path.resolve()) if original_copy_path else ""
            ),
            review_edited_path=str(edited_path.resolve()),
            review_reason=";".join(reasons),
            processing_mode=processing_mode,
            fallback_used=fallback_used,
            quality_metrics=quality_metrics,
            processing_time=processing_time,
            known_ids=known_ids,
        )
    except Exception as exc:  # noqa: BLE001
        manifest_error = str(exc)

    return {
        "review_id": review_id,
        "edited_path": edited_path,
        "original_copy_path": original_copy_path,
        "manifest": review_manifest_path(output_dir),
        "original_copy_error": original_copy_error,
        "manifest_error": manifest_error,
    }
