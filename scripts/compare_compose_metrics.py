"""Compare legacy vs studio compose metrics on synthetic products (no rembg)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ghate_editor.free_pipeline import compose_studio_square, enhance_product, clean_cutout_edges
from ghate_editor.processing.analyzer import analyze_image
from ghate_editor.processing.composition import compose_white_square
from ghate_editor.processing.profiles import select_profile
from ghate_editor.processing.studio_pipeline import build_studio_rgba


def _sample(kind: str) -> tuple[Image.Image, Image.Image]:
    size = 600
    bg = (220, 220, 220)
    rgb = np.full((size, size, 3), bg, dtype=np.uint8)
    m = np.zeros((size, size), dtype=np.uint8)
    if kind == "dark":
        rgb[150:450, 150:450] = (30, 32, 35)
        m[150:450, 150:450] = 255
    elif kind == "white":
        rgb[150:450, 150:450] = (235, 232, 225)
        m[150:450, 150:450] = 255
    elif kind == "hose":
        rgb[250:350, 40:560] = (45, 45, 48)
        m[250:350, 40:560] = 255
    elif kind == "mesh":
        rgb[120:480, 120:480] = (100, 100, 105)
        m[120:480, 120:480] = 255
        for i in range(140, 460, 14):
            for j in range(140, 460, 14):
                rgb[i : i + 5, j : j + 5] = bg
                m[i : i + 5, j : j + 5] = 0
    else:
        rgb[150:450, 150:450] = (120, 80, 60)
        m[150:450, 150:450] = 255
    # Halo contamination
    fringe = (m > 0)
    from PIL import ImageFilter

    dil = np.asarray(Image.fromarray(m).filter(ImageFilter.MaxFilter(7))) > 0
    halo = dil & (~fringe)
    rgb[halo] = (200, 200, 200)
    m[halo] = 90
    return Image.fromarray(rgb), Image.fromarray(m, mode="L")


def _metrics(canvas: Image.Image, rgba: Image.Image) -> dict:
    arr = np.asarray(canvas)
    corner = arr[0:40, 0:40]
    bg_purity = float(np.mean(np.all(corner >= 250, axis=2)))
    a = np.asarray(rgba.split()[-1], dtype=np.float32)
    fg = float((a >= 40).mean())
    return {
        "bg_purity": round(bg_purity, 4),
        "fg_frac_cutout": round(fg, 4),
        "size": list(canvas.size),
    }


def main() -> None:
    kinds = ["dark", "white", "hose", "mesh", "normal"]
    print("kind | path | bg_purity | time_s")
    for kind in kinds:
        rgb, mask = _sample(kind)
        rgba0 = rgb.convert("RGBA")
        rgba0.putalpha(mask)

        t0 = time.perf_counter()
        legacy = compose_studio_square(rgba0, size=800, with_shadow=False)
        t_legacy = time.perf_counter() - t0
        m_legacy = _metrics(legacy, rgba0)

        t0 = time.perf_counter()
        rgba1, profile, _, _ = build_studio_rgba(rgb, mask, model_name="synth")
        studio, _ = compose_white_square(rgba1, size=800, with_shadow=False, profile=profile)
        t_new = time.perf_counter() - t0
        m_new = _metrics(studio, rgba1)

        print(
            f"{kind:6} | legacy | {m_legacy['bg_purity']:.4f} | {t_legacy:.3f} | profile=-"
        )
        print(
            f"{kind:6} | studio | {m_new['bg_purity']:.4f} | {t_new:.3f} | profile={profile.primary.value}"
        )


if __name__ == "__main__":
    main()
