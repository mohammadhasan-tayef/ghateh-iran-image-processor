"""Unit tests for trimap / local alpha matting (no rembg)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.processing.alpha_matting import (  # noqa: E402
    TRIMAP_BG,
    TRIMAP_FG,
    TRIMAP_UNKNOWN,
    build_trimap,
    refine_alpha_matting,
    uncomposite_edge_rgb,
)
from ghate_editor.processing.edge_refinement import uncomposite_edge_band  # noqa: E402
from ghate_editor.processing.studio_pipeline import build_studio_rgba  # noqa: E402


def _disk_product(size: int = 240) -> tuple[Image.Image, Image.Image]:
    rgb = np.full((size, size, 3), 200, dtype=np.uint8)
    yy, xx = np.ogrid[:size, :size]
    cy, cx = size // 2, size // 2
    r = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    disc = r < 70
    rgb[disc] = (48, 52, 58)
    # Gray floor halo around disc (contamination)
    ring = (r >= 70) & (r < 82)
    rgb[ring] = (90, 90, 92)
    # Soft rembg-like mask that includes some halo
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[r < 70] = 255
    alpha[ring] = 110
    return Image.fromarray(rgb, "RGB"), Image.fromarray(alpha, "L")


def test_trimap_unknown_is_thin_ring():
    _, mask = _disk_product()
    tri = build_trimap(mask)
    unk = float((tri == TRIMAP_UNKNOWN).mean())
    assert 0.002 < unk < 0.20, unk
    assert (tri == TRIMAP_FG).any()
    assert (tri == TRIMAP_BG).any()


def test_matting_drops_halo_ring():
    rgb, mask = _disk_product()
    alpha, info = refine_alpha_matting(rgb, mask, max_side=240)
    a = np.asarray(alpha, dtype=np.uint8)
    yy, xx = np.ogrid[:240, :240]
    r = np.sqrt((yy - 120) ** 2 + (xx - 120) ** 2)
    core = float(a[r < 50].mean())
    halo = float(a[(r >= 74) & (r < 82)].mean())
    assert core > 200, core
    assert halo < 110, (halo, info)


def test_uncomposite_only_edge_changes_rgb():
    rgb = np.full((80, 80, 3), 40, dtype=np.uint8)
    alpha = np.zeros((80, 80), dtype=np.float32)
    alpha[20:60, 20:60] = 1.0
    alpha[18:62, 18:20] = 0.4
    rgb[18:62, 18:20] = (180, 180, 180)  # mixed gray fringe
    out = uncomposite_edge_rgb(rgb, alpha, np.array([200.0, 200.0, 200.0]))
    # Interior unchanged
    assert np.array_equal(out[30:50, 30:50], rgb[30:50, 30:50])
    # Fringe pulled away from gray toward product
    assert int(out[20, 18].mean()) < 180


def test_interior_rgb_preserved_in_studio():
    rgb, mask = _disk_product()
    rgba, _p, report, _ = build_studio_rgba(rgb, mask, model_name="test")
    arr = np.asarray(rgba)
    a = arr[:, :, 3]
    core = a >= 200
    src = np.asarray(rgb)
    # Interior core RGB should match source (fidelity)
    if core.any():
        delta = np.abs(arr[core][:, :3].astype(np.int16) - src[core].astype(np.int16)).mean()
        assert delta < 2.5, delta
    assert "matting" in report.to_dict()


def test_white_canvas_no_synthetic_shadow_in_compose():
    from ghate_editor.processing.composition import compose_white_square

    rgb, mask = _disk_product()
    rgba, profile, _, _ = build_studio_rgba(rgb, mask, model_name="test")
    canvas, _ = compose_white_square(rgba, size=400, with_shadow=False, profile=profile)
    arr = np.asarray(canvas)
    # Corners pure white
    assert tuple(arr[2, 2].tolist()) == (255, 255, 255)
    # No dark synthetic shadow blob in bottom-center off-product?
    # At least corners and far edges stay white
    edge_row = arr[-8:, :]
    white_frac = float(np.mean(np.all(edge_row >= 250, axis=2)))
    assert white_frac > 0.55, white_frac


if __name__ == "__main__":
    tests = [
        test_trimap_unknown_is_thin_ring,
        test_matting_drops_halo_ring,
        test_uncomposite_only_edge_changes_rgb,
        test_interior_rgb_preserved_in_studio,
        test_white_canvas_no_synthetic_shadow_in_compose,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"OK  {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    raise SystemExit(1 if failed else 0)
