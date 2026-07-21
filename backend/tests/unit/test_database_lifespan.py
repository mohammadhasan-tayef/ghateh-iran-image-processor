"""Unit tests for DatabaseRuntime lifespan ownership."""

import asyncio
import inspect
import socket
from collections.abc import Coroutine
from typing import NoReturn, cast

import pytest
from fastapi import FastAPI

import ghateh_processor.bootstrap.database_lifespan as lifespan_module
from ghateh_processor.bootstrap.database_lifespan import (
    DatabaseLifespanState,
    create_database_lifespan,
)
from ghateh_processor.bootstrap.database_runtime import DatabaseRuntime


class _SentinelBodyError(Exception):
    pass


class _SentinelFactoryError(Exception):
    pass


class _SentinelDisposalError(Exception):
    pass


class _RecordingRuntime:
    def __init__(self, disposal_error: Exception | None = None) -> None:
        self.dispose_calls = 0
        self.disposal_error = disposal_error

    def dispose(self) -> None:
        self.dispose_calls += 1
        if self.disposal_error is not None:
            raise self.disposal_error


class _RecordingRuntimeFactory:
    def __init__(
        self,
        supplied_runtimes: list[_RecordingRuntime] | None = None,
        factory_error: Exception | None = None,
    ) -> None:
        self._supplied_runtimes = list(supplied_runtimes or [])
        self.factory_error = factory_error
        self.calls = 0
        self.returned_runtimes: list[_RecordingRuntime] = []

    def __call__(self) -> DatabaseRuntime:
        self.calls += 1
        if self.factory_error is not None:
            raise self.factory_error

        if self._supplied_runtimes:
            runtime = self._supplied_runtimes.pop(0)
        else:
            runtime = _RecordingRuntime()
        self.returned_runtimes.append(runtime)
        return cast(DatabaseRuntime, runtime)


def _deny_network(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("database lifespan unit test attempted network access")


def _apply_network_denial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)


async def _await_with_network_denied(
    scenario: Coroutine[object, object, None],
) -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        _apply_network_denial(monkeypatch)
        await scenario


def _run_with_network_denied(
    scenario: Coroutine[object, object, None],
) -> None:
    asyncio.run(_await_with_network_denied(scenario))


def test_lifespan_constructor_is_lazy() -> None:
    factory = _RecordingRuntimeFactory()

    with pytest.MonkeyPatch.context() as monkeypatch:
        _apply_network_denial(monkeypatch)
        lifespan = create_database_lifespan(factory)

    assert callable(lifespan)
    assert factory.calls == 0
    assert factory.returned_runtimes == []


def test_successful_entry_yields_typed_state_and_exit_disposes_once() -> None:
    factory = _RecordingRuntimeFactory()
    lifespan = create_database_lifespan(factory)

    async def scenario() -> None:
        async with lifespan(FastAPI()) as raw_state:
            assert isinstance(raw_state, dict)
            state = cast(DatabaseLifespanState, raw_state)
            assert factory.calls == 1
            assert len(factory.returned_runtimes) == 1
            runtime = factory.returned_runtimes[0]
            assert set(state) == {"database_runtime"}
            assert state["database_runtime"] is cast(DatabaseRuntime, runtime)
            assert runtime.dispose_calls == 0

        assert runtime.dispose_calls == 1

    _run_with_network_denied(scenario())


def test_each_entry_creates_and_disposes_a_fresh_runtime() -> None:
    factory = _RecordingRuntimeFactory()
    lifespan = create_database_lifespan(factory)

    async def scenario() -> None:
        async with lifespan(FastAPI()) as first_raw_state:
            first_state = cast(DatabaseLifespanState, first_raw_state)
            first_runtime = factory.returned_runtimes[0]
            assert first_state["database_runtime"] is cast(
                DatabaseRuntime,
                first_runtime,
            )
            assert first_runtime.dispose_calls == 0

        assert first_runtime.dispose_calls == 1

        async with lifespan(FastAPI()) as second_raw_state:
            second_state = cast(DatabaseLifespanState, second_raw_state)
            second_runtime = factory.returned_runtimes[1]
            assert second_state["database_runtime"] is cast(
                DatabaseRuntime,
                second_runtime,
            )
            assert second_runtime is not first_runtime
            assert second_runtime.dispose_calls == 0

        assert second_runtime.dispose_calls == 1

    _run_with_network_denied(scenario())
    assert factory.calls == 2
    assert len(factory.returned_runtimes) == 2


def test_body_failure_disposes_once_and_propagates_original_exception() -> None:
    factory = _RecordingRuntimeFactory()
    lifespan = create_database_lifespan(factory)
    sentinel = _SentinelBodyError("body sentinel")

    async def scenario() -> None:
        async with lifespan(FastAPI()):
            raise sentinel

    with pytest.raises(_SentinelBodyError) as captured_error:
        _run_with_network_denied(scenario())

    assert captured_error.value is sentinel
    assert factory.calls == 1
    assert len(factory.returned_runtimes) == 1
    assert factory.returned_runtimes[0].dispose_calls == 1


def test_factory_failure_propagates_without_state_disposal_or_retry() -> None:
    sentinel = _SentinelFactoryError("factory sentinel")
    factory = _RecordingRuntimeFactory(factory_error=sentinel)
    lifespan = create_database_lifespan(factory)
    state_was_yielded = False

    async def scenario() -> None:
        nonlocal state_was_yielded
        async with lifespan(FastAPI()):
            state_was_yielded = True

    with pytest.raises(_SentinelFactoryError) as captured_error:
        _run_with_network_denied(scenario())

    assert captured_error.value is sentinel
    assert not state_was_yielded
    assert factory.calls == 1
    assert factory.returned_runtimes == []


def test_disposal_failure_propagates_without_second_disposal() -> None:
    sentinel = _SentinelDisposalError("disposal sentinel")
    runtime = _RecordingRuntime(disposal_error=sentinel)
    factory = _RecordingRuntimeFactory(supplied_runtimes=[runtime])
    lifespan = create_database_lifespan(factory)
    state_was_yielded = False

    async def scenario() -> None:
        nonlocal state_was_yielded
        async with lifespan(FastAPI()):
            state_was_yielded = True

    with pytest.raises(_SentinelDisposalError) as captured_error:
        _run_with_network_denied(scenario())

    assert captured_error.value is sentinel
    assert state_was_yielded
    assert factory.calls == 1
    assert runtime.dispose_calls == 1


def test_module_contract_exposes_only_state_and_lifespan_constructor() -> None:
    source = inspect.getsource(lifespan_module)

    assert lifespan_module.__all__ == (
        "DatabaseLifespanState",
        "create_database_lifespan",
    )
    assert DatabaseLifespanState.__required_keys__ == frozenset({"database_runtime"})
    assert DatabaseLifespanState.__optional_keys__ == frozenset()
    for forbidden_text in (
        "DatabaseSettings",
        "load_database_settings",
        "resolve_database_url",
        "create_database_runtime",
        "probe_database_connectivity",
        "get_secret_value",
        "make_url",
        "os.environ",
        "os.getenv",
        "create_engine",
        "engine.connect",
        "SELECT 1",
        "Session",
        "sessionmaker",
        "FastAPI(",
        "app.state",
        "request.state",
        "logging.",
        "logger.",
        "print(",
        "DatabaseRuntime(",
    ):
        assert forbidden_text not in source
    assert not any(
        isinstance(value, DatabaseRuntime) for value in vars(lifespan_module).values()
    )
