"""Unit tests for the application-runtime database connectivity probe."""

import inspect
import socket
from collections.abc import Callable
from decimal import Decimal
from types import TracebackType
from typing import NoReturn, cast

import pytest
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.sql.elements import TextClause

import ghateh_processor.bootstrap.database_connectivity as connectivity_module
from ghateh_processor.bootstrap.database_connectivity import (
    probe_database_connectivity,
)
from ghateh_processor.bootstrap.database_runtime import DatabaseRuntime

UNEXPECTED_RESULT_ERROR = "database connectivity probe returned an unexpected result"
DISPOSED_RUNTIME_ERROR = "database runtime is disposed"


class _SentinelError(Exception):
    pass


class _RecordingResult:
    def __init__(
        self,
        scalar_value: object = 1,
        scalar_error: Exception | None = None,
    ) -> None:
        self.scalar_value = scalar_value
        self.scalar_error = scalar_error
        self.scalar_one_calls = 0

    def scalar_one(self) -> object:
        self.scalar_one_calls += 1
        if self.scalar_error is not None:
            raise self.scalar_error
        return self.scalar_value


class _RecordingConnection:
    def __init__(
        self,
        result: _RecordingResult,
        execute_error: Exception | None = None,
    ) -> None:
        self.result = result
        self.execute_error = execute_error
        self.execute_calls: list[tuple[object, object | None]] = []

    def execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> _RecordingResult:
        self.execute_calls.append((statement, parameters))
        if self.execute_error is not None:
            raise self.execute_error
        return self.result


class _RecordingConnectionContext:
    def __init__(
        self,
        connection: _RecordingConnection,
        enter_error: Exception | None = None,
        exit_error: Exception | None = None,
    ) -> None:
        self.connection = connection
        self.enter_error = enter_error
        self.exit_error = exit_error
        self.enter_calls = 0
        self.exit_calls: list[
            tuple[
                type[BaseException] | None,
                BaseException | None,
                TracebackType | None,
            ]
        ] = []

    def __enter__(self) -> Connection:
        self.enter_calls += 1
        if self.enter_error is not None:
            raise self.enter_error
        return cast(Connection, self.connection)

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.exit_calls.append((exception_type, exception, traceback))
        if self.exit_error is not None:
            raise self.exit_error


class _RecordingEngine:
    def __init__(
        self,
        connection_context: _RecordingConnectionContext,
        connect_error: Exception | None = None,
    ) -> None:
        self.connection_context = connection_context
        self.connect_error = connect_error
        self.connect_calls = 0
        self.dispose_calls: list[bool] = []

    def connect(self) -> Connection:
        self.connect_calls += 1
        if self.connect_error is not None:
            raise self.connect_error
        return cast(Connection, self.connection_context)

    def dispose(self, *, close: bool = True) -> None:
        self.dispose_calls.append(close)


def _deny_network(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("database connectivity unit test attempted network access")


@pytest.fixture(autouse=True)
def _deny_unit_test_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)


def _build_runtime(
    *,
    scalar_value: object = 1,
    scalar_error: Exception | None = None,
    execute_error: Exception | None = None,
    enter_error: Exception | None = None,
    exit_error: Exception | None = None,
    connect_error: Exception | None = None,
) -> tuple[
    DatabaseRuntime,
    _RecordingEngine,
    _RecordingConnectionContext,
    _RecordingConnection,
    _RecordingResult,
]:
    result = _RecordingResult(scalar_value, scalar_error)
    connection = _RecordingConnection(result, execute_error)
    connection_context = _RecordingConnectionContext(
        connection,
        enter_error,
        exit_error,
    )
    engine = _RecordingEngine(connection_context, connect_error)
    runtime = DatabaseRuntime(cast(Engine, engine))
    return runtime, engine, connection_context, connection, result


def _assert_runtime_remains_active(
    runtime: DatabaseRuntime,
    engine: _RecordingEngine,
) -> None:
    assert not runtime.is_disposed
    assert runtime.engine is cast(Engine, engine)
    assert engine.dispose_calls == []


def test_successful_probe_uses_one_connection_and_keeps_runtime_active() -> None:
    runtime, engine, context, connection, result = _build_runtime()
    engine_before = runtime.engine

    try:
        probe_with_result = cast(
            Callable[[DatabaseRuntime], object],
            probe_database_connectivity,
        )
        returned_value = probe_with_result(runtime)

        assert returned_value is None
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert len(connection.execute_calls) == 1
        statement, parameters = connection.execute_calls[0]
        assert isinstance(statement, TextClause)
        assert str(statement) == "SELECT 1"
        assert parameters is None
        assert result.scalar_one_calls == 1
        assert len(context.exit_calls) == 1
        assert context.exit_calls[0] == (None, None, None)
        _assert_runtime_remains_active(runtime, engine)
        assert runtime.engine is engine_before
    finally:
        runtime.dispose()

    assert engine.dispose_calls == [True]


@pytest.mark.parametrize(
    "unexpected_result",
    [
        pytest.param(0, id="zero"),
        pytest.param(None, id="none"),
        pytest.param("1", id="string-one"),
        pytest.param(True, id="boolean-true"),
        pytest.param(1.0, id="float-one"),
        pytest.param(Decimal("1"), id="decimal-one"),
    ],
)
def test_unexpected_scalar_result_raises_stable_error_and_leaves_runtime_active(
    unexpected_result: object,
) -> None:
    runtime, engine, context, connection, result = _build_runtime(
        scalar_value=unexpected_result
    )

    try:
        with pytest.raises(RuntimeError) as captured_error:
            probe_database_connectivity(runtime)

        assert str(captured_error.value) == UNEXPECTED_RESULT_ERROR
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert len(context.exit_calls) == 1
        assert context.exit_calls[0] == (None, None, None)
        assert len(connection.execute_calls) == 1
        assert result.scalar_one_calls == 1
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_connect_failure_propagates_without_retry_or_disposal() -> None:
    sentinel = _SentinelError("connect sentinel")
    runtime, engine, context, connection, result = _build_runtime(
        connect_error=sentinel
    )

    try:
        with pytest.raises(_SentinelError) as captured_error:
            probe_database_connectivity(runtime)

        assert captured_error.value is sentinel
        assert engine.connect_calls == 1
        assert context.enter_calls == 0
        assert connection.execute_calls == []
        assert result.scalar_one_calls == 0
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_context_entry_failure_propagates_without_retry_or_disposal() -> None:
    sentinel = _SentinelError("context entry sentinel")
    runtime, engine, context, connection, result = _build_runtime(enter_error=sentinel)

    try:
        with pytest.raises(_SentinelError) as captured_error:
            probe_database_connectivity(runtime)

        assert captured_error.value is sentinel
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert context.exit_calls == []
        assert connection.execute_calls == []
        assert result.scalar_one_calls == 0
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_execute_failure_propagates_without_retry_or_disposal() -> None:
    sentinel = _SentinelError("execute sentinel")
    runtime, engine, context, connection, result = _build_runtime(
        execute_error=sentinel
    )

    try:
        with pytest.raises(_SentinelError) as captured_error:
            probe_database_connectivity(runtime)

        assert captured_error.value is sentinel
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert len(context.exit_calls) == 1
        assert context.exit_calls[0][1] is sentinel
        assert len(connection.execute_calls) == 1
        assert result.scalar_one_calls == 0
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_scalar_failure_propagates_without_retry_or_disposal() -> None:
    sentinel = _SentinelError("scalar sentinel")
    runtime, engine, context, connection, result = _build_runtime(scalar_error=sentinel)

    try:
        with pytest.raises(_SentinelError) as captured_error:
            probe_database_connectivity(runtime)

        assert captured_error.value is sentinel
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert len(context.exit_calls) == 1
        assert context.exit_calls[0][1] is sentinel
        assert len(connection.execute_calls) == 1
        assert result.scalar_one_calls == 1
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_connection_context_exit_failure_propagates_without_retry_or_disposal() -> None:
    sentinel = _SentinelError("context exit sentinel")
    runtime, engine, context, connection, result = _build_runtime(exit_error=sentinel)

    try:
        with pytest.raises(_SentinelError) as captured_error:
            probe_database_connectivity(runtime)

        assert captured_error.value is sentinel
        assert engine.connect_calls == 1
        assert context.enter_calls == 1
        assert len(context.exit_calls) == 1
        assert len(connection.execute_calls) == 1
        assert result.scalar_one_calls == 1
        _assert_runtime_remains_active(runtime, engine)
    finally:
        runtime.dispose()


def test_disposed_runtime_error_propagates_without_connection_or_sql() -> None:
    runtime, engine, context, connection, result = _build_runtime()
    runtime.dispose()

    with pytest.raises(RuntimeError) as captured_error:
        probe_database_connectivity(runtime)

    assert str(captured_error.value) == DISPOSED_RUNTIME_ERROR
    assert engine.connect_calls == 0
    assert context.enter_calls == 0
    assert connection.execute_calls == []
    assert result.scalar_one_calls == 0
    assert engine.dispose_calls == [True]


def test_module_contract_exposes_only_the_connectivity_probe() -> None:
    source = inspect.getsource(connectivity_module)

    assert connectivity_module.__all__ == ("probe_database_connectivity",)
    for forbidden_text in (
        "load_database_settings",
        "resolve_database_url",
        "DatabaseSettings",
        "get_secret_value",
        "make_url",
        "os.environ",
        "os.getenv",
        "create_engine",
        "Session",
        "sessionmaker",
        "sleep",
        "retry",
        "FastAPI",
        "app.state",
        "HTTPException",
        "logging.",
        "logger.",
        "print(",
        "DatabaseRuntime(",
    ):
        assert forbidden_text not in source
    assert not any(
        isinstance(value, (DatabaseRuntime, Engine))
        for value in vars(connectivity_module).values()
    )
