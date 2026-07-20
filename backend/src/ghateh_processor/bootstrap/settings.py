"""Typed runtime configuration for the local API server."""

from ipaddress import IPv4Address, IPv6Address
from typing import Annotated

from pydantic import AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

type LoopbackAddress = IPv4Address | IPv6Address


def _require_loopback(address: LoopbackAddress) -> LoopbackAddress:
    if not address.is_loopback:
        raise ValueError("API host must be a loopback IP address")
    return address


class ApiRuntimeSettings(BaseSettings):
    """Validated, immutable process-environment settings for the local API."""

    model_config = SettingsConfigDict(
        env_prefix="GHATEH_",
        env_file=None,
        frozen=True,
        validate_default=True,
    )

    api_host: Annotated[LoopbackAddress, AfterValidator(_require_loopback)] = (
        IPv4Address("127.0.0.1")
    )
    api_port: Annotated[int, Field(ge=1024, le=65535)] = 8000


def load_api_runtime_settings() -> ApiRuntimeSettings:
    """Load and validate a fresh runtime configuration instance."""
    return ApiRuntimeSettings()
