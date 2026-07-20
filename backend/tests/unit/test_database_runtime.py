"""Unit tests for process-local runtime database engine ownership."""

import inspect
import socket
from typing import NoReturn, cast

import pytest
from sqlalchemy.engine import URL, Engine
from sqlalchemy.pool import QueuePool

import ghateh_processor.bootstrap.database_runtime as database_runtime_module
from ghateh_processor.bootstrap.database_runtime import (
    DatabaseRuntime,
    create_database_runtime,
)
from ghateh_processor.bootstrap.database_settings import (
    DatabaseSettings,
    load_database_settings,
    resolve_database_url,
)

DATABASE_URL_ENVIRONMENT_VARIABLE = "GHATEH_DATABASE_URL"
UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE = "DATABASE_URL"
FAKE_PASSWORD = "clearly_fake_runtime_password"
FAKE_DATABASE_URL = (
    f"postgresql+psycopg://runtime_user:{FAKE_PASSWORD}@runtime.test.invalid:6543/"
    "ghateh_runtime_test"
)


class _ExpectedContextError(Exception):
    pass


class _ExpectedDisposalError(Exception):
    pass


class _RecordingEngine:
    def __init__(self, disposal_error: Exception | None = None) -> None:
        self.dispose_calls: list[bool] = []
        self.disposal_error = disposal_error

    def dispose(self, *, close: bool = True) -> None:
        self.dispose_calls.append(close)
        if self.disposal_error is not None:
            raise self.disposal_error


def _load_settings(monkeypatch: pytest.MonkeyPatch) -> DatabaseSettings:
    monkeypatch.delenv(UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, FAKE_DATABASE_URL)
    return load_database_settings()


def _runtime_with_recording_engine(
    recording_engine: _RecordingEngine,
) -> DatabaseRuntime:
    return DatabaseRuntime(cast(Engine, recording_engine))


def _deny_network(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("runtime Engine construction attempted network access")


def test_factory_creates_distinct_process_local_runtime_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    original_settings = settings.model_dump()
    first = create_database_runtime(settings)
    second = create_database_runtime(settings)

    try:
        first_engine = first.engine
        second_engine = second.engine

        assert isinstance(first, DatabaseRuntime)
        assert isinstance(first_engine, Engine)
        assert first is not second
        assert first_engine is not second_engine
        assert first_engine.url.drivername == "postgresql+psycopg"
        assert first_engine.url.username == "runtime_user"
        assert first_engine.url.host == "runtime.test.invalid"
        assert first_engine.url.port == 6543
        assert first_engine.url.database == "ghateh_runtime_test"
        assert isinstance(first_engine.pool, QueuePool)
        assert settings.model_dump() == original_settings
    finally:
        first.dispose()
        second.dispose()


def test_factory_does_not_reread_environment_after_settings_are_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    monkeypatch.setenv(
        DATABASE_URL_ENVIRONMENT_VARIABLE,
        "sqlite:///must-not-be-read.db",
    )

    runtime = create_database_runtime(settings)
    try:
        assert runtime.engine.url.host == "runtime.test.invalid"
    finally:
        runtime.dispose()


def test_factory_passes_resolved_url_and_exact_engine_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    recording_engine = _RecordingEngine()
    captured_url: URL | None = None
    captured_options: dict[str, object] = {}

    def recording_create_engine(database_url: URL, **options: object) -> Engine:
        nonlocal captured_url
        captured_url = database_url
        captured_options.update(options)
        return cast(Engine, recording_engine)

    monkeypatch.setattr(
        database_runtime_module,
        "create_engine",
        recording_create_engine,
    )

    runtime = create_database_runtime(settings)
    try:
        assert runtime.engine is cast(Engine, recording_engine)
        assert isinstance(captured_url, URL)
        assert captured_url == resolve_database_url(settings)
        assert captured_options == {
            "poolclass": QueuePool,
            "pool_pre_ping": True,
            "echo": False,
            "hide_parameters": True,
        }
    finally:
        runtime.dispose()


def test_factory_constructs_engine_without_network_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)

    runtime = create_database_runtime(settings)
    try:
        assert isinstance(runtime.engine, Engine)
    finally:
        runtime.dispose()


def test_dispose_is_explicit_idempotent_and_rejects_engine_access() -> None:
    recording_engine = _RecordingEngine()
    runtime = _runtime_with_recording_engine(recording_engine)

    assert not runtime.is_disposed
    assert runtime.engine is cast(Engine, recording_engine)

    runtime.dispose()
    runtime.dispose()

    assert recording_engine.dispose_calls == [True]
    with pytest.raises(RuntimeError, match="^database runtime is disposed$"):
        runtime.engine
    assert runtime.is_disposed


def test_runtime_properties_are_read_only() -> None:
    recording_engine = _RecordingEngine()
    runtime = _runtime_with_recording_engine(recording_engine)

    try:
        with pytest.raises(AttributeError):
            setattr(runtime, "engine", cast(Engine, recording_engine))
        with pytest.raises(AttributeError):
            setattr(runtime, "is_disposed", True)
    finally:
        runtime.dispose()


def test_normal_context_exit_disposes_and_returns_owner() -> None:
    recording_engine = _RecordingEngine()
    runtime = _runtime_with_recording_engine(recording_engine)

    with runtime as entered:
        assert entered is runtime
        assert not entered.is_disposed

    assert runtime.is_disposed
    assert recording_engine.dispose_calls == [True]


def test_exceptional_context_exit_disposes_and_propagates_original_error() -> None:
    recording_engine = _RecordingEngine()
    runtime = _runtime_with_recording_engine(recording_engine)

    with pytest.raises(_ExpectedContextError, match="expected context failure"):
        with runtime:
            raise _ExpectedContextError("expected context failure")

    assert runtime.is_disposed
    assert recording_engine.dispose_calls == [True]


def test_disposal_failure_propagates_without_marking_runtime_disposed() -> None:
    disposal_error = _ExpectedDisposalError("expected disposal failure")
    recording_engine = _RecordingEngine(disposal_error)
    runtime = _runtime_with_recording_engine(recording_engine)

    with pytest.raises(_ExpectedDisposalError) as captured_error:
        runtime.dispose()

    assert captured_error.value is disposal_error
    assert not runtime.is_disposed
    assert runtime.engine is cast(Engine, recording_engine)
    assert recording_engine.dispose_calls == [True]

    recording_engine.disposal_error = None
    runtime.dispose()
    assert runtime.is_disposed


def test_normal_representations_do_not_expose_database_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    runtime = create_database_runtime(settings)

    try:
        representations = (
            repr(runtime),
            str(runtime),
            repr(runtime.engine),
            str(runtime.engine.url),
            repr(runtime.engine.url),
        )
        assert all(FAKE_PASSWORD not in value for value in representations)
    finally:
        runtime.dispose()


def test_module_contract_exposes_only_runtime_owner_and_factory() -> None:
    source = inspect.getsource(database_runtime_module)

    assert database_runtime_module.__all__ == (
        "DatabaseRuntime",
        "create_database_runtime",
    )
    for forbidden_text in (
        "get_secret_value",
        "make_url",
        "os.environ",
        "os.getenv",
        "engine.connect",
        "engine.begin",
        "Session",
        "sessionmaker",
    ):
        assert forbidden_text not in source
    assert not any(
        isinstance(value, (DatabaseRuntime, Engine))
        for value in vars(database_runtime_module).values()
    )
