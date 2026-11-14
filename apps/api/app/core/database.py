from __future__ import annotations

from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from packages.common.config import get_settings


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine(database_url: str | None = None) -> AsyncEngine:
    global _engine
    if database_url is not None:
        return create_async_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.async_database_url,
            pool_pre_ping=True,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


def reset_db_engine(database_url: str | None = None) -> None:
    """Allow test suites to point the session factory at an isolated test database."""
    global _engine, _session_factory
    _engine = get_engine(database_url) if database_url else None
    _session_factory = (
        async_sessionmaker(bind=_engine, expire_on_commit=False, class_=AsyncSession)
        if _engine
        else None
    )


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
