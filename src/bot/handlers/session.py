"""
GhostAttend — Session Handler (DB-Based)

Aktif oturum yönetimi: /status, /cancel komutları.
DB'den ders bilgisini çeker, scheduler bağımsız çalışır.
"""

import redis.asyncio as aioredis
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.constants import DAYS_TR, REDIS_PREFIX_CANCEL
from src.core.logging import get_logger
from src.bot.utils.safe_text import escape_dynamic_text

log = get_logger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — Aktif oturumu ve zamanlanmış dersleri göster (DB-based)."""
    user = update.effective_user
    log.info("bot.status", user_id=user.id)

    from zoneinfo import ZoneInfo

    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository
    from src.db.repositories.session import SessionRepository
    from src.db.repositories.user import UserRepository
    from src.scheduler.lesson_scheduler import get_user_jobs

    recent_sessions = []
    user_tz = "Europe/Istanbul"
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
    except Exception as e:
        log.error("bot.status_db_error", user_id=user.id, error=str(e))
        courses = []

    if not courses:
        await update.message.reply_text(
            "📊 **Oturum Durumu**\n\n"
            "Zamanlanmış ders yok.\n"
            "/upload\\_schedule ile ders programını yükle.",
            parse_mode="Markdown",
        )
        return

    # day_of_week (int) → Türkçe gün adı
    day_names = {v: k for k, v in DAYS_TR.items()}

    lines = ["📊 **Zamanlanmış Dersler**\n"]
    for c in courses:
        if c.is_online is True:
            online_badge = "🟢 Online"
        elif c.is_online is False:
            online_badge = "🔴 Yüz yüze"
        else:
            online_badge = "❓ Belirsiz"

        safe_name = escape_dynamic_text(c.name, parse_mode="Markdown")
        lines.append(
            f"📚 **{safe_name}**\n"
            f"   📅 {day_names.get(c.day_of_week, '?')} "
            f"{c.start_time.strftime('%H:%M')}–{c.end_time.strftime('%H:%M')}\n"
            f"   {online_badge}"
        )

    # Scheduler job'ları (APScheduler Redis jobstore)
    try:
        jobs = get_user_jobs(user.id)
    except Exception as e:
        log.warning("bot.status_job_list_failed", user_id=user.id, error=str(e))
        jobs = []

    if jobs:
        lines.append("\n⏱️ **Zamanlayıcı Job'ları**")
        for j in jobs:
            job_name = escape_dynamic_text(str(j.get("name") or ""), parse_mode="Markdown")
            next_run_dt = j.get("next_run")
            job_type = j.get("job_type")

            if next_run_dt:
                try:
                    next_local = next_run_dt.astimezone(ZoneInfo(user_tz))
                    next_run = next_local.strftime("%Y-%m-%d %H:%M %Z")
                except Exception:
                    next_run = str(next_run_dt)
            else:
                next_run = "yok"

            safe_next_run = escape_dynamic_text(next_run, parse_mode="Markdown")
            if job_type:
                safe_job_type = escape_dynamic_text(str(job_type), parse_mode="Markdown")
                lines.append(f"- {job_name}\n  `next_run`: `{safe_next_run}`\n  `type`: `{safe_job_type}`")
            else:
                lines.append(f"- {job_name}\n  `next_run`: `{safe_next_run}`")
    else:
        lines.append(
            "\n⏱️ **Zamanlayıcı Job'ları**\n"
            "- (Bu kullanıcı için job bulunamadı)\n\n"
            "Olası nedenler:\n"
            "- Scheduler container çalışmıyor olabilir.\n"
            "- Redis ayarları tutarsız olabilir (bot/scheduler farklı Redis'e bakıyor).\n"
            "- Bu dersler online değilse (yüz yüze) job üretilmez.\n"
            "- Kullanıcının DYS URL'i yoksa (ve direct_url yoksa) job atlanır.\n\n"
            "Kontrol:\n"
            "- `/health` ile scheduler heartbeat'e bak.\n"
            "- /upload\\_schedule sonrası tekrar `/status` dene."
        )

    # Son oturum özeti (varsa)
    if recent_sessions:
        last = recent_sessions[0]
        status = last.status
        reason = last.failure_reason or "-"
        lines.append(
            "\n🧾 **Son Oturum Özeti**\n"
            f"- status: `{status}`\n"
            f"- failure_reason: `{reason}`"
        )

    lines.append(f"\nToplam: {len(courses)} ders (DB) · {len(jobs)} job (scheduler)")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel — Bu kullanıcının aktif oturumunu ve tüm verilerini temizle."""
    user = update.effective_user
    log.info("bot.cancel_session", user_id=user.id)

    redis_client: aioredis.Redis | None = context.bot_data.get("redis")

    from src.core.session_cancel import cancel_user_session
    from src.db.connection import get_session
    from src.db.repositories.user import UserRepository
    from src.scheduler.lesson_scheduler import unschedule_all_for_user

    async with get_session() as session:
        # 1) Runtime oturumunu iptal et + Redis temizliği
        result = await cancel_user_session(
            user_id=user.id,
            redis_client=redis_client,
            db_session=session,
        )

        # 2) Kullanıcının tüm zamanlanmış job'larını kaldır
        removed = await unschedule_all_for_user(user.id)
        log.info("bot.cancel_unschedule_done", user_id=user.id, removed_jobs=removed)

        # 3) Kullanıcının veritabanındaki tüm verilerini sil
        repo = UserRepository(session)
        await repo.delete_user_and_related(user.id)

        await session.commit()

    # PTB tarafı: conversation state'lerini de temizle
    context.user_data.clear()

    await update.message.reply_text(
        "⏹️ İptal alındı.\n"
        "Bu kullanıcıya ait tüm dersler, oturumlar, bildirimler ve kimlik bilgileri veritabanından silindi.\n"
        "Tekrar başlamak için /start yazabilirsin."
    )


async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/health — Bot/Redis/Scheduler heartbeat özetini göster."""
    user = update.effective_user
    redis_client: aioredis.Redis | None = context.bot_data.get("redis")

    scheduler_alive = "bilinmiyor"
    if redis_client:
        try:
            val = await redis_client.get("scheduler:heartbeat")
            scheduler_alive = "evet" if val else "hayır"
        except Exception as e:
            log.warning("bot.health_redis_failed", user_id=user.id, error=str(e))
            scheduler_alive = "hata"
    else:
        scheduler_alive = "redis_yok"

    await update.message.reply_text(
        "🩺 **Sağlık Durumu**\n\n"
        f"- redis_client: `{'var' if redis_client else 'yok'}`\n"
        f"- scheduler_heartbeat: `{scheduler_alive}`\n\n"
        "Notlar:\n"
        "- heartbeat `hayır` ise scheduler container çalışmıyor olabilir veya Redis bağlantısı farklı olabilir.\n"
        "- heartbeat `evet` ama job yoksa, dersler online olmayabilir veya DYS URL eksik olabilir.\n",
        parse_mode="Markdown",
    )


def get_session_handlers() -> list[CommandHandler]:
    """Session ile ilgili handler'ları döndür."""
    return [
        CommandHandler("status", status_command),
        CommandHandler("cancel", cancel_session_command),
        CommandHandler("health", health_command),
    ]
