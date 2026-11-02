from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def normalize_database_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def default_database_url() -> str:
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://controlplane_app:controlplane_app@localhost:5432/controlplane",
    )


def async_engine_from_url(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    raw = url or default_database_url()
    return create_async_engine(normalize_database_url(raw), echo=echo)


def async_session_maker_from_url(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = async_engine_from_url(url)
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
