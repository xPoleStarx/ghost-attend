from __future__ import annotations

import asyncio

from app.app import GhostAttendApplication
from app.bootstrap import run_migrations, wait_for_database
from app.config import get_settings
from app.telemetry.logging import configure_logging, get_logger


async def run(settings) -> None:
    application = GhostAttendApplication.build(settings)
    startup_state = await application.startup()
    log = get_logger(component="runtime_cli")
    telegram_app = application.telegram_service.build()
    if telegram_app is None:
        log.info(
            "runtime.standby_mode",
            reason="missing token or telegram dependency",
            **startup_state,
        )
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await application.shutdown()
        return
    log.info("runtime.telegram_ready", **startup_state)
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()  # type: ignore[union-attr]
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await telegram_app.updater.stop()  # type: ignore[union-attr]
        await telegram_app.stop()
        await telegram_app.shutdown()
        await application.shutdown()


def main() -> None:
    configure_logging()
    settings = get_settings()
    asyncio.run(wait_for_database(settings))
    run_migrations()
    asyncio.run(run(settings))
