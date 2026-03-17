"""
GhostAttend — Celery Tasks

Celery task tanımları: ders katılımı, cookie bakımı, sağlık kontrolü.
Her task asenkron olarak çalıştırılır ve sonuçlarını Redis'e yazar.
architecture.md Section 11.2
"""

import asyncio
import uuid
from datetime import datetime, timezone

from src.scheduler.celery_app import celery_app

from src.core.logging import get_logger

log = get_logger(__name__)


def _run_async(coro):
    """Senkron Celery worker'da async fonksiyon çalıştır."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@celery_app.task(
    name="src.scheduler.tasks.attend_lesson_task",
    bind=True,
    max_retries=0,  # Retry mantığı orchestrator'da
    soft_time_limit=3600,
    time_limit=3900,
)
def attend_lesson_task(
    self,
    user_id: int,
    course_id: str,
    course_name: str,
    dys_url: str,
    end_time: str,
    direct_url: str | None = None,
    dys_search_hint: str | None = None,
):
    """
    Bir derse otonom katılım Celery task'ı.
    SessionOrchestrator'ı çalıştırır.
    """
    session_id = str(uuid.uuid4())

    log.info(
        "task.attend_lesson",
        task_id=self.request.id,
        session_id=session_id,
        user_id=user_id,
        course=course_name,
    )

    async def _run():
        import redis.asyncio as aioredis

        from src.agent.orchestrator import SessionOrchestrator
        from src.core.config import settings
        from src.db.connection import get_session
        from src.db.repositories.session import SessionRepository
        from src.notifications.service import NotificationService
        from src.security.encryption import CredentialVault
        from src.security.vault import VaultService

        # Bağlantılar
        redis_client = aioredis.from_url(settings.REDIS_URL)

        async with get_session() as db_session:
            # Vault oluştur
            vault = CredentialVault(settings.MASTER_ENCRYPTION_KEY)
            vault_service = VaultService(db_session, vault)

            # Notification servisi
            notifier = NotificationService(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
            )

            # DB session kaydı oluştur (tek source of truth)
            session_repo = SessionRepository(db_session)
            agent_session = await session_repo.create(
                user_id=user_id,
                course_id=uuid.UUID(course_id),
            )
            log.info(
                "task.session_created",
                task_id=self.request.id,
                agent_session_id=str(agent_session.id),
                user_id=user_id,
                course=course_name,
            )

            # Orchestrator
            orchestrator = SessionOrchestrator(
                user_id=user_id,
                session_id=str(agent_session.id),
                redis_client=redis_client,
                notifier=notifier,
                vault=vault_service,
                session_repo=session_repo,
            )

            # Çalıştır
            result = await orchestrator.attend_lesson(
                course_name=course_name,
                dys_url=dys_url,
                end_time=end_time,
                direct_url=direct_url,
                dys_search_hint=dys_search_hint,
            )

            await db_session.commit()

        await redis_client.close()
        return result

    try:
        result = _run_async(_run())
        log.info(
            "task.attend_lesson_complete",
            task_id=self.request.id,
            status=result.get("status"),
        )
        return result
    except Exception as e:
        log.error(
            "task.attend_lesson_failed",
            task_id=self.request.id,
            error=str(e),
        )
        return {"status": "error", "error": str(e)}


@celery_app.task(name="src.scheduler.tasks.check_cookie_expiry_task")
def check_cookie_expiry_task():
    """
    Günlük cookie expire kontrolü.
    Expire olacak cookie'leri tespit edip kullanıcıya bildirim gönderir.
    """
    log.info("task.check_cookie_expiry")

    async def _run():
        from src.core.config import settings
        from src.db.connection import get_session
        from src.notifications.service import NotificationService
        from src.security.encryption import CredentialVault
        from src.security.vault import VaultService

        async with get_session() as db_session:
            vault = CredentialVault(settings.MASTER_ENCRYPTION_KEY)
            vault_service = VaultService(db_session, vault)

            expiring = await vault_service.get_expiring_credentials(days_ahead=7)

            notifier = NotificationService(bot_token=settings.TELEGRAM_BOT_TOKEN)

            for cred in expiring:
                await notifier.send_message(
                    user_id=cred.user_id,
                    text=(
                        "⚠️ Oturum bilgilerin yakında expire olacak.\n"
                        "Sonraki derslerde yeniden giriş yapılacak.\n"
                        "Sorunsuz devam etmesi için /reauth ile güncelle."
                    ),
                )

            log.info("task.cookie_expiry_checked", expiring_count=len(expiring))

    _run_async(_run())


@celery_app.task(name="src.scheduler.tasks.health_check_task")
def health_check_task():
    """
    Periyodik sağlık kontrolü.
    Redis, DB ve Telegram bağlantılarını test eder.
    """
    log.info("task.health_check")

    async def _run():
        import redis.asyncio as aioredis

        from src.core.config import settings

        checks = {"redis": False, "timestamp": datetime.now(timezone.utc).isoformat()}

        # Redis check
        try:
            redis_client = aioredis.from_url(settings.REDIS_URL)
            await redis_client.ping()
            checks["redis"] = True
            await redis_client.close()
        except Exception as e:
            checks["redis_error"] = str(e)

        log.info("task.health_check_result", **checks)
        return checks

    return _run_async(_run())
