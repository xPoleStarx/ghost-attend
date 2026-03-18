"""GhostAttend session handlers."""

from __future__ import annotations

import redis.asyncio as aioredis
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.bot.utils.timezone import is_valid_timezone, normalize_timezone_name
from src.core.constants import DAYS_TR
from src.core.logging import get_logger

log = get_logger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status - show scheduled lessons and recent runtime/session summary."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    log.info("bot.status", user_id=user.id)

    from zoneinfo import ZoneInfo

    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository
    from src.db.repositories.session import SessionRepository
    from src.db.repositories.user import UserRepository
    from src.scheduler.lesson_scheduler import get_user_jobs

    user_tz = "Europe/Istanbul"
    courses = []
    recent_sessions = []
    try:
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_id(user.id)
            if db_user and getattr(db_user, "timezone", None):
                user_tz = db_user.timezone

            course_repo = CourseRepository(session)
            courses = await course_repo.get_user_courses(user.id, active_only=True)

            session_repo = SessionRepository(session)
            recent_sessions = await session_repo.get_recent_sessions(user.id, limit=1)
    except Exception as exc:
        log.error("bot.status_db_error", user_id=user.id, error=str(exc))

    if not courses:
        await update.message.reply_text(
            "Oturum Durumu\n\nZamanlanmis ders yok.\n/upload_schedule ile ders programini yukle."
        )
        return

    day_names = {value: key for key, value in DAYS_TR.items()}
    lines = ["Zamanlanmis Dersler", ""]
    for course in courses:
        if course.is_online is True:
            online_badge = "Online"
        elif course.is_online is False:
            online_badge = "Yuz yuze"
        else:
            online_badge = "Belirsiz"
        lines.append(
            f"- {course.name}\n"
            f"  {day_names.get(course.day_of_week, '?')} {course.start_time.strftime('%H:%M')}-{course.end_time.strftime('%H:%M')}\n"
            f"  {online_badge}"
        )

    try:
        jobs = get_user_jobs(user.id)
    except Exception as exc:
        log.warning("bot.status_job_list_failed", user_id=user.id, error=str(exc))
        jobs = []

    lines.append("")
    lines.append("Zamanlayici Job'lari")
    if jobs:
        for job in jobs:
            next_run_dt = job.get("next_run")
            if next_run_dt:
                try:
                    next_run = next_run_dt.astimezone(ZoneInfo(user_tz)).strftime("%Y-%m-%d %H:%M %Z")
                except Exception:
                    next_run = str(next_run_dt)
            else:
                next_run = "yok"
            lines.append(f"- {job.get('name') or 'isimsiz'}")
            lines.append(f"  next_run: {next_run}")
            if job.get("job_type"):
                lines.append(f"  type: {job['job_type']}")
    else:
        lines.append("- Bu kullanici icin job bulunamadi")

    if recent_sessions:
        last = recent_sessions[0]
        metadata = getattr(last, "metadata_", None) or {}
        runtime_session = metadata.get("runtime_session") or {}
        latest_snapshot = runtime_session.get("latest_snapshot") or {}
        lines.append("")
        lines.append("Son Oturum Ozeti")
        lines.append(f"- status: {last.status}")
        lines.append(f"- failure_reason: {last.failure_reason or '-'}")
        if runtime_session:
            lines.append(f"- runtime_mode: {runtime_session.get('runtime_mode') or metadata.get('runtime_mode') or '-'}")
            lines.append(f"- runtime_state: {runtime_session.get('fsm_state') or '-'}")
            lines.append(f"- last_tool: {runtime_session.get('last_tool') or '-'}")
            lines.append(f"- last_error: {runtime_session.get('last_error') or '-'}")
            if latest_snapshot:
                lines.append(f"- snapshot_title: {latest_snapshot.get('title') or '-'}")
                lines.append(f"- snapshot_url: {latest_snapshot.get('url') or '-'}")

    lines.append("")
    lines.append(f"Toplam: {len(courses)} ders (DB) · {len(jobs)} job (scheduler)")
    await update.message.reply_text("\n".join(lines))


async def cancel_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel - cancel active session and clear user state."""
    user = update.effective_user
    if user is None or update.message is None:
        return
    log.info("bot.cancel_session", user_id=user.id)

    redis_client: aioredis.Redis | None = context.bot_data.get("redis")

    from src.core.session_cancel import cancel_user_session
    from src.db.connection import get_session
    from src.db.repositories.user import UserRepository
    from src.scheduler.lesson_scheduler import unschedule_all_for_user

    async with get_session() as session:
        cancel_result = await cancel_user_session(
            user_id=user.id,
            redis_client=redis_client,
            db_session=session,
        )
        removed = await unschedule_all_for_user(user.id)
        log.info("bot.cancel_unschedule_done", user_id=user.id, removed_jobs=removed)

        repo = UserRepository(session)
        await repo.delete_user_and_related(user.id)
        await session.commit()

    context.user_data.clear()
    await update.message.reply_text(
        "Iptal alindi.\n"
        "Bu kullaniciya ait tum dersler, oturumlar, bildirimler ve kimlik bilgileri veritabanindan silindi.\n\n"
        f"Temizlik ozeti:\n"
        f"- scheduler_job_removed: {removed}\n"
        f"- cancel_flag_set: {bool(cancel_result.get('cancel_flag_set'))}\n"
        f"- redis_deleted: {int(cancel_result.get('redis_deleted') or 0)}\n"
        f"- db_session_cancelled: {bool(cancel_result.get('db_cancelled'))}\n\n"
        "Tekrar baslamak icin /start yazabilirsin."
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/health - show bot and scheduler heartbeat summary."""
    user = update.effective_user
    if user is None or update.message is None:
        return

    redis_client: aioredis.Redis | None = context.bot_data.get("redis")
    scheduler_alive = "bilinmiyor"
    if redis_client:
        try:
            value = await redis_client.get("scheduler:heartbeat")
            scheduler_alive = "evet" if value else "hayir"
        except Exception as exc:
            log.warning("bot.health_redis_failed", user_id=user.id, error=str(exc))
            scheduler_alive = "hata"
    else:
        scheduler_alive = "redis_yok"

    await update.message.reply_text(
        "Saglik Durumu\n\n"
        f"- redis_client: {'var' if redis_client else 'yok'}\n"
        f"- scheduler_heartbeat: {scheduler_alive}\n\n"
        "Notlar:\n"
        "- heartbeat hayir ise scheduler container calismiyor olabilir veya Redis baglantisi farkli olabilir.\n"
        "- heartbeat evet ama job yoksa, dersler online olmayabilir veya DYS URL eksik olabilir.\n"
    )


async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/timezone - show or update the user's timezone."""
    user = update.effective_user
    if user is None or update.message is None:
        return

    from src.db.connection import get_session
    from src.db.repositories.user import UserRepository

    requested = normalize_timezone_name(" ".join(context.args)) if context.args else ""

    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_id(user.id)
        current_timezone = getattr(db_user, "timezone", None) or "Europe/Istanbul"

        if not requested:
            await update.message.reply_text(
                "Kayitli timezone bilgisi:\n"
                f"- {current_timezone}\n\n"
                "Degistirmek icin ornek kullanim:\n"
                "/timezone Europe/Istanbul\n"
                "/timezone America/New_York"
            )
            return

        if not is_valid_timezone(requested):
            await update.message.reply_text(
                "Gecerli bir IANA timezone yazman gerekiyor.\n"
                "Ornek: /timezone Europe/Istanbul"
            )
            return

        await user_repo.create_or_update(
            user_id=user.id,
            first_name=update.effective_user.first_name,
            username=update.effective_user.username,
            timezone=requested,
        )
        await session.commit()

    await update.message.reply_text(
        "Timezone guncellendi.\n"
        f"- Yeni timezone: {requested}\n"
        "Sonraki scheduler job hesaplari bu saat dilimine gore yapilacak."
    )


def get_session_handlers() -> list[CommandHandler]:
    """Return command handlers related to session management."""
    return [
        CommandHandler("status", status_command),
        CommandHandler("cancel", cancel_session_command),
        CommandHandler("health", health_command),
        CommandHandler("timezone", timezone_command),
    ]
