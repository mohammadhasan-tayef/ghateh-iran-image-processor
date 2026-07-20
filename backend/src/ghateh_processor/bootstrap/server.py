"""Local API server entry point."""

from typing import Final

import uvicorn

from ghateh_processor.bootstrap.settings import load_api_runtime_settings

APPLICATION_FACTORY: Final = "ghateh_processor.bootstrap.api:create_app"


def main() -> None:
    """Validate runtime settings and start the local API server."""
    settings = load_api_runtime_settings()
    uvicorn.run(
        APPLICATION_FACTORY,
        factory=True,
        host=str(settings.api_host),
        port=settings.api_port,
    )
