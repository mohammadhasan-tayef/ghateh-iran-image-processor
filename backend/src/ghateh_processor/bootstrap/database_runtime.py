"""Process-local application runtime database engine ownership.

Each executable process creates its own ``DatabaseRuntime``, and the creating
composition root owns disposal. The Engine is process-local: it must not be
created before process forking and reused across processes, or stored as a
repository-wide singleton.
"""

from types import TracebackType
from typing import Self, final

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from ghateh_processor.bootstrap.database_settings import (
    DatabaseSettings,
    resolve_database_url,
)

__all__ = ("DatabaseRuntime", "create_database_runtime")


@final
class DatabaseRuntime:
    """Own one process-local synchronous SQLAlchemy Engine."""

    def __init__(self, engine: Engine) -> None:
        self._engine: Engine | None = engine

    @property
    def engine(self) -> Engine:
        """Return the active Engine or reject access after disposal."""
        engine = self._engine
        if engine is None:
            raise RuntimeError("database runtime is disposed")
        return engine

    @property
    def is_disposed(self) -> bool:
        """Return whether the owned Engine has been disposed successfully."""
        return self._engine is None

    def dispose(self) -> None:
        """Dispose the owned Engine once and mark the owner disposed."""
        engine = self._engine
        if engine is None:
            return

        engine.dispose(close=True)
        self._engine = None

    def __enter__(self) -> Self:
        """Return this owner for synchronous lifecycle management."""
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Dispose on every context exit without suppressing exceptions."""
        self.dispose()


def create_database_runtime(settings: DatabaseSettings) -> DatabaseRuntime:
    """Create a fresh lazy runtime Engine owner from validated settings."""
    database_url = resolve_database_url(settings)
    engine = create_engine(
        database_url,
        poolclass=QueuePool,
        pool_pre_ping=True,
        echo=False,
        hide_parameters=True,
    )
    return DatabaseRuntime(engine)
