"""Micro-profile studio + QC stages on one calibration image."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.free_pipeline import (  # noqa: E402
    analyze_scene,
    evaluate_structure_consistency,
    evaluate_studio_quality,
    open_rgb,
    segment_mask,
)
from ghate_editor.model_service import warmup  # noqa: E402
from ghate_editor.processing.analyzer import analyze_image  # noqa: E402
from ghate_editor.processing.color import (  # noqa: E402
    adaptive_exposure_wb,
    apply_with_preservation,
)
from ghate_editor.processing.composition import compose_white_square  # noqa: E402
from ghate_editor.processing.config import DEFAULT_PROCESSING  # noqa: E402
from ghate_editor.processing.edge_refinement import (  # noqa: E402
    decontaminate_halo,
    refine_edges,
    strip_large_shadows,
)
from ghate_editor.processing.enhancement import adaptive_denoise_sharpen  # noqa: E402
from ghate_editor.processing.mask_refinement import (  # noqa: E402
    refine_mask,
    score_mask_confidence,
)
from ghate_editor.processing.profiles import select_profile  # noqa: E402
from ghate_editor.processing.studio_pipeline import build_studio_rgba  # noqa: E402
from ghate_editor.qc_raw_final import compute_raw_final_integrity  # noqa: E402


def timed(name: str, fn):
    t0 = time.perf_counter()
    r = fn()
    dt = time.perf_counter() - t0
    print(f"{name:30s} {dt:.3f}s")
    return r


def main() -> None:
    warmup("u2net")
    src = ROOT / "calibration" / "good" / "2026_06_08_17_09_50_IMG_4042.HEIC"
    working = open_rgb(src)
    scene = analyze_scene(working)
    mask, iw, ih = segment_mask(working, max_side=768, model_name="u2net", scene=scene)
    print("working", working.size, "infer", iw, ih)

    seg = timed(
        "score_mask_confidence",
        lambda: score_mask_confidence(mask, model_name="u2net", rgb=working),
    )
    analysis = timed("analyze_image", lambda: analyze_image(working, mask=seg.mask))
    profile = timed(
        "select_profile",
        lambda: select_profile(analysis, mask=seg.mask, scene=scene, cfg=DEFAULT_PROCESSING),
    )
    refined, _info = timed(
        "refine_mask",
        lambda: refine_mask(seg.mask, profile=profile, cfg=DEFAULT_PROCESSING),
    )
    rgba = working.convert("RGBA")
    rgba.putalpha(refined.convert("L"))
    rgba, _ = timed(
        "refine_edges",
        lambda: refine_edges(rgba, working, profile=profile, cfg=DEFAULT_PROCESSING),
    )
    rgba, _ = timed(
        "strip_large_shadows",
        lambda: strip_large_shadows(rgba, cfg=DEFAULT_PROCESSING),
    )
    rgba, _ = timed(
        "decontaminate_halo",
        lambda: decontaminate_halo(rgba, profile=profile, cfg=DEFAULT_PROCESSING),
    )
    edited, _ = timed(
        "adaptive_exposure_wb",
        lambda: adaptive_exposure_wb(rgba, analysis, profile=profile, cfg=DEFAULT_PROCESSING),
    )
    edited, _ = timed(
        "color_preservation",
        lambda: apply_with_preservation(rgba, edited, cfg=DEFAULT_PROCESSING),
    )
    a2 = timed(
        "analyze_image_2",
        lambda: analyze_image(edited.convert("RGB"), mask=edited.split()[-1]),
    )
    edited, _ = timed(
        "denoise_sharpen",
        lambda: adaptive_denoise_sharpen(edited, a2, profile=profile, cfg=DEFAULT_PROCESSING),
    )
    timed(
        "build_studio_rgba_full",
        lambda: build_studio_rgba(working, mask, scene=scene, model_name="u2net"),
    )

    studio, _ = compose_white_square(
        edited, size=2000, with_shadow=False, profile=profile, cfg=DEFAULT_PROCESSING
    )
    timed(
        "evaluate_structure",
        lambda: evaluate_structure_consistency(working, edited, scene=scene),
    )
    timed(
        "evaluate_studio",
        lambda: evaluate_studio_quality(studio, scene=scene),
    )
    timed(
        "compute_raw_final",
        lambda: compute_raw_final_integrity(working, edited, studio_rgb=studio),
    )


if __name__ == "__main__":
    main()
