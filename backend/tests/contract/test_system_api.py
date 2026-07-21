"""Contracts for the system API walking skeleton."""

import inspect
from importlib.metadata import version as distribution_version
from typing import Final, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import ghateh_processor.bootstrap.api as api_module
from ghateh_processor.bootstrap.api import create_app
from ghateh_processor.bootstrap.database_lifespan import create_database_lifespan
from ghateh_processor.bootstrap.database_runtime import DatabaseRuntime

DISTRIBUTION_NAME: Final = "ghateh-iran-image-processor"
LIVENESS_PATH: Final = "/api/v1/health/live"


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
        *,
        runtime: _RecordingRuntime | None = None,
        factory_error: Exception | None = None,
    ) -> None:
        self._runtime = runtime
        self.factory_error = factory_error
        self.calls = 0
        self.returned_runtimes: list[_RecordingRuntime] = []

    def __call__(self) -> DatabaseRuntime:
        self.calls += 1
        if self.factory_error is not None:
            raise self.factory_error

        runtime = self._runtime or _RecordingRuntime()
        self.returned_runtimes.append(runtime)
        return cast(DatabaseRuntime, runtime)


def test_create_app_returns_independent_fastapi_instances() -> None:
    """The factory returns a new FastAPI application on every call."""
    first_application = create_app()
    second_application = create_app()

    assert isinstance(first_application, FastAPI)
    assert isinstance(second_application, FastAPI)
    assert first_application is not second_application


def test_liveness_response_contract() -> None:
    """The liveness route exposes only stable process metadata."""
    expected_response = {
        "status": "ok",
        "service": DISTRIBUTION_NAME,
        "version": distribution_version(DISTRIBUTION_NAME),
    }

    with TestClient(create_app()) as client:
        response = client.get(LIVENESS_PATH)

    assert response.status_code == 200
    assert response.headers["content-type"].split(";", maxsplit=1)[0] == (
        "application/json"
    )
    assert response.json() == expected_response


def test_openapi_declares_exact_liveness_schema() -> None:
    """OpenAPI publishes the liveness path without sensitive fields."""
    schema = create_app().openapi()
    operation = schema["paths"][LIVENESS_PATH]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    schema_name = response_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    liveness_schema = schema["components"]["schemas"][schema_name]
    properties = liveness_schema["properties"]

    assert set(properties) == {"status", "service", "version"}
    assert set(liveness_schema["required"]) == {"status", "service", "version"}
    assert liveness_schema["additionalProperties"] is False
    assert properties["status"]["const"] == "ok"
    assert properties["service"]["const"] == DISTRIBUTION_NAME


def test_injected_database_lifespan_is_lazy_during_application_construction() -> None:
    """Application construction passes through without starting the lifespan."""
    runtime = _RecordingRuntime()
    runtime_factory = _RecordingRuntimeFactory(runtime=runtime)
    database_lifespan = create_database_lifespan(runtime_factory)

    application = create_app(lifespan=database_lifespan)

    assert isinstance(application, FastAPI)
    assert runtime_factory.calls == 0
    assert runtime_factory.returned_runtimes == []
    assert runtime.dispose_calls == 0


def test_fastapi_runs_injected_database_lifespan_around_client_context() -> None:
    """FastAPI owns one injected Runtime for the active client lifespan."""
    expected_response = {
        "status": "ok",
        "service": DISTRIBUTION_NAME,
        "version": distribution_version(DISTRIBUTION_NAME),
    }
    runtime_factory = _RecordingRuntimeFactory()
    database_lifespan = create_database_lifespan(runtime_factory)
    application = create_app(lifespan=database_lifespan)

    with TestClient(application) as client:
        assert runtime_factory.calls == 1
        assert len(runtime_factory.returned_runtimes) == 1
        runtime = runtime_factory.returned_runtimes[0]
        assert runtime.dispose_calls == 0

        response = client.get(LIVENESS_PATH)
        assert response.status_code == 200
        assert response.headers["content-type"].split(";", maxsplit=1)[0] == (
            "application/json"
        )
        assert response.json() == expected_response

    assert runtime.dispose_calls == 1
    assert runtime_factory.calls == 1
    assert len(runtime_factory.returned_runtimes) == 1


def test_injected_runtime_factory_failure_propagates_from_client_entry() -> None:
    """FastAPI does not suppress or retry a lifespan startup failure."""
    sentinel = _SentinelFactoryError("factory sentinel")
    runtime = _RecordingRuntime()
    runtime_factory = _RecordingRuntimeFactory(
        runtime=runtime,
        factory_error=sentinel,
    )
    application = create_app(
        lifespan=create_database_lifespan(runtime_factory),
    )
    client_body_entered = False

    with pytest.raises(_SentinelFactoryError) as captured_error:
        with TestClient(application):
            client_body_entered = True

    assert captured_error.value is sentinel
    assert not client_body_entered
    assert runtime_factory.calls == 1
    assert runtime_factory.returned_runtimes == []
    assert runtime.dispose_calls == 0


def test_injected_runtime_disposal_failure_propagates_from_client_exit() -> None:
    """FastAPI does not suppress a lifespan shutdown failure."""
    sentinel = _SentinelDisposalError("disposal sentinel")
    runtime = _RecordingRuntime(disposal_error=sentinel)
    runtime_factory = _RecordingRuntimeFactory(runtime=runtime)
    application = create_app(
        lifespan=create_database_lifespan(runtime_factory),
    )

    with pytest.raises(_SentinelDisposalError) as captured_error:
        with TestClient(application) as client:
            assert runtime_factory.calls == 1
            assert runtime_factory.returned_runtimes == [runtime]
            assert runtime.dispose_calls == 0
            response = client.get(LIVENESS_PATH)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

    assert captured_error.value is sentinel
    assert runtime.dispose_calls == 1
    assert runtime_factory.calls == 1
    assert runtime_factory.returned_runtimes == [runtime]


def test_application_factory_signature_and_source_remain_generic() -> None:
    """The factory exposes only a keyword lifespan injection seam."""
    factory_signature = inspect.signature(create_app)
    parameters = tuple(factory_signature.parameters.values())
    source = inspect.getsource(api_module)

    assert api_module.create_app is create_app
    assert create_app.__name__ == "create_app"
    assert len(parameters) == 1
    assert parameters[0].name == "lifespan"
    assert parameters[0].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[0].default is None
    assert factory_signature.return_annotation is FastAPI
    assert "lifespan=lifespan" in source
    for forbidden_text in (
        "DatabaseRuntime",
        "DatabaseSettings",
        "DatabaseLifespanState",
        "create_database_lifespan",
        "create_database_runtime",
        "load_database_settings",
        "resolve_database_url",
        "probe_database_connectivity",
        "get_secret_value",
        "create_engine",
        "engine.connect",
        "SELECT 1",
        "Session",
        "sessionmaker",
        "os.environ",
        "os.getenv",
        "app.state",
        "application.state",
        "request.state",
    ):
        assert forbidden_text not in source
    assert not any(isinstance(value, FastAPI) for value in vars(api_module).values())
