"""Unit tests for typed local API runtime configuration."""

from ipaddress import IPv4Address, IPv6Address
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ghateh_processor.bootstrap.server import APPLICATION_FACTORY, main
from ghateh_processor.bootstrap.settings import load_api_runtime_settings

HOST_ENVIRONMENT_VARIABLE = "GHATEH_API_HOST"
PORT_ENVIRONMENT_VARIABLE = "GHATEH_API_PORT"


def _clear_runtime_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(HOST_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv(PORT_ENVIRONMENT_VARIABLE, raising=False)


def test_runtime_settings_use_typed_defaults_and_fresh_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_environment(monkeypatch)

    first = load_api_runtime_settings()
    second = load_api_runtime_settings()

    assert first.api_host == IPv4Address("127.0.0.1")
    assert first.api_port == 8000
    assert first is not second
    assert first.model_dump() == {
        "api_host": IPv4Address("127.0.0.1"),
        "api_port": 8000,
    }


def test_runtime_settings_are_immutable(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_runtime_environment(monkeypatch)
    settings = load_api_runtime_settings()

    with pytest.raises(ValidationError):
        setattr(settings, "api_port", 9000)


def test_runtime_settings_ignore_unprefixed_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv("API_HOST", "127.0.0.2")
    monkeypatch.setenv("API_PORT", "9000")

    settings = load_api_runtime_settings()

    assert settings.api_host == IPv4Address("127.0.0.1")
    assert settings.api_port == 8000


def test_runtime_settings_accept_an_ipv4_loopback_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv(HOST_ENVIRONMENT_VARIABLE, "127.0.0.2")
    monkeypatch.setenv(PORT_ENVIRONMENT_VARIABLE, "8123")

    settings = load_api_runtime_settings()

    assert settings.api_host == IPv4Address("127.0.0.2")
    assert settings.api_port == 8123


def test_runtime_settings_accept_the_ipv6_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv(HOST_ENVIRONMENT_VARIABLE, "::1")

    settings = load_api_runtime_settings()

    assert settings.api_host == IPv6Address("::1")


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "192.168.1.10", "8.8.8.8", "localhost", "not-an-ip"],
)
def test_runtime_settings_reject_invalid_hosts(
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv(HOST_ENVIRONMENT_VARIABLE, host)

    with pytest.raises(ValidationError):
        load_api_runtime_settings()


@pytest.mark.parametrize("port", ["0", "80", "65536", "not-an-integer"])
def test_runtime_settings_reject_invalid_ports(
    monkeypatch: pytest.MonkeyPatch,
    port: str,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv(PORT_ENVIRONMENT_VARIABLE, port)

    with pytest.raises(ValidationError):
        load_api_runtime_settings()


def test_server_main_invokes_uvicorn_with_validated_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_runtime_environment(monkeypatch)
    monkeypatch.setenv(HOST_ENVIRONMENT_VARIABLE, "127.0.0.3")
    monkeypatch.setenv(PORT_ENVIRONMENT_VARIABLE, "9123")

    with patch("ghateh_processor.bootstrap.server.uvicorn.run") as run_server:
        main()

    run_server.assert_called_once_with(
        APPLICATION_FACTORY,
        factory=True,
        host="127.0.0.3",
        port=9123,
    )
