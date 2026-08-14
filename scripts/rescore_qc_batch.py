"""
Re-score approximate decisions from existing QC JSON diagnostics.

Old JSON lacks full metric blobs, but we can replay build_qc_report using
tags (bads/warns/posits) + subscores-derived proxies when present.

This estimates how many REVIEW files would flip under QC v2.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.qc_config import QCConfig, set_qc_config
from ghate_editor.qc_engine import build_qc_report


def replay(d: dict) -> dict:
    bads = list(d.get("bads") or [])
    warns = list(d.get("warns") or [])
    posits = list(d.get("posits") or [])
    subs = d.get("subscores") or {}
    # Build minimal stats that preserve tags; numeric proxies from old scores
    mask = {
        "soft_coverage": 0.12,
        "solid_of_soft": 0.75,
        "fog_ratio": 0.25,
        "mean_alpha_soft": 170,
        "roi_fill": 0.45,
        "main_component_frac": 0.55 if "multi_object_ok" not in posits else 0.3,
        "n_significant_components": 5 if "foreground_fragmented" in bads else 1,
        "n_solid_components": 5 if "foreground_fragmented" in bads else 1,
        "n_tiny_components": 0,
        "bbox_frac": 0.12,
        "bbox_aspect": 1.5,
        "_bads": [b for b in bads if b in {
            "empty_mask", "foreground_fragmented", "foggy_soft_mask",
            "weak_mask_low_opacity", "weak_mask_mean_alpha", "mask_near_full_frame",
            "bbox_implausibly_thin",
        }],
        "_warns": [w for w in warns if w in {
            "foreground_fragmented", "foggy_soft_mask", "weak_mask_low_opacity",
            "weak_mask_mean_alpha", "mask_near_full_frame", "catastrophic_structure_loss",
        }],
        "_posits": [p for p in posits if p in {
            "strong_main_component", "opaque_core", "plausible_coverage",
            "multi_object_ok", "legitimate_holes",
        }],
    }
    # If fragmented but has strong_main + dark posits → treat as kit
    if (
        "foreground_fragmented" in bads
        and "strong_main_component" in posits
        and ("dark_on_white" in posits or "structure_preserved" in posits)
    ):
        mask["_posits"] = list(dict.fromkeys(mask["_posits"] + ["multi_object_ok"]))
        mask["n_significant_components"] = 5
        mask["n_tiny_components"] = 0
        mask["main_component_frac"] = 0.28

    cutout = {
        "fog_of_fg": 0.25,
        "visibility": float(subs.get("exposure_score", 80) or 80) * 0.7,
        "near_white_in_solid": 0.1,
        "solid_std": 30,
        "edge_band_mean_alpha": 120,
        "_bads": [b for b in bads if b in {"foreground_too_small", "product_faded", "foggy_alpha_edges"}],
        "_warns": [w for w in warns if w in {"product_faded", "foggy_alpha_edges"}],
        "_posits": [p for p in posits if p in {"strong_visibility", "dark_high_contrast"}],
    }
    studio = {
        "product_mean": 80 if "dark_on_white" in posits else 140,
        "product_std": 35,
        "product_visibility": 70,
        "light_grey_frac": 0.1,
        "edge_inner_light_frac": 0.15,
        "bg_dirty_frac": 0.005,
        "bg_shadow_frac": 0.002,
        "product_frac": 0.12,
        "studio_roi_fill": 0.5,
        "_bads": [b for b in bads if b in {
            "final_washed_out", "product_faded", "final_too_white_small_product",
            "foreground_fragmented", "foggy_alpha_edges",
        }],
        "_warns": [w for w in warns if w in {"product_faded", "foggy_alpha_edges", "foreground_fragmented"}],
        "_posits": [p for p in posits if p in {
            "dark_on_white", "readable_product", "multi_object_ok", "coherent_dark_core",
        }],
    }
    # Structure
    struct_bad = "catastrophic_structure_loss" in bads
    struct_warn = "catastrophic_structure_loss" in warns
    structure = {
        "structure_loss": 0.50 if struct_bad else (0.26 if struct_warn else 0.08),
        "edge_drop": 0.45 if struct_bad else (0.2 if struct_warn else 0.05),
        "midtone_loss": 0.4 if struct_bad else 0.1,
        "collapsed_regions": 3 if struct_bad else 0,
        "_bads": ["catastrophic_structure_loss"] if struct_bad else [],
        "_warns": ["catastrophic_structure_loss"] if struct_warn and not struct_bad else [],
        "_posits": [p for p in posits if p in {"structure_preserved", "edges_retained", "coherent_edges"}],
    }
    after = bool((d.get("thresholds") or {}).get("after_rescue"))
    return build_qc_report(
        mask, cutout, studio, structure,
        after_rescue=after,
        filename=str(d.get("file") or ""),
    )


def main() -> None:
    qc_dir = Path(sys.argv[1] if len(sys.argv) > 1 else r"E:\final\QC")
    set_qc_config(QCConfig())
    old = Counter()
    new = Counter()
    flips_to_pass = 0
    flips_to_review = 0
    keep_review = 0
    keep_pass = 0
    samples_flip = []

    for p in sorted(qc_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        odec = str(d.get("decision") or "?")
        old[odec] += 1
        rep = replay(d)
        ndec = rep["decision"]
        new[ndec] += 1
        if odec == "review" and ndec == "pass":
            flips_to_pass += 1
            if len(samples_flip) < 8:
                samples_flip.append((d.get("file"), d.get("final_score"), rep["final_score"], rep.get("triggered_rules"), rep.get("processing_profile")))
        elif odec == "pass" and ndec == "review":
            flips_to_review += 1
        elif odec == "review" and ndec == "review":
            keep_review += 1
        elif odec == "pass" and ndec == "pass":
            keep_pass += 1

    print("Old decisions:", dict(old))
    print("New decisions:", dict(new))
    print(f"Former REVIEW -> PASS (est.): {flips_to_pass}")
    print(f"Former PASS -> REVIEW (est.): {flips_to_review}")
    print(f"Stay REVIEW: {keep_review}  Stay PASS: {keep_pass}")
    print("\nSample flips REVIEW->PASS:")
    for s in samples_flip:
        print(" ", s)


if __name__ == "__main__":
    main()
