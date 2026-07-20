"""Alembic migration environment for the backend workspace."""

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from ghateh_processor.bootstrap.database_settings import (
    load_database_settings,
    resolve_database_url,
)

target_metadata = None


def run_migrations_offline() -> None:
    """Generate PostgreSQL migration SQL without opening a connection."""
    settings = load_database_settings()
    database_url = resolve_database_url(settings)

    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Execute migrations with a short-lived migration-only engine."""
    settings = load_database_settings()
    database_url = resolve_database_url(settings)
    migration_engine = create_engine(
        database_url,
        poolclass=NullPool,
        echo=False,
    )

    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
            )

            with context.begin_transaction():
                context.run_migrations()
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
