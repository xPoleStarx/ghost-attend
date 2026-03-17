"""
GhostAttend — Session Handler (Scheduler Entegre)

Aktif oturum yönetimi: /status, /cancel komutları.
Scheduler ve Redis bilgisiyle birlikte çalışır.
"""

import redis.asyncio as aioredis
from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.constants import REDIS_PREFIX_CANCEL
from src.core.logging import get_logger
from src.scheduler.lesson_scheduler import get_user_jobs

log = get_logger(__name__)


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — Aktif oturumu ve zamanlanmış dersleri göster."""
    user = update.effective_user
    log.info("bot.status", user_id=user.id)

    # Zamanlanmış job'ları kontrol et
    try:
        jobs = get_user_jobs(user.id)
    except Exception:
        jobs = []

    if not jobs:
        await update.message.reply_text(
            "📊 **Oturum Durumu**\n\n"
            "Zamanlanmış ders yok.\n"
            "/upload\\_schedule ile ders programını yükle.",
            parse_mode="Markdown",
        )
        return

    lines = ["📊 **Zamanlanmış Dersler**\n"]
    for job in jobs:
        next_run = job.get("next_run", "Bilinmiyor")
        lines.append(f"📚 {job['name']}\n   ⏰ Sonraki: {next_run}")

    lines.append(f"\nToplam: {len(jobs)} ders zamanlanmış")

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
    ]
