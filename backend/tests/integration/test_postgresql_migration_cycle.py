"""Verify the complete Alembic cycle against disposable PostgreSQL."""

import hashlib
import os
from pathlib import Path
from typing import Final

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.pool import NullPool

from ghateh_processor.bootstrap.database_settings import (
    load_database_settings,
    resolve_database_url,
)

pytestmark = pytest.mark.postgresql_integration

BACKEND_ROOT: Final = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIGURATION: Final = BACKEND_ROOT / "alembic.ini"
BASELINE_REVISION: Final = "0001_empty_baseline"
OPT_IN_VARIABLE: Final = "GHATEH_RUN_POSTGRESQL_INTEGRATION"
DISPOSABLE_USERNAME: Final = "ghateh_ci"
DISPOSABLE_DATABASE: Final = "ghateh_processor_ci"
SUPPORTED_DRIVER: Final = "postgresql+psycopg"
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "::1"})
MIGRATION_SOURCE_FILES: Final = (
    ALEMBIC_CONFIGURATION,
    BACKEND_ROOT / "migrations" / "env.py",
    BACKEND_ROOT / "migrations" / "script.py.mako",
    BACKEND_ROOT / "migrations" / "versions" / "0001_empty_baseline.py",
)


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
            "Refusing PostgreSQL migration integration target: "
            + "; ".join(violations),
            pytrace=False,
        )


def _configuration() -> Config:
    return Config(str(ALEMBIC_CONFIGURATION))


def _migration_source_hashes() -> dict[Path, str]:
    return {
        source_file: hashlib.sha256(source_file.read_bytes()).hexdigest()
        for source_file in MIGRATION_SOURCE_FILES
    }


def _public_tables(connection: Connection) -> set[str]:
    table_names = connection.execute(
        text(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
    ).scalars()
    return {str(table_name) for table_name in table_names}


def _schema_names(connection: Connection) -> set[str]:
    schema_names = connection.execute(
        text(
            """
            SELECT schema_name
            FROM information_schema.schemata
            ORDER BY schema_name
            """
        )
    ).scalars()
    return {str(schema_name) for schema_name in schema_names}


def _revision_rows(connection: Connection) -> list[str]:
    if "alembic_version" not in _public_tables(connection):
        return []

    revisions = connection.execute(
        text(
            """
            SELECT version_num
            FROM public.alembic_version
            ORDER BY version_num
            """
        )
    ).scalars()
    return [str(revision) for revision in revisions]


def _assert_empty_baseline(connection: Connection) -> None:
    assert _public_tables(connection) == {"alembic_version"}
    assert _revision_rows(connection) == [BASELINE_REVISION]


def test_postgresql_migration_cycle() -> None:
    if os.environ.get(OPT_IN_VARIABLE) != "1":
        pytest.skip("requires explicit approval for disposable PostgreSQL")

    settings = load_database_settings()
    database_url = resolve_database_url(settings)
    _require_disposable_target(database_url)

    source_hashes_before = _migration_source_hashes()
    alembic_configuration = _configuration()
    script_directory = ScriptDirectory.from_config(alembic_configuration)
    assert script_directory.get_heads() == [BASELINE_REVISION]

    inspection_engine = create_engine(
        database_url,
        poolclass=NullPool,
        echo=False,
    )
    inspection_pool = inspection_engine.pool

    try:
        with inspection_engine.connect() as connection:
            server_version_number = int(
                str(
                    connection.execute(
                        text("SELECT current_setting('server_version_num')")
                    ).scalar_one()
                )
            )
            assert server_version_number // 10000 == 17
            assert (
                connection.execute(text("SELECT current_database()")).scalar_one()
                == DISPOSABLE_DATABASE
            )
            assert (
                connection.execute(text("SELECT current_user")).scalar_one()
                == DISPOSABLE_USERNAME
            )
            assert _public_tables(connection) == set()
            initial_schema_names = _schema_names(connection)

        command.upgrade(alembic_configuration, "head")

        with inspection_engine.connect() as connection:
            _assert_empty_baseline(connection)

        command.downgrade(alembic_configuration, "base")

        with inspection_engine.connect() as connection:
            assert _revision_rows(connection) == []
            assert _public_tables(connection) <= {"alembic_version"}

        command.upgrade(alembic_configuration, "head")

        with inspection_engine.connect() as connection:
            _assert_empty_baseline(connection)
            assert _schema_names(connection) == initial_schema_names

        assert ScriptDirectory.from_config(alembic_configuration).get_heads() == [
            BASELINE_REVISION
        ]
        assert _migration_source_hashes() == source_hashes_before
    finally:
        inspection_engine.dispose()

    assert inspection_engine.pool is not inspection_pool
