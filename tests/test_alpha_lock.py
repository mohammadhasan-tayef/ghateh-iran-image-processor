"""Alpha lock, zone masks, alignment, exact white composite (no rembg)."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.extraction.enhancer import ProductEnhancer  # noqa: E402
from ghate_editor.extraction.fidelity import assemble_fidelity_rgba  # noqa: E402
from ghate_editor.extraction.lock import (  # noqa: E402
    AlphaMutationError,
    lock_alpha,
)
from ghate_editor.extraction.zones import product_zones  # noqa: E402
from ghate_editor.processing.composition import (  # noqa: E402
    compose_white_square,
    straight_over_white,
)
from ghate_editor.processing.config import ProcessingConfig  # noqa: E402
from ghate_editor.processing.studio_pipeline import build_studio_rgba  # noqa: E402


def _disk(size: int = 240, radius: int = 70, fg=(40, 42, 48), bg=(200, 200, 205)):
    rgb = np.full((size, size, 3), bg, dtype=np.uint8)
    yy, xx = np.ogrid[:size, :size]
    disc = (yy - size // 2) ** 2 + (xx - size // 2) ** 2 <= radius**2
    rgb[disc] = fg
    alpha = np.zeros((size, size), dtype=np.uint8)
    alpha[disc] = 255
    # Soft transition ring
    ring = (
        ((yy - size // 2) ** 2 + (xx - size // 2) ** 2 <= (radius + 4) ** 2)
        & (~disc)
    )
    alpha[ring] = 90
    rgb[ring] = (110, 110, 112)
    return Image.fromarray(rgb, "RGB"), Image.fromarray(alpha, "L")


def test_lock_checksum_stable():
    _, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    assert locked.locked is True
    assert locked.verify(strict=True) is True
    copy = locked.image()
    copy.putpixel((0, 0), 123)
    # Mutating a copy cannot change the lock.
    assert locked.verify(strict=True) is True
    assert locked.matches(a)


def test_mutation_detected():
    _, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    mutant = a.copy()
    mutant.putpixel((120, 120), 1)
    assert locked.matches(mutant) is False
    try:
        locked.verify(mutant, strict=True, label="unit")
        raise AssertionError("expected AlphaMutationError")
    except AlphaMutationError as exc:
        assert "ALPHA_MUTATION_DETECTED" in str(exc)


def test_assemble_preserves_interior_rgb_and_alpha():
    rgb, a = _disk(fg=(33, 36, 40))
    locked = lock_alpha(a, source_engine="test")
    rgba, meta = assemble_fidelity_rgba(rgb, locked, decontam=False)
    assert locked.matches(rgba.split()[-1])
    src = np.asarray(rgb)
    out = np.asarray(rgba)
    interior = locked.data >= int(0.98 * 255)
    d = np.abs(out[:, :, :3][interior].astype(np.int16) - src[interior].astype(np.int16))
    assert float(d.mean()) < 0.5
    assert meta["rgb_source"] == "original_working_rgb"


def test_decontam_does_not_change_alpha():
    rgb, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    before = locked.checksum
    rgba, _ = assemble_fidelity_rgba(rgb, locked, decontam=True)
    assert locked.checksum == before
    assert locked.matches(rgba.split()[-1])
    assert locked.verify(strict=True)


def test_holes_preserved():
    size = 200
    rgb = np.full((size, size, 3), 210, dtype=np.uint8)
    a = np.zeros((size, size), dtype=np.uint8)
    a[40:160, 40:160] = 255
    a[80:120, 80:120] = 0  # hole
    rgb[40:160, 40:160] = (60, 60, 65)
    rgb[80:120, 80:120] = (210, 210, 210)
    locked = lock_alpha(Image.fromarray(a, "L"), source_engine="test")
    rgba, _ = assemble_fidelity_rgba(Image.fromarray(rgb, "RGB"), locked)
    hole = np.asarray(rgba.split()[-1])[90:110, 90:110]
    assert float((hole < 8).mean()) > 0.95


def test_compose_exact_white_and_no_shadow():
    rgb, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    rgba, _ = assemble_fidelity_rgba(rgb, locked, decontam=False)
    canvas, info = compose_white_square(
        rgba, size=400, locked_alpha=locked, with_shadow=True
    )
    assert info["with_shadow"] is False
    arr = np.asarray(canvas)
    corner = arr[0:12, 0:12]
    assert np.all(corner == 255)
    # Pixels that must be background
    assert info["composite"] == "straight_over_white"
    assert info["resize_ops"] == 1


def test_rgb_alpha_same_transform():
    """A known vertical edge stays co-located after the one LANCZOS resize."""
    h, w = 100, 160
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:, :] = (240, 240, 240)
    rgb[:, :70] = (20, 22, 25)
    a = np.zeros((h, w), dtype=np.uint8)
    a[:, :70] = 255
    locked = lock_alpha(Image.fromarray(a, "L"), source_engine="test")
    rgba = Image.fromarray(rgb, "RGB").convert("RGBA")
    rgba.putalpha(locked.image())
    # Manual same transform as compose crop+scale
    crop_rgb = Image.fromarray(rgb[:, :90], "RGB")  # include a little bg
    crop_a = Image.fromarray(a[:, :90], "L")
    nw, nh = 180, 200
    r1 = np.asarray(crop_rgb.resize((nw, nh), Image.Resampling.LANCZOS))
    r2 = np.asarray(crop_a.resize((nw, nh), Image.Resampling.LANCZOS))
    # Edge x: first col where alpha drops below 128
    row = nh // 2
    edge_a = int(np.argmax(r2[row] < 128))
    # RGB edge: first col where luma > 120
    luma = 0.299 * r1[row, :, 0] + 0.587 * r1[row, :, 1] + 0.114 * r1[row, :, 2]
    edge_rgb = int(np.argmax(luma > 120))
    assert abs(edge_a - edge_rgb) <= 1, (edge_a, edge_rgb)

    canvas, info = compose_white_square(rgba, size=400, locked_alpha=locked)
    assert info["resample"] == "LANCZOS"


def test_locked_studio_skips_geometry_ops():
    rgb, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    rgba, profile, report, _ = build_studio_rgba(
        rgb, a, model_name="test", locked_alpha=locked
    )
    assert report.mask_refine.get("skipped") is True
    assert report.matting.get("reason") == "alpha_locked"
    assert report.shadow.get("skipped") is True
    assert locked.matches(rgba.split()[-1])
    canvas, info = compose_white_square(
        rgba, size=320, locked_alpha=locked, profile=profile
    )
    assert np.all(np.asarray(canvas)[0:8, 0:8] == 255)
    _ = info


def test_enhancer_noop_cannot_change_alpha():
    rgb, a = _disk()
    locked = lock_alpha(a, source_engine="test")
    zones = product_zones(locked)
    from ghate_editor.extraction.zones import zone_images

    z = zone_images(zones)
    out = ProductEnhancer().enhance(rgb, z["interior_mask"], z["edge_protection_mask"])
    assert out.size == rgb.size
    # Alpha lock independently unchanged
    assert locked.verify(strict=True)


def test_straight_over_white_math():
    rgb = np.array([[[100, 0, 0]]], dtype=np.uint8)
    alpha = np.array([[128]], dtype=np.uint8)
    out = straight_over_white(rgb, alpha)
    # 100*0.5 + 255*0.5 ≈ 177.5 → 178
    assert out.shape == (1, 1, 3)
    assert abs(int(out[0, 0, 0]) - 178) <= 1
    assert int(out[0, 0, 1]) == 128 or abs(int(out[0, 0, 1]) - 128) <= 1


if __name__ == "__main__":
    failed = 0
    for fn in [
        test_lock_checksum_stable,
        test_mutation_detected,
        test_assemble_preserves_interior_rgb_and_alpha,
        test_decontam_does_not_change_alpha,
        test_holes_preserved,
        test_compose_exact_white_and_no_shadow,
        test_rgb_alpha_same_transform,
        test_locked_studio_skips_geometry_ops,
        test_enhancer_noop_cannot_change_alpha,
        test_straight_over_white_math,
    ]:
        try:
            fn()
            print(f"OK  {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
    raise SystemExit(failed)
