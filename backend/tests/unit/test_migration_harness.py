"""Tests for the Alembic migration harness and empty baseline."""

import inspect
import socket
from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import NoReturn

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import Script, ScriptDirectory
from pydantic import ValidationError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_CONFIGURATION = BACKEND_ROOT / "alembic.ini"
MIGRATIONS_DIRECTORY = BACKEND_ROOT / "migrations"
BASELINE_REVISION = "0001_empty_baseline"
DATABASE_URL_ENVIRONMENT_VARIABLE = "GHATEH_DATABASE_URL"
UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE = "DATABASE_URL"
FAKE_PASSWORD = "clearly_fake_migration_password"
FAKE_HOSTNAME = "offline.invalid"
FAKE_DATABASE_URL = (
    f"postgresql+psycopg://migration_user:{FAKE_PASSWORD}@{FAKE_HOSTNAME}:5432/"
    "ghateh_processor"
)
APPLICATION_TABLE_NAMES = {
    "batch_images",
    "batches",
    "candidate_versions",
    "export_items",
    "export_jobs",
    "idempotency_records",
    "image_assets",
    "model_installations",
    "model_registry_entries",
    "outbox_messages",
    "preset_revisions",
    "presets",
    "processing_events",
    "processing_runs",
    "review_decisions",
    "source_observations",
    "source_preview_artifacts",
    "storage_roots",
    "user_sessions",
    "users",
}


def _clear_database_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)
    monkeypatch.delenv(UNPREFIXED_DATABASE_URL_ENVIRONMENT_VARIABLE, raising=False)


def _configuration(*, output_buffer: StringIO | None = None) -> Config:
    return Config(
        str(ALEMBIC_CONFIGURATION),
        stdout=StringIO(),
        output_buffer=output_buffer,
    )


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(_configuration())


def _baseline_script() -> Script:
    revision = _script_directory().get_revision(BASELINE_REVISION)
    assert revision is not None
    return revision


def _deny_network(*args: object, **kwargs: object) -> NoReturn:
    raise AssertionError("offline migration attempted network access")


def test_alembic_configuration_is_minimal_and_secret_free() -> None:
    assert ALEMBIC_CONFIGURATION.is_file()

    configuration = _configuration()
    script_location = configuration.get_main_option("script_location")
    configuration_text = ALEMBIC_CONFIGURATION.read_text(encoding="utf-8")
    normalized_configuration = configuration_text.casefold()

    assert configuration.file_config.sections() == ["alembic"]
    assert script_location is not None
    assert Path(script_location).resolve() == MIGRATIONS_DIRECTORY.resolve()
    assert configuration.get_main_option("version_locations") is None
    assert "sqlalchemy.url" not in normalized_configuration
    assert "://" not in normalized_configuration
    assert "password" not in normalized_configuration
    assert "credential" not in normalized_configuration
    assert "prepend_sys_path" not in normalized_configuration


def test_script_tree_has_one_linear_empty_baseline() -> None:
    script_directory = _script_directory()
    revisions = list(script_directory.walk_revisions(base="base", head="heads"))
    baseline = _baseline_script()

    assert [revision.revision for revision in revisions] == [BASELINE_REVISION]
    assert script_directory.get_heads() == [BASELINE_REVISION]
    assert script_directory.get_bases() == [BASELINE_REVISION]
    assert baseline.revision == BASELINE_REVISION
    assert baseline.down_revision is None
    assert not baseline.branch_labels
    assert not baseline.dependencies


def test_empty_baseline_upgrade_and_downgrade_are_intentional_no_ops() -> None:
    baseline = _baseline_script()
    baseline_module = baseline.module
    source = inspect.getsource(baseline_module)
    normalized_source = source.casefold()

    assert baseline_module.upgrade() is None
    assert baseline_module.downgrade() is None
    assert "from alembic" not in normalized_source
    assert "import alembic" not in normalized_source
    assert "sqlalchemy" not in normalized_source
    assert "op." not in normalized_source
    assert "create_table" not in normalized_source
    assert "create_schema" not in normalized_source
    assert "create_index" not in normalized_source
    assert "create_constraint" not in normalized_source
    assert not any(
        table_name in normalized_source for table_name in APPLICATION_TABLE_NAMES
    )


def test_offline_upgrade_generates_secret_safe_postgresql_sql_without_network(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_database_environment(monkeypatch)
    monkeypatch.setenv(DATABASE_URL_ENVIRONMENT_VARIABLE, FAKE_DATABASE_URL)
    monkeypatch.setattr(socket, "socket", _deny_network)
    monkeypatch.setattr(socket, "create_connection", _deny_network)
    monkeypatch.setattr(socket, "getaddrinfo", _deny_network)
    sql_output = StringIO()
    configuration = _configuration(output_buffer=sql_output)

    command.upgrade(configuration, "head", sql=True)

    captured = capsys.readouterr()
    generated_sql = sql_output.getvalue()
    combined_output = generated_sql + captured.out + captured.err
    assert "CREATE TABLE alembic_version" in generated_sql
    assert BASELINE_REVISION in generated_sql
    assert "INSERT INTO alembic_version" in generated_sql
    assert not any(
        f"CREATE TABLE {table_name}" in generated_sql
        for table_name in APPLICATION_TABLE_NAMES
    )
    assert FAKE_PASSWORD not in combined_output
    assert FAKE_HOSTNAME not in combined_output


def test_offline_upgrade_without_database_url_fails_through_typed_settings(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_database_environment(monkeypatch)

    with pytest.raises(ValidationError) as error:
        command.upgrade(_configuration(output_buffer=StringIO()), "head", sql=True)

    captured = capsys.readouterr()
    combined_output = str(error.value) + captured.out + captured.err
    assert "database_url" in combined_output.casefold()
    assert "field required" in combined_output.casefold()
    assert FAKE_PASSWORD not in combined_output


def test_invalid_database_url_is_redacted_during_offline_upgrade(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _clear_database_environment(monkeypatch)
    fake_query_secret = "clearly_fake_query_secret"
    monkeypatch.setenv(
        DATABASE_URL_ENVIRONMENT_VARIABLE,
        f"{FAKE_DATABASE_URL}?password={fake_query_secret}",
    )

    with pytest.raises(ValidationError) as error:
        command.upgrade(_configuration(output_buffer=StringIO()), "head", sql=True)

    captured = capsys.readouterr()
    combined_output = str(error.value) + captured.out + captured.err
    assert "database URL query parameters are not supported" in combined_output
    assert FAKE_PASSWORD not in combined_output
    assert fake_query_secret not in combined_output


@pytest.mark.parametrize(
    "alembic_command",
    [
        pytest.param(command.heads, id="heads"),
        pytest.param(command.history, id="history"),
    ],
)
def test_script_only_commands_work_without_database_configuration(
    monkeypatch: pytest.MonkeyPatch,
    alembic_command: Callable[[Config], None],
) -> None:
    _clear_database_environment(monkeypatch)
    output = StringIO()
    configuration = Config(str(ALEMBIC_CONFIGURATION), stdout=output)

    alembic_command(configuration)

    command_output = output.getvalue()
    assert BASELINE_REVISION in command_output
    assert FAKE_PASSWORD not in command_output
    assert FAKE_HOSTNAME not in command_output
