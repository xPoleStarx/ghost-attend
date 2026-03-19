from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.telemetry.logging import get_logger


async def wait_for_database(settings: Settings, retries: int = 30, delay_seconds: int = 2) -> None:
    log = get_logger(component="bootstrap.db_wait")
    engine = create_async_engine(settings.database_url, future=True)
    try:
        for attempt in range(1, retries + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                log.info("bootstrap.db_ready", attempt=attempt)
                return
            except Exception as exc:  # noqa: BLE001
                log.info("bootstrap.db_retry", attempt=attempt, error=str(exc))
                await asyncio.sleep(delay_seconds)
        msg = "Database did not become ready in time."
        raise RuntimeError(msg)
    finally:
        await engine.dispose()


def run_migrations() -> None:
    config = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    command.upgrade(config, "head")
