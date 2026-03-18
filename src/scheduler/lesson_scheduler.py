"""
GhostAttend — Ders Zamanlayıcı

APScheduler ile derslerin otomatik zamanlanması.
Her kullanıcının derslerini DB'den okur ve 5dk önce
Celery task'ı olarak kuyruğa ekler.
architecture.md Section 11.3
"""

import asyncio
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlparse

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.triggers.cron import CronTrigger

from src.core.config import settings
from src.core.constants import DAYS_TR
from src.core.logging import get_logger

log = get_logger(__name__)

# Celery app'i import ederek scheduler process'inde de default/current set edilmesini garanti et.
# Bu sayede burada yapılan `attend_lesson_task.delay(...)` publish'i Redis broker'a gider.
# Test ortamlarında celery dependency kurulmamış olabilir; bu durumda import'u yumuşat.
try:
    import src.scheduler.celery_app  # noqa: F401
except ModuleNotFoundError:
    log.warning("scheduler.celery_not_available")

# APScheduler persistence — Redis job store
_scheduler: AsyncIOScheduler | None = None


def _redis_conn_from_settings() -> tuple[str, int, str | None]:
    """
    APScheduler RedisJobStore için bağlantı parametrelerini döndür.

    Not:
    - Celery tarafı `settings.REDIS_URL` kullanıyor.
    - Scheduler tarafında host/port/password alanları ayrı tutulmuş.
    Bu fonksiyon, mümkünse `REDIS_URL`'ı source of truth kabul ederek drift'i engeller.
    """
    if settings.REDIS_URL:
        parsed = urlparse(settings.REDIS_URL)
        if parsed.hostname:
            host = parsed.hostname
            port = parsed.port or 6379
            password = parsed.password
            return host, port, password
    return settings.REDIS_HOST, settings.REDIS_PORT, (settings.REDIS_PASSWORD or None)


def get_scheduler() -> AsyncIOScheduler:
    """Singleton scheduler instance döndür."""
    global _scheduler
    if _scheduler is None:
        host, port, password = _redis_conn_from_settings()
        jobstores = {
            "default": RedisJobStore(
                host=host,
                port=port,
                password=password,
                db=1,  # Ana Redis DB'den ayrı
            ),
        }

        _scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            timezone="Europe/Istanbul",
            job_defaults={
                "coalesce": True,       # Kaçırılan job'ları birleştir
                "max_instances": 1,      # Aynı job max 1 instance
                "misfire_grace_time": 300,  # 5dk tolerans
            },
        )

    return _scheduler


def _parse_time(time_str: str) -> time:
    """'HH:MM' formatındaki string'i time objesine çevir."""
    parts = time_str.split(":")
    return time(int(parts[0]), int(parts[1]))


def _get_cron_day_of_week(day_tr: str) -> str:
    """Türkçe gün adını cron day_of_week'e çevir."""
    day_map = {
        "Pazartesi": "mon",
        "Salı": "tue",
        "Çarşamba": "wed",
        "Perşembe": "thu",
        "Cuma": "fri",
        "Cumartesi": "sat",
        "Pazar": "sun",
    }
    return day_map.get(day_tr, "mon")


async def schedule_course(
    user_id: int,
    course_id: str,
    course_name: str,
    day: str,
    start_time: str,
    end_time: str,
    dys_url: str,
    direct_url: str | None = None,
    dys_search_hint: str | None = None,
    early_minutes: int = 5,
) -> str:
    """
    Bir ders için haftalık tekrarlayan job oluştur.
    Ders başlangıcından early_minutes dakika önce tetiklenir.

    Returns:
        Job ID
    """
    scheduler = get_scheduler()

    # Başlangıç saatinden early_minutes dk çıkar
    start = _parse_time(start_time)
    trigger_dt = datetime.combine(datetime.today(), start) - timedelta(minutes=early_minutes)
    trigger_time = trigger_dt.time()

    # Cron day
    cron_day = _get_cron_day_of_week(day)

    job_id = f"course_{user_id}_{course_id}"

    # Mevcut job varsa güncelle
    existing = scheduler.get_job(job_id)
    if existing:
        scheduler.remove_job(job_id)

    scheduler.add_job(
        _trigger_attend_lesson,
        trigger=CronTrigger(
            day_of_week=cron_day,
            hour=trigger_time.hour,
            minute=trigger_time.minute,
            # CronTrigger default timezone'u bazı ortamlarda sistem tz (Etc/UTC) olabiliyor.
            # Scheduler timezone'u ile tutarlı olması için açıkça set et.
            timezone=scheduler.timezone,
        ),
        id=job_id,
        name=f"{course_name} ({day} {start_time})",
        kwargs={
            "user_id": user_id,
            "course_id": course_id,
            "course_name": course_name,
            "dys_url": dys_url,
            "end_time": end_time,
            "direct_url": direct_url,
            "dys_search_hint": dys_search_hint,
        },
        replace_existing=True,
    )

    log.info(
        "scheduler.course_scheduled",
        job_id=job_id,
        course=course_name,
        day=day,
        trigger=f"{trigger_time.hour:02d}:{trigger_time.minute:02d}",
        start=start_time,
        user_id=user_id,
        early_minutes=early_minutes,
    )

    return job_id


async def _trigger_attend_lesson(
    user_id: int,
    course_id: str,
    course_name: str,
    dys_url: str,
    end_time: str,
    direct_url: str | None = None,
    dys_search_hint: str | None = None,
):
    """
    APScheduler tarafından çağrılır.
    Celery task'ı kuyruğa ekler.
    """
    from src.scheduler.tasks import attend_lesson_task
    # NOTE: Bu import burada kalmalı; testler patch'leyebilmek için module-level isme ihtiyaç duyar.
    from src.notifications.service import NotificationService

    log.info(
        "scheduler.triggering_task",
        user_id=user_id,
        course=course_name,
    )

    # Ders başlamadan 5dk önce kullanıcıya hatırlatma gönder.
    # Bildirim başarısız olsa bile ders katılım task'ı kuyruğa eklenmeye devam eder.
    try:
        if settings.TELEGRAM_BOT_TOKEN:
            notifier = NotificationService(bot_token=settings.TELEGRAM_BOT_TOKEN)
            await notifier.send_lesson_reminder(
                user_id=user_id,
                course_name=course_name,
                start_time=None,
                minutes_before=settings.MEETING_START_OFFSET_MINUTES,
            )
        else:
            log.warning("scheduler.reminder_skipped_missing_bot_token", user_id=user_id)
    except Exception as e:
        log.warning(
            "scheduler.reminder_failed",
            user_id=user_id,
            course=course_name,
            error=str(e),
        )

    try:
        async_result = attend_lesson_task.delay(
            user_id=user_id,
            course_id=course_id,
            course_name=course_name,
            dys_url=dys_url,
            end_time=end_time,
            direct_url=direct_url,
            dys_search_hint=dys_search_hint,
        )
        log.info(
            "scheduler.task_enqueued",
            user_id=user_id,
            course=course_name,
            celery_task_id=getattr(async_result, "id", None),
            queue="agent_queue",
        )
    except Exception as e:
        log.error(
            "scheduler.task_enqueue_failed",
            user_id=user_id,
            course=course_name,
            error=str(e),
            exc_info=True,
        )


async def schedule_all_courses_for_user(user_id: int) -> list[str]:
    """
    Kullanıcının tüm aktif derslerini zamanla.
    DB'den dersleri okur ve her biri için job oluşturur.

    Returns:
        Oluşturulan job ID'leri
    """
    scheduler = get_scheduler()
    started_here = False
    if not scheduler.running:
        # Jobstore'a persist garantisi için kısa süreli paused start.
        scheduler.start(paused=True)
        started_here = True

    from src.db.connection import get_session
    from src.db.repositories.credential import CredentialRepository
    from src.db.repositories.course import CourseRepository

    # day_of_week (int) → Türkçe gün adı
    day_int_to_name = {v: k for k, v in DAYS_TR.items()}

    job_ids = []

    async with get_session() as session:
        cred_repo = CredentialRepository(session)
        dys_url = await cred_repo.get_dys_url_for_user(user_id)
        if not dys_url:
            log.warning("scheduler.dys_url_missing", user_id=user_id)

        course_repo = CourseRepository(session)
        courses = await course_repo.get_user_courses(user_id, active_only=True)

        for course in courses:
            # is_online=False → yüz yüze, zamanlamaya gerek yok
            if course.is_online is False:
                continue

            day_name = day_int_to_name.get(course.day_of_week, "Pazartesi")

            # DYS URL yoksa ve direct_url da yoksa bu ders zamanlanamaz
            if not dys_url and not course.direct_url:
                log.warning(
                    "scheduler.course_skipped_missing_dys_url",
                    user_id=user_id,
                    course=str(course.id),
                    course_name=course.name,
                )
                continue

            job_id = await schedule_course(
                user_id=user_id,
                course_id=str(course.id),
                course_name=course.name,
                day=day_name,
                start_time=course.start_time.strftime("%H:%M"),
                end_time=course.end_time.strftime("%H:%M"),
                dys_url=dys_url or "",
                direct_url=course.direct_url,
                dys_search_hint=getattr(course, "dys_search_hint", None),
                early_minutes=settings.MEETING_START_OFFSET_MINUTES,
            )
            job_ids.append(job_id)

    log.info(
        "scheduler.all_courses_scheduled",
        user_id=user_id,
        count=len(job_ids),
        job_ids=job_ids,
    )

    # Bot gibi non-scheduler process'lerde scheduler instance'ı çalışır bırakma.
    if started_here:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass

    return job_ids


async def unschedule_all_for_user(user_id: int) -> int:
    """Kullanıcının tüm zamanlanmış job'larını kaldır."""
    scheduler = get_scheduler()
    removed = 0

    for job in scheduler.get_jobs():
        if job.id.startswith(f"course_{user_id}_"):
            scheduler.remove_job(job.id)
            removed += 1

    log.info("scheduler.all_removed", user_id=user_id, removed=removed)
    return removed


async def reconcile_jobs_for_user(user_id: int) -> dict:
    """
    Scheduler jobstore ile DB arasındaki drift'i düzelt.

    - DB'de pasif/silinmiş veya yüz yüze (is_online=False) olan derslerin job'larını kaldırır.
    - DB'de aktif online dersler için job oluşturmayı schedule_all_courses_for_user zaten yapar.
    """
    scheduler = get_scheduler()

    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository

    async with get_session() as session:
        course_repo = CourseRepository(session)
        courses = await course_repo.get_user_courses(user_id, active_only=True)

    # Active-only geldiği için burada sadece online filtreyi uygula
    valid_course_ids: set[str] = {
        str(c.id) for c in courses if c.is_online is not False
    }

    removed = 0
    kept = 0
    for job in scheduler.get_jobs():
        if not job.id.startswith(f"course_{user_id}_"):
            continue

        # job_id: course_{user_id}_{course_uuid}
        parts = job.id.split("_", 2)
        course_part = parts[2] if len(parts) == 3 else ""
        if course_part and course_part in valid_course_ids:
            kept += 1
            continue

        scheduler.remove_job(job.id)
        removed += 1

    log.info(
        "scheduler.reconcile_done",
        user_id=user_id,
        removed=removed,
        kept=kept,
        valid_count=len(valid_course_ids),
    )
    return {"removed": removed, "kept": kept, "valid": len(valid_course_ids)}


def get_user_jobs(user_id: int) -> list[dict]:
    """Kullanıcının zamanlanmış job'larını listele."""
    scheduler = get_scheduler()
    jobs = []

    for job in scheduler.get_jobs():
        if job.id.startswith(f"course_{user_id}_"):
            next_run = getattr(job, "next_run_time", None)
            jobs.append({
                "id": job.id,
                "name": job.name,
                # APScheduler 3.x: next_run_time. Ortam drift'inde attribute yoksa None kalır.
                "next_run": next_run,
                "job_type": f"{type(job).__module__}.{type(job).__name__}",
            })

    return jobs
