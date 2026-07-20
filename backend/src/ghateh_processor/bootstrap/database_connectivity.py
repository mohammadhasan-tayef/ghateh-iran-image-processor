"""Application-runtime PostgreSQL connectivity probing."""

from sqlalchemy import text

from ghateh_processor.bootstrap.database_runtime import DatabaseRuntime

__all__ = ("probe_database_connectivity",)


def probe_database_connectivity(runtime: DatabaseRuntime) -> None:
    """Verify that the active Runtime Engine can execute the fixed probe."""
    engine = runtime.engine

    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1")).scalar_one()

    if type(result) is not int or result != 1:
        raise RuntimeError("database connectivity probe returned an unexpected result")
