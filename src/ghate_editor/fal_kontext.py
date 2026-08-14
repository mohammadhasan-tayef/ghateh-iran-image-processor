"""fal.ai FLUX.1 Kontext [pro] client helpers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .prompt import ECOMMERCE_WHITE_STUDIO_PROMPT, FAL_MODEL_ID, PROMPT_VERSION


def get_fal_key() -> str:
    key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY") or ""
    if not key:
        raise RuntimeError(
            "Missing FAL_KEY. Set it in the environment or a .env file "
            "(see .env.example)."
        )
    return key


def configure_fal() -> None:
    """Ensure FAL_KEY is present (fal_client reads it from the environment)."""
    os.environ["FAL_KEY"] = get_fal_key()


def edit_image_file(
    image_path: Path | str,
    *,
    prompt: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """Upload a local image and run Kontext Pro. Returns fal result dict."""
    import fal_client

    configure_fal()
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    image_url = fal_client.upload_file(str(path))
    payload: dict[str, Any] = {
        "prompt": prompt or ECOMMERCE_WHITE_STUDIO_PROMPT,
        "image_url": image_url,
    }
    if seed is not None:
        payload["seed"] = seed

    result = fal_client.subscribe(
        FAL_MODEL_ID,
        arguments=payload,
        with_logs=False,
    )
    return {
        "prompt_version": PROMPT_VERSION,
        "model": FAL_MODEL_ID,
        "result": result,
    }


def first_image_url(result_payload: dict[str, Any]) -> str:
    result = result_payload.get("result") or result_payload
    images = result.get("images") or []
    if not images:
        raise RuntimeError(f"No images in fal result: {result!r}")
    url = images[0].get("url")
    if not url:
        raise RuntimeError(f"Missing image URL in fal result: {result!r}")
    return url
