"""Typed, secret-safe PostgreSQL configuration."""

from typing import Final

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

SUPPORTED_DATABASE_DRIVER: Final = "postgresql+psycopg"


def _parse_and_validate_database_url(value: SecretStr) -> URL:
    try:
        url = make_url(value.get_secret_value())
    except ArgumentError:
        raise ValueError("malformed database URL") from None

    if url.drivername != SUPPORTED_DATABASE_DRIVER:
        raise ValueError("unsupported database driver")
    if not url.username:
        raise ValueError("database username is required")
    if not url.password:
        raise ValueError("database password is required")
    if not url.host:
        raise ValueError("database host is required")

    try:
        port = url.port
    except ValueError:
        raise ValueError("database port is required or invalid") from None

    if port is None or not 1 <= port <= 65535:
        raise ValueError("database port is required or invalid")
    if not url.database:
        raise ValueError("database name is required")
    if url.query:
        raise ValueError("database URL query parameters are not supported")

    return url


class DatabaseSettings(BaseSettings):
    """Validated, immutable process-environment database settings."""

    model_config = SettingsConfigDict(
        env_prefix="GHATEH_",
        env_file=None,
        frozen=True,
        validate_default=True,
    )

    database_url: SecretStr

    def __init__(self) -> None:
        super().__init__()

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: SecretStr) -> SecretStr:
        _parse_and_validate_database_url(value)
        return value


def load_database_settings() -> DatabaseSettings:
    """Load and validate a fresh database configuration instance."""
    return DatabaseSettings()


def resolve_database_url(settings: DatabaseSettings) -> URL:
    """Resolve validated settings into a fresh, redacted SQLAlchemy URL."""
    return _parse_and_validate_database_url(settings.database_url)
