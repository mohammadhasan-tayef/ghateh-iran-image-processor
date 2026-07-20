"""Unit tests for typed PostgreSQL configuration."""

import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy.engine import URL

from ghateh_processor.bootstrap.database_settings import (
    DatabaseSettings,
    load_database_settings,
    resolve_database_url,
)

DATABASE_URL_ENVIRONMENT_VARIABLE = "GHATEH_DATABASE_URL"
UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE = "DATABASE_URL"
VALID_DATABASE_URL = (
    "postgresql+psycopg://app_user:fake_password@postgres:5432/ghateh_processor"
)


def _clear_database_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv(UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)


def _load_from_environment(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> DatabaseSettings:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, database_url)
    return load_database_settings()


def test_database_settings_define_one_required_field() -> None:
    assert set(DatabaseSettings.model_fields) == {"database_url"}
    assert DatabaseSettings.model_fields["database_url"].is_required()


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_database_environment(monkeypatch)

    with pytest.raises(ValidationError):
        load_database_settings()


def test_unprefixed_database_url_is_not_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv(
        UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE,
        VALID_DATABASE_URL,
    )

    with pytest.raises(ValidationError):
        load_database_settings()


def test_loader_returns_fresh_settings_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, VALID_DATABASE_URL)

    first = load_database_settings()
    second = load_database_settings()

    assert first is not second


def test_database_settings_are_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _load_from_environment(monkeypatch, VALID_DATABASE_URL)

    with pytest.raises(ValidationError):
        setattr(settings, "database_url", SecretStr("replacement"))


def test_resolver_preserves_validated_database_url_components(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_from_environment(
        monkeypatch,
        "postgresql+psycopg://app_user:fake%40password%3Avalue@postgres:6543/"
        "ghateh_processor",
    )

    resolved_url = resolve_database_url(settings)

    assert isinstance(resolved_url, URL)
    assert resolved_url.drivername == "postgresql+psycopg"
    assert resolved_url.username == "app_user"
    assert resolved_url.password == "fake@password:value"
    assert resolved_url.host == "postgres"
    assert resolved_url.port == 6543
    assert resolved_url.database == "ghateh_processor"


def test_resolver_returns_independent_values_without_mutating_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_from_environment(monkeypatch, VALID_DATABASE_URL)
    original_serialization = settings.model_dump()

    first = resolve_database_url(settings)
    second = resolve_database_url(settings)

    assert first == second
    assert first is not second
    assert settings.model_dump() == original_serialization


@pytest.mark.parametrize(
    "database_url",
    [
        pytest.param(VALID_DATABASE_URL, id="docker-service-hostname"),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@192.168.1.10:5432/"
            "ghateh_processor",
            id="ipv4-host",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@[2001:db8::1]:5432/"
            "ghateh_processor",
            id="bracketed-ipv6-host",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake%40password%3Avalue@postgres:5432/"
            "ghateh_processor",
            id="percent-encoded-password",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres:6543/"
            "ghateh_processor",
            id="non-default-port",
        ),
    ],
)
def test_supported_database_urls_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    settings = _load_from_environment(monkeypatch, database_url)

    assert isinstance(settings.database_url, SecretStr)


@pytest.mark.parametrize(
    "database_url",
    [
        pytest.param("sqlite:///local.db", id="sqlite"),
        pytest.param(
            "postgresql://app_user:fake_password@postgres:5432/ghateh_processor",
            id="generic-postgresql",
        ),
        pytest.param(
            "postgresql+asyncpg://app_user:fake_password@postgres:5432/"
            "ghateh_processor",
            id="asyncpg",
        ),
        pytest.param(
            "postgresql+psycopg2://app_user:fake_password@postgres:5432/"
            "ghateh_processor",
            id="psycopg2",
        ),
    ],
)
def test_unsupported_database_drivers_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        _load_from_environment(monkeypatch, database_url)


@pytest.mark.parametrize(
    "database_url",
    [
        pytest.param(
            "postgresql+psycopg://:fake_password@postgres:5432/ghateh_processor",
            id="missing-username",
        ),
        pytest.param(
            "postgresql+psycopg://app_user@postgres:5432/ghateh_processor",
            id="missing-password",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@:5432/ghateh_processor",
            id="missing-host",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres/ghateh_processor",
            id="missing-port",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres:5432",
            id="missing-database-name",
        ),
        pytest.param("not a database URL", id="malformed"),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres:0/ghateh_processor",
            id="zero-port",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres:65536/"
            "ghateh_processor",
            id="port-above-maximum",
        ),
        pytest.param(
            "postgresql+psycopg://app_user:fake_password@postgres:not-a-port/"
            "ghateh_processor",
            id="non-integer-port",
        ),
    ],
)
def test_incomplete_or_malformed_database_urls_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    database_url: str,
) -> None:
    with pytest.raises(ValidationError):
        _load_from_environment(monkeypatch, database_url)


@pytest.mark.parametrize(
    "query_string",
    [
        pytest.param("sslmode=require", id="sslmode"),
        pytest.param("host=other-host", id="alternate-host"),
        pytest.param("port=5433", id="alternate-port"),
        pytest.param("user=other-user", id="alternate-user"),
        pytest.param("password=other-password", id="alternate-password"),
        pytest.param("dbname=other-database", id="alternate-database"),
        pytest.param("application_name=ghateh", id="application-name"),
        pytest.param("unapproved=value", id="unknown-parameter"),
        pytest.param(
            "sslmode=require&application_name=ghateh",
            id="multiple-parameters",
        ),
    ],
)
def test_database_url_query_parameters_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    query_string: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match="database URL query parameters are not supported",
    ):
        _load_from_environment(monkeypatch, f"{VALID_DATABASE_URL}?{query_string}")


def test_database_credentials_are_redacted_from_normal_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_password = "clearly_fake_test_password"
    settings = _load_from_environment(
        monkeypatch,
        f"postgresql+psycopg://app_user:{fake_password}@postgres:5432/ghateh_processor",
    )
    resolved_url = resolve_database_url(settings)

    assert fake_password not in repr(settings)
    assert fake_password not in str(settings.database_url)
    assert fake_password not in repr(settings.model_dump())
    assert fake_password not in settings.model_dump_json()
    assert fake_password not in str(resolved_url)
    assert fake_password not in repr(resolved_url)


def test_invalid_database_url_errors_redact_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_password = "clearly_fake_invalid_password"
    invalid_url = (
        f"postgresql+psycopg://app_user:{fake_password}@postgres:not-a-port/"
        "ghateh_processor"
    )

    with pytest.raises(ValidationError) as error:
        _load_from_environment(monkeypatch, invalid_url)

    assert fake_password not in str(error.value)


def test_query_validation_errors_redact_credentials_and_query_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_password = "clearly_fake_query_password"
    fake_query_value = "clearly_fake_query_value"
    invalid_url = (
        f"postgresql+psycopg://app_user:{fake_password}@postgres:5432/"
        f"ghateh_processor?password={fake_query_value}"
    )

    with pytest.raises(ValidationError) as error:
        _load_from_environment(monkeypatch, invalid_url)

    error_text = str(error.value)
    assert "database URL query parameters are not supported" in error_text
    assert fake_password not in error_text
    assert fake_query_value not in error_text
