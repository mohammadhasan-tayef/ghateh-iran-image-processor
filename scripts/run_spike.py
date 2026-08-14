#!/usr/bin/env python3
"""Run Kontext Pro on golden/raw → golden/spike_out (requires FAL_KEY)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from ghate_editor.export import download_url, to_square_white_jpg
from ghate_editor.fal_kontext import edit_image_file, first_image_url
from ghate_editor.prompt import PROMPT_VERSION

RAW = ROOT / "golden" / "raw"
OUT = ROOT / "golden" / "spike_out"
MANIFEST = OUT / "spike_manifest.json"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raws = sorted(RAW.glob("*_raw.png"))
    if not raws:
        print(f"No raws in {RAW}")
        return 1

    entries = []
    for raw in raws:
        stem = raw.name.replace("_raw.png", "")
        print(f"=== {stem} ===")
        payload = edit_image_file(raw)
        url = first_image_url(payload)
        tmp = OUT / f"{stem}_api.png"
        jpg = OUT / f"{stem}_spike.jpg"
        download_url(url, tmp)
        to_square_white_jpg(tmp, jpg)
        entries.append(
            {
                "id": stem,
                "raw": str(raw.relative_to(ROOT)),
                "api_png": str(tmp.relative_to(ROOT)),
                "spike_jpg": str(jpg.relative_to(ROOT)),
                "edited_golden": str(
                    (ROOT / "golden" / "edited" / f"{stem}_edited.png").relative_to(
                        ROOT
                    )
                ),
                "prompt_version": PROMPT_VERSION,
                "image_url": url,
            }
        )
        print(f"wrote {jpg}")

    MANIFEST.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"manifest → {MANIFEST}")
    print("Next: python scripts/score_spike.py  (fill docs/spike-scorecard.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
