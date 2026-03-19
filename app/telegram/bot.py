from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from app.config.settings import Settings
from app.graph.builder import build_compiled_graph
from app.persistence.checkpointer import create_checkpointer
from app.telegram.handlers import on_close_browser, on_start, on_text_message


async def _post_init(application: Application) -> None:
    settings: Settings = application.bot_data["settings"]
    checkpointer = await create_checkpointer(settings)
    graph = build_compiled_graph(settings, checkpointer)
    application.bot_data["graph"] = graph
    me = await application.bot.get_me()
    application.bot_data["bot_username"] = me.username


def run_bot(settings: Settings) -> None:
    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .build()
    )
    application.bot_data["settings"] = settings

    application.add_handler(CommandHandler("start", on_start))
    application.add_handler(CommandHandler("tarayici", on_close_browser))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))

    application.run_polling(allowed_updates=Update.ALL_TYPES)
