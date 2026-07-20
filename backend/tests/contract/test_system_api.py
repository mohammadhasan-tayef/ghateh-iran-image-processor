"""Contracts for the system API walking skeleton."""

from importlib.metadata import version as distribution_version
from typing import Final

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ghateh_processor.bootstrap.api import create_app

DISTRIBUTION_NAME: Final = "ghateh-iran-image-processor"
LIVENESS_PATH: Final = "/api/v1/health/live"


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
