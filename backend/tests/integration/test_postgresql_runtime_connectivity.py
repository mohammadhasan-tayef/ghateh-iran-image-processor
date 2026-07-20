"""Verify the Runtime Engine connectivity probe against disposable PostgreSQL."""

import os
from collections.abc import Callable
from typing import Final, cast

import pytest
from sqlalchemy.engine import URL

from ghateh_processor.bootstrap.database_connectivity import (
    probe_database_connectivity,
)
from ghateh_processor.bootstrap.database_runtime import (
    DatabaseRuntime,
    create_database_runtime,
)
from ghateh_processor.bootstrap.database_settings import load_database_settings

pytestmark = pytest.mark.postgresql_integration

OPT_IN_VARIABLE: Final = "GHATEH_RUN_POSTGRESQL_INTEGRATION"
DISPOSABLE_USERNAME: Final = "ghateh_ci"
DISPOSABLE_DATABASE: Final = "ghateh_processor_ci"
SUPPORTED_DRIVER: Final = "postgresql+psycopg"
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1"})


def _require_disposable_target(database_url: URL) -> None:
    violations: list[str] = []

    if database_url.drivername != SUPPORTED_DRIVER:
        violations.append("driver is not postgresql+psycopg")
    if database_url.username != DISPOSABLE_USERNAME:
        violations.append("username is not the dedicated integration user")
    if database_url.database != DISPOSABLE_DATABASE:
        violations.append("database is not the dedicated integration database")
    if database_url.host not in LOOPBACK_HOSTS:
        violations.append("host is not an explicit approved loopback IP")
    if database_url.port is None or not 1 <= database_url.port <= 65535:
        violations.append("port is not explicit and valid")
    if database_url.query:
        violations.append("URL query parameters are present")

    if violations:
        pytest.fail(
            "Refusing Runtime PostgreSQL integration target: " + "; ".join(violations),
            pytrace=False,
        )


def test_postgresql_runtime_connectivity() -> None:
    if os.environ.get(OPT_IN_VARIABLE) != "1":
        pytest.skip("requires explicit approval for disposable PostgreSQL")

    settings = load_database_settings()
    runtime = create_database_runtime(settings)

    try:
        assert not runtime.is_disposed
        engine_before = runtime.engine
        assert engine_before.url.drivername == SUPPORTED_DRIVER
        _require_disposable_target(engine_before.url)

        probe_with_result = cast(
            Callable[[DatabaseRuntime], object],
            probe_database_connectivity,
        )
        assert probe_with_result(runtime) is None
        assert not runtime.is_disposed
        assert runtime.engine is engine_before
    finally:
        runtime.dispose()

    assert runtime.is_disposed
