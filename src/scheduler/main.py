"""
GhostAttend — Scheduler Entry Point

APScheduler'ı başlatır ve kullanıcıların derslerini zamanlar.
Docker container olarak ayrı çalışır.
"""

import asyncio

import redis.asyncio as aioredis

from src.core.config import settings
from src.core.logging import configure_logging, get_logger
from src.scheduler.lesson_scheduler import (
    get_scheduler,
    reconcile_jobs_for_user,
    schedule_all_courses_for_user,
)

log = get_logger(__name__)

HEARTBEAT_KEY = "scheduler:heartbeat"

async def init_scheduler():
    """Scheduler'ı başlat ve mevcut kullanıcıları zamanla."""

    scheduler = get_scheduler()

    log.info("scheduler.starting")

    # Jobstore (Redis) ile persistence için scheduler'ı erken başlat.
    # APScheduler bazı jobstore'larda job write/restore işlemlerini start() sonrası kesinleştirir.
    scheduler.start()
    log.info("scheduler.started")

    # Mevcut aktif kullanıcıları zamanla
    try:
        from src.db.connection import get_session
        from src.db.repositories.user import UserRepository

        async with get_session() as session:
            user_repo = UserRepository(session)
            active_users = await user_repo.get_active_users()

            for user in active_users:
                try:
                    # Önce drift temizle, sonra yeniden zamanla (idempotent)
                    await reconcile_jobs_for_user(user.id)
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

    # Sonsuz bekle
    redis_client = None
    try:
        if settings.REDIS_URL:
            redis_client = aioredis.from_url(settings.REDIS_URL)
    except Exception as e:
        log.warning("scheduler.heartbeat_redis_init_failed", error=str(e))

    try:
        while True:
            # Heartbeat (bot /health için)
            if redis_client:
                try:
                    await redis_client.set(
                        HEARTBEAT_KEY,
                        "alive",
                        ex=90,  # 90sn içinde yenilenmezse ölü kabul edilebilir
                    )
                except Exception as e:
                    log.warning("scheduler.heartbeat_write_failed", error=str(e))
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass
        scheduler.shutdown()
        log.info("scheduler.stopped")


def main():
    """Scheduler entry point."""
    configure_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)
    log.info("scheduler.init", environment=settings.ENVIRONMENT)
    asyncio.run(init_scheduler())


if __name__ == "__main__":
    main()
