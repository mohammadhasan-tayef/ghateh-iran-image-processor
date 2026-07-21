"""FastAPI-compatible ownership lifecycle for a DatabaseRuntime."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import TypedDict

from fastapi import FastAPI
from starlette.types import Lifespan

from ghateh_processor.bootstrap.database_runtime import DatabaseRuntime

__all__ = (
    "DatabaseLifespanState",
    "create_database_lifespan",
)


class DatabaseLifespanState(TypedDict):
    """Typed state yielded while one DatabaseRuntime is owned."""

    database_runtime: DatabaseRuntime


def create_database_lifespan(
    runtime_factory: Callable[[], DatabaseRuntime],
) -> Lifespan[FastAPI]:
    """Create a lazy lifespan that owns one Runtime per entry."""

    @asynccontextmanager
    async def lifespan(
        application: FastAPI,
    ) -> AsyncIterator[DatabaseLifespanState]:
        del application
        runtime = runtime_factory()
        try:
            yield {"database_runtime": runtime}
        finally:
            runtime.dispose()

    return lifespan
