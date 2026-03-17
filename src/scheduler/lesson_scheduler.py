"""
GhostAttend — Ders Zamanlayıcı

APScheduler ile derslerin otomatik zamanlanması.
Her kullanıcının derslerini DB'den okur ve 5dk önce
Celery task'ı olarak kuyruğa ekler.
architecture.md Section 11.3
"""

import asyncio
from datetime import datetime, time, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.triggers.cron import CronTrigger

from src.core.config import settings
from src.core.constants import DAYS_TR
from src.core.logging import get_logger

log = get_logger(__name__)

# APScheduler persistence — Redis job store
_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Singleton scheduler instance döndür."""
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": RedisJobStore(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
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
                minutes_before=5,
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

    attend_lesson_task.delay(
        user_id=user_id,
        course_id=course_id,
        course_name=course_name,
        dys_url=dys_url,
        end_time=end_time,
        direct_url=direct_url,
        dys_search_hint=dys_search_hint,
    )


async def schedule_all_courses_for_user(user_id: int) -> list[str]:
    """
    Kullanıcının tüm aktif derslerini zamanla.
    DB'den dersleri okur ve her biri için job oluşturur.

    Returns:
        Oluşturulan job ID'leri
    """
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
            )
            job_ids.append(job_id)

    log.info(
        "scheduler.all_courses_scheduled",
        user_id=user_id,
        count=len(job_ids),
    )

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


def get_user_jobs(user_id: int) -> list[dict]:
    """Kullanıcının zamanlanmış job'larını listele."""
    scheduler = get_scheduler()
    jobs = []

    for job in scheduler.get_jobs():
        if job.id.startswith(f"course_{user_id}_"):
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None,
            })

    return jobs
