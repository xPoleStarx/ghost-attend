"""
GhostAttend — Credential Handler

Credential toplama ve güncelleme işlemleri.
/reauth komutu ile credential yenileme.
"""

from telegram import Update
from telegram.ext import (
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.states import OnboardingState
from src.core.logging import get_logger

log = get_logger(__name__)


async def reauth_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """/reauth komutu — credential yenileme akışı başlat."""
    user = update.effective_user
    log.info("bot.reauth", user_id=user.id)

    # Şifre isteği
    prompt_msg = await update.message.reply_text(
        text=(
            "🔄 Kimlik doğrulamayı yeniliyorum.\n\n"
            "📧 E-posta adresini yaz:"
        ),
    )

    context.user_data["reauth_mode"] = True

    return OnboardingState.ASK_DYS_EMAIL


async def handle_reauth_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reauth: E-posta al."""
    email = update.message.text.strip()

    if "@" not in email:
        await update.message.reply_text("⚠️ Geçerli bir e-posta adresi gir.")
        return OnboardingState.ASK_DYS_EMAIL

    context.user_data["dys_email"] = email

    prompt_msg = await update.message.reply_text(
        text=(
            "🔒 Şifreni yaz:\n"
            "⚠️ Bu mesaj ve senin mesajın hemen silinecek."
        ),
    )
    context.user_data["password_prompt_msg_id"] = prompt_msg.message_id

    return OnboardingState.ASK_DYS_PASSWORD


async def handle_reauth_password(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reauth: Şifreyi al, mesajları sil, güncelle."""
    password = update.message.text
    user_id = update.effective_user.id

    # Mesajları sil
    try:
        await update.message.delete()
    except Exception:
        log.warning("bot.reauth_delete_failed", user_id=user_id)

    prompt_msg_id = context.user_data.get("password_prompt_msg_id")
    if prompt_msg_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=prompt_msg_id,
            )
        except Exception:
            pass

    # DB'ye kaydet
    from src.db.connection import get_session
    from src.db.repositories.user import UserRepository
    
    try:
        async with get_session() as session:
            user_repo = UserRepository(session)
            await user_repo.create_or_update_credentials(
                user_id=user_id,
                type="unified", # Varsayılan
                email=context.user_data["dys_email"],
                password=password,
                dys_url=context.user_data.get("dys_url")
            )
            await session.commit()
    except Exception as e:
        log.error("bot.reauth_db_failed", user_id=user_id, error=str(e))
        await update.effective_chat.send_message("❌ Veritabanı hatası oluştu.")
        return ConversationHandler.END

    await update.effective_chat.send_message(
        text=(
            "✅ Kimlik bilgileri başarıyla güncellendi ve şifrelendi!\n\n"
            "Artık yeni bilgilerle derslere katılabilirim."
        ),
        parse_mode="Markdown",
    )

    context.user_data.pop("reauth_mode", None)
    return ConversationHandler.END


async def cancel_reauth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Reauth'u iptal et."""
    context.user_data.pop("reauth_mode", None)
    await update.message.reply_text("⏹️ Kimlik yenileme iptal edildi.")
    return ConversationHandler.END


def get_reauth_handler() -> ConversationHandler:
    """Reauth ConversationHandler'ı oluştur."""
    return ConversationHandler(
        entry_points=[CommandHandler("reauth", reauth_command)],
        states={
            OnboardingState.ASK_DYS_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reauth_email),
            ],
            OnboardingState.ASK_DYS_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reauth_password),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_reauth)],
        name="reauth",
        persistent=True,
    )
