from __future__ import annotations

from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import SettingsDB, get_db_settings
from .models import SCHEMA_NAME, Base


def _get_connect_args(use_async_driver: bool) -> dict[str, object]:
    search_path = f"{SCHEMA_NAME},public"
    if use_async_driver:
        return {"server_settings": {"search_path": search_path}}

    return {"options": f"-csearch_path={search_path}"}


def build_connection_url(
    settings: SettingsDB | None = None, use_async_driver: bool = False
) -> str:
    """Build a PostgreSQL connection URL using safely quoted credentials.

    For async engines set ``use_async_driver=True`` to use the ``asyncpg`` driver.
    """

    s = settings or get_db_settings()

    user_q = quote_plus(s.user)
    password_q = quote_plus(s.password)

    scheme = "postgresql+asyncpg" if use_async_driver else "postgresql+psycopg2"

    return f"{scheme}://{user_q}:{password_q}@{s.server}:{s.port}/{s.database}"


def get_engine(echo: bool = False) -> Engine:
    """Create a synchronous SQLAlchemy engine."""

    return create_engine(
        build_connection_url(),
        echo=echo,
        future=True,
        connect_args=_get_connect_args(use_async_driver=False),
    )


def get_async_engine(echo: bool = False) -> AsyncEngine:
    """Create an asynchronous SQLAlchemy engine using an asyncio-compatible driver."""

    return create_async_engine(
        build_connection_url(use_async_driver=True),
        echo=echo,
        future=True,
        connect_args=_get_connect_args(use_async_driver=True),
    )


def get_async_sessionmaker(echo: bool = False) -> async_sessionmaker[AsyncSession]:
    """Return an async sessionmaker bound to a fresh async engine."""

    engine = get_async_engine(echo=echo)
    return async_sessionmaker(engine, expire_on_commit=False)


async def create_tables_async(engine: AsyncEngine | None = None) -> None:
    """Create tables asynchronously if they do not exist."""

    engine = engine or get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def create_tables(engine: Engine | None = None) -> None:
    """Create tables synchronously if they do not exist."""

    engine = engine or get_engine()
    with engine.begin() as conn:
        Base.metadata.create_all(conn)


__all__ = [
    "build_connection_url",
    "get_engine",
    "get_async_engine",
    "get_async_sessionmaker",
    "create_tables",
    "create_tables_async",
]
