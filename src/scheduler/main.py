"""
GhostAttend — Scheduler Entry Point

APScheduler'ı başlatır ve kullanıcıların derslerini zamanlar.
Docker container olarak ayrı çalışır.
"""

import asyncio

from src.core.config import settings
from src.core.logging import configure_logging, get_logger
from src.scheduler.lesson_scheduler import get_scheduler, schedule_all_courses_for_user

log = get_logger(__name__)


async def init_scheduler():
    """Scheduler'ı başlat ve mevcut kullanıcıları zamanla."""

    scheduler = get_scheduler()

    log.info("scheduler.starting")

    # Mevcut aktif kullanıcıları zamanla
    try:
        from src.db.connection import get_session
        from src.db.repositories.user import UserRepository

        async with get_session() as session:
            user_repo = UserRepository(session)
            active_users = await user_repo.get_active_users()

            for user in active_users:
                try:
                    await schedule_all_courses_for_user(user.id)
                except Exception as e:
                    log.error(
                        "scheduler.user_schedule_failed",
                        user_id=user.id,
                        error=str(e),
                    )

        log.info("scheduler.users_loaded", count=len(active_users))

    except Exception as e:
        log.warning("scheduler.db_not_ready", error=str(e))

    scheduler.start()
    log.info("scheduler.started")

    # Sonsuz bekle
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        log.info("scheduler.stopped")


def main():
    """Scheduler entry point."""
    configure_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)
    log.info("scheduler.init", environment=settings.ENVIRONMENT)
    asyncio.run(init_scheduler())


if __name__ == "__main__":
    main()
