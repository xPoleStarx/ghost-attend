"""
GhostAttend — Admin Handler (Scheduler Entegre)

/pause, /resume, /logs, /help yönetim komutları.
Scheduler ve DB ile entegre.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.logging import get_logger
from src.scheduler.lesson_scheduler import (
    get_user_jobs,
    schedule_all_courses_for_user,
    unschedule_all_for_user,
)

log = get_logger(__name__)


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/pause — Otomasyonu geçici durdur (tüm zamanlanmış dersleri kaldır)."""
    user = update.effective_user
    log.info("bot.pause", user_id=user.id)

    try:
        removed = await unschedule_all_for_user(user.id)
        await update.message.reply_text(
            f"⏸️ GhostAttend duraklatıldı.\n"
            f"{removed} ders zamanlaması kaldırıldı.\n\n"
            "/resume ile devam edebilirsin."
        )
    except Exception as e:
        log.error("bot.pause_failed", error=str(e))
        await update.message.reply_text("⚠️ Duraklama sırasında hata oluştu.")


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/resume — Otomasyonu devam ettir (tüm dersleri yeniden zamanla)."""
    user = update.effective_user
    log.info("bot.resume", user_id=user.id)

    try:
        job_ids = await schedule_all_courses_for_user(user.id)
        await update.message.reply_text(
            f"▶️ GhostAttend devam ediyor!\n"
            f"{len(job_ids)} ders yeniden zamanlandı."
        )
    except Exception as e:
        log.error("bot.resume_failed", error=str(e))
        await update.message.reply_text("⚠️ Devam ettirme sırasında hata oluştu.")


async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/logs — Son oturum özetlerini göster."""
    user = update.effective_user
    log.info("bot.logs", user_id=user.id)

    # TODO: DB'den son 5 session'ı çek ve göster
    await update.message.reply_text(
        text=(
            "📋 **Son Oturumlar**\n\n"
            "_(DB entegrasyonu tamamlanınca gösterilecek)_\n\n"
            "Zamanlanmış dersler için /status yaz."
        ),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/help — Komut listesi."""
    await update.message.reply_text(
        text=(
            "🤖 **GhostAttend Komutları**\n\n"
            "📋 **Kurulum**\n"
            "/start — İlk kurulumu başlat\n"
            "/upload\\_schedule — Ders programı yükle\n"
            "/reauth — Giriş bilgilerini güncelle\n\n"
            "📊 **Durum**\n"
            "/status — Zamanlanmış dersleri gör\n"
            "/courses — Kayıtlı derslerini listele\n"
            "/schedule — Bugünün derslerini göster\n"
            "/logs — Son oturum kayıtları\n\n"
            "⚙️ **Yönetim**\n"
            "/pause — Otomasyonu duraklat\n"
            "/resume — Otomasyonu devam ettir\n"
            "/cancel — Aktif oturumu iptal et\n"
            "/confirmed — MFA Authenticator onayı\n\n"
            "❓ /help — Bu mesaj"
        ),
        parse_mode="Markdown",
    )


def get_admin_handlers() -> list[CommandHandler]:
    """Admin ve yardım handler'larını döndür."""
    return [
        CommandHandler("pause", pause_command),
        CommandHandler("resume", resume_command),
        CommandHandler("logs", logs_command),
        CommandHandler("help", help_command),
    ]
