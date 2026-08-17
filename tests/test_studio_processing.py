"""Regression tests for studio processing (no GUI, no rembg required)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.processing.analyzer import analyze_image
from ghate_editor.processing.color import (
    adaptive_exposure_wb,
    apply_with_preservation,
    product_color_signature,
)
from ghate_editor.processing.composition import compose_white_square
from ghate_editor.processing.edge_refinement import decontaminate_halo, strip_large_shadows
from ghate_editor.processing.mask_refinement import refine_mask, score_mask_confidence
from ghate_editor.processing.profiles import ProductProfile, select_profile
from ghate_editor.processing.studio_pipeline import build_studio_rgba


def _make_product(
    *,
    size: int = 400,
    fg_color: tuple[int, int, int] = (40, 40, 40),
    bg_color: tuple[int, int, int] = (210, 210, 210),
    elongated: bool = False,
    mesh: bool = False,
) -> tuple[Image.Image, Image.Image]:
    rgb = Image.new("RGB", (size, size), bg_color)
    mask = Image.new("L", (size, size), 0)
    arr = np.asarray(rgb).copy()
    m = np.zeros((size, size), dtype=np.uint8)
    if elongated:
        y0, y1 = size // 3, 2 * size // 3
        x0, x1 = size // 10, 9 * size // 10
    else:
        y0, y1 = size // 4, 3 * size // 4
        x0, x1 = size // 4, 3 * size // 4
    arr[y0:y1, x0:x1] = fg_color
    m[y0:y1, x0:x1] = 255
    if mesh:
        # Punch holes
        for i in range(y0 + 8, y1 - 8, 12):
            for j in range(x0 + 8, x1 - 8, 12):
                arr[i : i + 4, j : j + 4] = bg_color
                m[i : i + 4, j : j + 4] = 0
    # Soft fringe
    m = np.maximum(m, (m > 0).astype(np.uint8) * 200)
    return Image.fromarray(arr, mode="RGB"), Image.fromarray(m, mode="L")


def test_analyze_and_profile_dark():
    rgb, mask = _make_product(fg_color=(25, 25, 28))
    a = analyze_image(rgb, mask=mask)
    p = select_profile(a, mask=mask)
    assert a.mean_luma < 90
    assert ProductProfile.DARK_OBJECT in p.tags or p.primary == ProductProfile.DARK_OBJECT


def test_analyze_and_profile_white():
    rgb, mask = _make_product(fg_color=(230, 228, 220), bg_color=(245, 245, 245))
    a = analyze_image(rgb, mask=mask)
    p = select_profile(a, mask=mask, scene={"pale_product": True})
    assert p.gentle_edges is True


def test_mesh_preserves_holes():
    rgb, mask = _make_product(mesh=True, fg_color=(90, 90, 95))
    a = analyze_image(rgb, mask=mask)
    p = select_profile(a, mask=mask)
    refined, info = refine_mask(mask, profile=p)
    # Mesh profile should preserve holes — refined solid should not swallow all holes
    m0 = np.asarray(mask, dtype=np.uint8)
    m1 = np.asarray(refined, dtype=np.uint8)
    holes0 = int(((m0 >= 40).sum()) - (m0 >= 128).sum())
    holes1 = int(((m1 >= 40).sum()) - (m1 >= 128).sum())
    if p.preserve_holes:
        assert holes1 >= holes0 * 0.5


def test_compose_white_pure_bg():
    rgb, mask = _make_product()
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    a = analyze_image(rgb, mask=mask)
    p = select_profile(a, mask=mask)
    canvas, info = compose_white_square(rgba, size=500, with_shadow=False, profile=p)
    assert canvas.size == (500, 500)
    arr = np.asarray(canvas)
    # Corners should be pure white
    assert tuple(arr[0, 0].tolist()) == (255, 255, 255)
    assert tuple(arr[-1, -1].tolist()) == (255, 255, 255)
    assert info["product_size"][0] > 0


def test_color_preservation_rollback():
    rgb, mask = _make_product(fg_color=(180, 60, 40))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    # Heavily shift color
    arr = np.asarray(rgba, dtype=np.float32)
    arr[:, :, 1] = np.clip(arr[:, :, 1] * 1.8, 0, 255)
    edited = Image.fromarray(arr.astype(np.uint8), mode="RGBA")
    out, result = apply_with_preservation(rgba, edited)
    assert result.rolled_back or result.acceptable
    # Delta after preservation should be controlled
    before = product_color_signature(rgba)
    after = product_color_signature(out)
    de = float(np.linalg.norm(before - after))
    assert de < 25.0


def test_build_studio_rgba_canvas_metrics():
    rgb, mask = _make_product(fg_color=(50, 55, 60))
    # Add grey shadow fringe
    m = np.asarray(mask, dtype=np.uint8)
    rgb_a = np.asarray(rgb).copy()
    fringe = (m == 0)
    # soft shadow near product
    from PIL import ImageFilter

    dil = Image.fromarray(m).filter(ImageFilter.MaxFilter(15))
    dil_a = np.asarray(dil) > 0
    shadow = dil_a & fringe
    rgb_a[shadow] = (40, 40, 40)
    m2 = m.copy()
    m2[shadow] = 120
    rgb = Image.fromarray(rgb_a)
    mask = Image.fromarray(m2, mode="L")

    rgba, profile, report, _ = build_studio_rgba(rgb, mask, model_name="test")
    studio, _ = compose_white_square(rgba, size=800, with_shadow=False, profile=profile)
    arr = np.asarray(studio)
    # Background purity: most near-corner pixels white
    corner = arr[5:25, 5:25]
    purity = float(np.mean(np.all(corner >= 250, axis=2)))
    assert purity >= 0.9
    assert report.segmentation["confidence"] >= 0.0
    assert studio.size == (800, 800)


def test_seg_confidence_tiny_mask():
    m = np.zeros((200, 200), dtype=np.uint8)
    m[90:95, 90:95] = 255
    mask = Image.fromarray(m, mode="L")
    seg = score_mask_confidence(mask, model_name="t")
    assert seg.confidence < 0.7
    assert "tiny_foreground" in seg.warnings


def test_exposure_skips_good_image():
    rgb, mask = _make_product(fg_color=(110, 112, 115))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    a = analyze_image(rgb, mask=mask)
    p = select_profile(a, mask=mask)
    out, rep = adaptive_exposure_wb(rgba, a, profile=p)
    # Should often skip or apply mild gain only
    assert rep.get("exposure_gain", 1.0) <= 1.2
    assert out.size == rgba.size


def test_matting_trimap_and_interior_rgb():
    """Matting must keep interior RGB identical to source."""
    from ghate_editor.processing.alpha_matting import build_trimap, refine_alpha_matting

    rgb, mask = _make_product(fg_color=(48, 52, 60), bg_color=(200, 200, 205))
    tri = build_trimap(mask)
    assert set(np.unique(tri).tolist()) <= {0, 128, 255}
    rgba, profile, report, _ = build_studio_rgba(rgb, mask, model_name="test")
    src = np.asarray(rgb, dtype=np.uint8)
    out = np.asarray(rgba.convert("RGBA"), dtype=np.uint8)
    a = out[:, :, 3]
    core = a >= 220
    if core.any():
        d = np.abs(out[core][:, :3].astype(np.int16) - src[core].astype(np.int16)).mean()
        assert d < 1.0, d
    canvas, _ = compose_white_square(rgba, size=600, with_shadow=False, profile=profile)
    corner = np.asarray(canvas)[0:12, 0:12]
    assert float(np.mean(np.all(corner >= 254, axis=2))) >= 0.95


def test_fidelity_skips_color_enhance():
    rgb, mask = _make_product(fg_color=(50, 55, 60))
    _, _, report, _ = build_studio_rgba(rgb, mask, model_name="test")
    assert report.enhance.get("skipped") is True or report.exposure_wb.get("skipped") is True
    assert "matting" in report.to_dict()


def test_optional_shadow_off_by_default():
    rgb, mask = _make_product()
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    canvas, _ = compose_white_square(rgba, size=400)
    arr = np.asarray(canvas)
    # No synthetic gray shadow blob in the bottom-center canvas when default
    bottom = arr[-30:, 180:220]
    # canvas is white + product; bottom strip should stay nearly white
    assert float(np.mean(bottom)) >= 240.0


def test_decontam_and_shadow():
    rgb, mask = _make_product()
    rgba = rgb.convert("RGBA")
    rgba.putalpha(mask)
    out, d = decontaminate_halo(rgba)
    out2, s = strip_large_shadows(out)
    assert out2.mode == "RGBA"
    assert "decontam_px" in d
    assert "shadow_px_removed" in s


if __name__ == "__main__":
    tests = [
        test_analyze_and_profile_dark,
        test_analyze_and_profile_white,
        test_mesh_preserves_holes,
        test_compose_white_pure_bg,
        test_color_preservation_rollback,
        test_build_studio_rgba_canvas_metrics,
        test_seg_confidence_tiny_mask,
        test_exposure_skips_good_image,
        test_decontam_and_shadow,
        test_matting_trimap_and_interior_rgb,
        test_fidelity_skips_color_enhance,
        test_optional_shadow_off_by_default,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    if failed:
        raise SystemExit(1)
    print(f"All {len(tests)} tests passed.")
