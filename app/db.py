from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .settings import get_settings

_engine = None
_sessions = None


def session_factory():
    global _engine, _sessions
    if _sessions is not None:
        return _sessions
    url = get_settings().database_url
    if not url:
        return None
    _engine = create_async_engine(url, pool_pre_ping=True)
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessions


async def get_db() -> AsyncIterator[AsyncSession]:
    factory = session_factory()
    if factory is None:
        raise HTTPException(503, "DATABASE_URL이 설정되지 않았습니다.")
    async with factory() as session:
        yield session


async def close_db() -> None:
    global _engine, _sessions
    if _engine is not None:
        await _engine.dispose()
    _engine = _sessions = None
