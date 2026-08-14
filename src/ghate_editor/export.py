"""Export helpers: square white canvas JPG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def to_square_white_jpg(
    src: Path | str,
    dest: Path | str,
    *,
    size: int = 2000,
    quality: int = 92,
    product_fill: float = 0.85,
) -> Path:
    """Place product on a square white canvas, scaled to fill ~product_fill of the side."""
    src_path = Path(src)
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.open(src_path).convert("RGBA")
    # Flatten any transparency onto white first
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat = Image.alpha_composite(white, img).convert("RGB")

    canvas = Image.new("RGB", (size, size), (255, 255, 255))
    max_side = int(size * product_fill)
    w, h = flat.size
    scale = min(max_side / w, max_side / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    resized = flat.resize((new_w, new_h), Image.Resampling.LANCZOS)
    x = (size - new_w) // 2
    y = (size - new_h) // 2
    canvas.paste(resized, (x, y))
    canvas.save(dest_path, "JPEG", quality=quality, optimize=True)
    return dest_path


def download_url(url: str, dest: Path | str) -> Path:
    import urllib.request

    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, dest_path)
    return dest_path
