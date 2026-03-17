"""
GhostAttend — MFA Bot Handler

Telegram üzerinden MFA/2FA kodu alma.
Agent MFA tespit ettiğinde bu handler aktif olur:
- SMS/email kodu → kullanıcı yazar → Redis'e gönderilir
- Authenticator push → kullanıcı /confirmed yazar → Redis'e yazılır
architecture.md Section 10.4, 10.5
"""

import redis.asyncio as aioredis
from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.states import SessionState
from src.core.constants import REDIS_PREFIX_MFA
from src.core.logging import get_logger

log = get_logger(__name__)


async def handle_mfa_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Kullanıcının yazdığı MFA kodunu Redis'e yaz.
    Agent bu kodu Redis'ten okuyup forma girecek.

    Format: sadece rakamlar (6-8 haneli), yoksa normal mesaj olarak işlenir.
    """
    text = update.message.text.strip()
    user_id = update.effective_user.id

    # MFA kodu formatı: 4-8 haneli sayı
    if not text.isdigit() or not (4 <= len(text) <= 8):
        return  # MFA kodu değil, normal mesaj

    # Redis bağlantısı context'ten al
    redis_client: aioredis.Redis | None = context.bot_data.get("redis")
    if not redis_client:
        log.error("mfa.redis_not_available", user_id=user_id)
        await update.message.reply_text("⚠️ Sistem hatası. Tekrar dene.")
        return

    # Aktif MFA bekleme var mı kontrol et
    mfa_key = f"{REDIS_PREFIX_MFA}{user_id}"

    # Kullanıcının mesajını hemen sil (güvenlik)
    try:
        await update.message.delete()
    except Exception:
        log.warning("mfa.delete_message_failed", user_id=user_id)

    # Kodu Redis'e yaz (agent okuyacak)
    await redis_client.set(mfa_key, text, ex=300)

    log.info("mfa.code_submitted_via_telegram", user_id=user_id, code_length=len(text))

    await update.effective_chat.send_message(
        text=f"✅ MFA kodu alındı ({len(text)} haneli). Agent'a iletiliyor...",
    )


async def handle_confirmed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /confirmed komutu — Authenticator push onayı.
    Kullanıcı telefonundaki Microsoft Authenticator'dan
    onay verdikten sonra bu komutu yazarak agent'a bildirir.
    """
    user_id = update.effective_user.id

    redis_client: aioredis.Redis | None = context.bot_data.get("redis")
    if not redis_client:
        await update.message.reply_text("⚠️ Sistem hatası.")
        return

    mfa_key = f"{REDIS_PREFIX_MFA}{user_id}"
    await redis_client.set(mfa_key, "CONFIRMED", ex=300)

    log.info("mfa.push_confirmed_via_telegram", user_id=user_id)

    await update.message.reply_text(
        "✅ Authenticator onayı kaydedildi. Agent devam ediyor..."
    )


async def handle_mfa_timeout_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    MFA timeout sonrası kullanıcıdan gelen yanıtları işle.
    /retry komutu ile oturumu yeniden başlatma.
    """
    user_id = update.effective_user.id
    log.info("mfa.retry_requested", user_id=user_id)

    # TODO: Oturumu yeniden başlat
    await update.message.reply_text(
        "🔄 Oturum yeniden başlatılıyor...\n"
        "_(Scheduler entegrasyonu Sprint 5'te aktifleşecek)_"
    )


def get_mfa_handlers() -> list:
    """MFA ile ilgili tüm handler'ları döndür."""
    return [
        CommandHandler("confirmed", handle_confirmed),
        CommandHandler("retry", handle_mfa_timeout_response),
        # MFA kod yakalama — en düşük öncelikle eklenmeli (diğer handler'lar eşleşmezse)
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & filters.Regex(r"^\d{4,8}$"),
            handle_mfa_code,
        ),
    ]
