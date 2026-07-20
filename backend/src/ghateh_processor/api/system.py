"""System-level HTTP contracts."""

from typing import Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

SERVICE_IDENTIFIER: Final = "ghateh-iran-image-processor"


class LivenessResponse(BaseModel):
    """Public response contract for API process liveness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["ok"]
    service: Literal["ghateh-iran-image-processor"]
    version: str


def create_system_router(*, version: str) -> APIRouter:
    """Create the system router with explicit technical metadata."""
    router = APIRouter()

    @router.get("/health/live", response_model=LivenessResponse)
    def get_liveness() -> LivenessResponse:
        return LivenessResponse(
            status="ok",
            service=SERVICE_IDENTIFIER,
            version=version,
        )

    return router
