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

log = get_logger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — Aktif oturumu ve zamanlanmış dersleri göster (DB-based)."""
    user = update.effective_user
    log.info("bot.status", user_id=user.id)

    from src.db.connection import get_session
    from src.db.repositories.course import CourseRepository

    try:
        async with get_session() as session:
            repo = CourseRepository(session)
            courses = await repo.get_user_courses(user.id, active_only=True)
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

        lines.append(
            f"📚 **{c.name}**\n"
            f"   📅 {day_names.get(c.day_of_week, '?')} "
            f"{c.start_time.strftime('%H:%M')}–{c.end_time.strftime('%H:%M')}\n"
            f"   {online_badge}"
        )

    lines.append(f"\nToplam: {len(courses)} ders zamanlanmış")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cancel_session_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/cancel — Aktif oturumu durdur (Redis'e cancel flag yaz)."""
    user = update.effective_user
    log.info("bot.cancel_session", user_id=user.id)

    redis_client: aioredis.Redis | None = context.bot_data.get("redis")

    if redis_client:
        cancel_key = f"{REDIS_PREFIX_CANCEL}{user.id}"
        await redis_client.set(cancel_key, "1", ex=600)  # 10dk TTL

        await update.message.reply_text(
            "⏹️ Aktif oturum iptal ediliyor...\n"
            "Agent en kısa sürede duracak."
        )
    else:
        await update.message.reply_text("⏹️ Şu anda aktif bir oturum yok.")


def get_session_handlers() -> list[CommandHandler]:
    """Session ile ilgili handler'ları döndür."""
    return [
        CommandHandler("status", status_command),
        CommandHandler("cancel", cancel_session_command),
    ]
