"""Pytest test session configuration and database isolation fixtures."""

import asyncio
import os
from pathlib import Path
import sys
from typing import AsyncGenerator

# Ensure workspace root and backend directory are always resolvable in sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BACKEND_ROOT = _PROJECT_ROOT / "backend"
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.deps import get_db

from app.core.config import settings
from app.db.base import Base
from app.main import app

TEST_DB_FILE = Path(__file__).resolve().parent / "test_suite.db"
TEST_DB_URL = f"sqlite+aiosqlite:///{TEST_DB_FILE}"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

test_session_maker = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency override providing test database sessions."""
    async with test_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure a clean, isolated database for the entire test session."""
    settings.DATABASE_URL = TEST_DB_URL

    import app.db.session as session_mod
    session_mod.engine = test_engine
    session_mod.async_session_maker = test_session_maker

    if TEST_DB_FILE.exists():
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass

    async def _init_tables():
        import app.models  # noqa: F401
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)


    asyncio.run(_init_tables())

    app.dependency_overrides[get_db] = override_get_db

    yield

    app.dependency_overrides.clear()

    async def _dispose():
        await test_engine.dispose()

    asyncio.run(_dispose())

    if TEST_DB_FILE.exists():
        try:
            os.remove(TEST_DB_FILE)
        except Exception:
            pass
