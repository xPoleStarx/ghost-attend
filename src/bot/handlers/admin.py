"""
GhostAttend — Admin Handler (Scheduler Entegre)

/pause, /resume, /logs, /help yönetim komutları.
Scheduler ve DB ile entegre.
"""

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes

from src.core.logging import get_logger
from src.bot.utils.safe_text import escape_dynamic_text
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
    """/logs — Son 5 oturum özetini veritabanından çekip göster."""
    user = update.effective_user
    log.info("bot.logs", user_id=user.id)

    from src.db.connection import get_session
    from src.db.repositories.session import SessionRepository

    try:
        async with get_session() as session:
            repo = SessionRepository(session)
            recent = await repo.get_recent_sessions(user.id, limit=5)
    except Exception as e:
        log.error("bot.logs_db_error", user_id=user.id, error=str(e))
        await update.message.reply_text("⚠️ Geçmiş kayıtlar çekilirken hata oluştu.")
        return

    if not recent:
        await update.message.reply_text("📋 Henüz bir oturum kaydı bulunmuyor.")
        return

    status_emojis = {
        "completed": "✅",
        "failed": "❌",
        "cancelled": "⏹️",
        "running": "⏳",
        "joined": "👤",
        "pending": "📅",
    }

    lines = ["📋 **Son Oturumlar**\n"]
    for s in recent:
        emoji = status_emojis.get(s.status, "❓")
        date_str = s.created_at.strftime("%d/%m %H:%M")
        
        # Course name'i relationship'tan veya async loader'dan al
        # (Eager loading varsayıyoruz veya DB query'de JOIN yapmalıydık)
        # Session modelinde course relationship var.
        course_name = escape_dynamic_text(s.course.name if s.course else "Bilinmeyen Ders", parse_mode="Markdown")
        
        lines.append(f"{emoji} {date_str} — **{course_name}** ({s.status})")
        if s.failure_reason:
            reason = escape_dynamic_text(s.failure_reason[:50], parse_mode="Markdown")
            lines.append(f"   └ ⚠️ {reason}...")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


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
