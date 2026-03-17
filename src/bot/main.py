"""
GhostAttend — Telegram Bot Entry Point

Bot'u başlatır, handler'ları register eder.
Production'da webhook, development'ta polling kullanır.
"""

import asyncio

import redis.asyncio as aioredis
from telegram.ext import Application, CommandHandler

from src.bot.handlers.admin import get_admin_handlers
from src.bot.handlers.credentials import get_reauth_handler
from src.bot.handlers.mfa import get_mfa_handlers
from src.bot.handlers.schedule import get_schedule_handlers
from src.bot.handlers.session import get_session_handlers
from src.bot.handlers.start import get_onboarding_handler
from src.bot.handlers.agent_chat import handle_agent_chat
from src.bot.safe_bot import SafeExtBot
from src.core.config import settings
from src.core.logging import configure_logging, get_logger

log = get_logger(__name__)


def create_application() -> Application:
    """Telegram bot Application oluştur ve handler'ları register et."""

    # Merkezi metin sanitize katmanı için SafeExtBot kullan.
    builder = Application.builder().bot(SafeExtBot(token=settings.TELEGRAM_BOT_TOKEN))

    app = builder.build()

    # ── Shared connections (bot_data) ──
    # MFA / cancel gibi akışlar Redis'e ihtiyaç duyar.
    if settings.REDIS_URL:
        app.bot_data["redis"] = aioredis.from_url(settings.REDIS_URL)

    # ── Conversation Handlers ──
    app.add_handler(get_onboarding_handler())
    app.add_handler(get_reauth_handler())

    # ── Command Handlers ──
    for handler in get_session_handlers():
        app.add_handler(handler)

    for handler in get_schedule_handlers():
        app.add_handler(handler)

    for handler in get_admin_handlers():
        app.add_handler(handler)

    # ── Agentic Chat (en düşük önceliklerden biri) ──
    # Not: MFA kodları (4-8 digit) ayrı handler ile yakalanıyor.
    from telegram.ext import MessageHandler, filters
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & ~filters.Regex(r"^\d{4,8}$"),
            handle_agent_chat,
        )
    )

    # ── MFA Handlers (en düşük öncelik) ──
    for handler in get_mfa_handlers():
        app.add_handler(handler)

    # ── Cancel komutu (global fallback) ──
    # Not: ConversationHandler fallbacks / session handler'ı önceliklidir.
    # Buradaki fallback, beklenmedik bir durumda dahi "temizlik" garantisi sağlar.
    async def cancel_global(update, context):
        from src.core.session_cancel import cancel_user_session
        from src.db.connection import get_session

        user = update.effective_user
        if not user:
            return

        redis_client = context.bot_data.get("redis")
        async with get_session() as session:
            await cancel_user_session(user_id=user.id, redis_client=redis_client, db_session=session)
            await session.commit()

        context.user_data.clear()
        await update.message.reply_text("⏹️ İptal alındı. Geçici veriler temizlendi.")

    app.add_handler(CommandHandler("cancel", cancel_global))

    log.info("bot.handlers_registered")

    return app


async def run_polling():
    """Development modunda polling ile çalıştır."""
    app = create_application()

    log.info("bot.starting", mode="polling")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    # Graceful shutdown için bekle
    try:
        # Event loop'un kapanmasını bekle
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        redis_client = app.bot_data.get("redis")
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


async def run_webhook():
    """Production modunda webhook ile çalıştır."""
    app = create_application()

    log.info("bot.starting", mode="webhook", url=settings.TELEGRAM_WEBHOOK_URL)
    await app.initialize()
    await app.start()

    await app.bot.set_webhook(
        url=f"{settings.TELEGRAM_WEBHOOK_URL}/webhook",
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
    )

    # Webhook server'ı başlat (FastAPI veya aiohttp ile)
    # Bu kısım api/webhooks.py ile entegre edilecek

    await app.updater.start_webhook(
        listen="0.0.0.0",
        port=8443,
        url_path="webhook",
        webhook_url=f"{settings.TELEGRAM_WEBHOOK_URL}/webhook",
        secret_token=settings.TELEGRAM_WEBHOOK_SECRET,
    )

    try:
        stop_event = asyncio.Event()
        await stop_event.wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        redis_client = app.bot_data.get("redis")
        if redis_client:
            try:
                await redis_client.close()
            except Exception:
                pass
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


def main():
    """Bot entry point."""
    configure_logging(settings.LOG_LEVEL, settings.ENVIRONMENT)

    log.info(
        "bot.init",
        environment=settings.ENVIRONMENT,
        llm_provider=settings.AGENT_LLM_PROVIDER,
    )

    if settings.is_development:
        asyncio.run(run_polling())
    else:
        asyncio.run(run_webhook())


if __name__ == "__main__":
    main()
