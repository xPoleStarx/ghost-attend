"""
GhostAttend — SQLAlchemy Async Database Connection

Async engine + session factory yönetimi.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import settings

# Async engine oluştur
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.is_development,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency veya genel kullanım için async session üreteci."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Veritabanı bağlantısını test et."""
    async with engine.begin() as conn:
        # Connection test
        await conn.execute(
            __import__("sqlalchemy").text("SELECT 1")
        )


async def close_db() -> None:
    """Engine'i kapat (uygulama kapanırken çağrılır)."""
    await engine.dispose()
