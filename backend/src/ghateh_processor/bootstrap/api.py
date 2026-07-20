"""FastAPI application composition root."""

from importlib.metadata import version as distribution_version
from typing import Final

from fastapi import FastAPI

from ghateh_processor.api.system import create_system_router

API_PREFIX: Final = "/api/v1"
DISTRIBUTION_NAME: Final = "ghateh-iran-image-processor"


def create_app() -> FastAPI:
    """Construct and return a new FastAPI application instance."""
    package_version = distribution_version(DISTRIBUTION_NAME)
    application = FastAPI(
        title="Ghateh Iran Image Processor API",
        version=package_version,
    )
    application.include_router(
        create_system_router(version=package_version),
        prefix=API_PREFIX,
    )
    return application
