from __future__ import annotations

from pathlib import Path
from typing import Any

from app.bot.service import GhostAttendBotService
from app.services.app_runtime import ApplicationRuntime
from app.telemetry.logging import get_logger

try:
    from telegram import Update
    from telegram.ext import (
        Application,
        ApplicationBuilder,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
    )
except Exception:  # noqa: BLE001
    Update = Any  # type: ignore[assignment,misc]
    Application = Any  # type: ignore[assignment,misc]
    ApplicationBuilder = None  # type: ignore[assignment]
    ContextTypes = Any  # type: ignore[assignment,misc]
    CommandHandler = None  # type: ignore[assignment]
    MessageHandler = None  # type: ignore[assignment]
    filters = None  # type: ignore[assignment]


class TelegramApplicationService:
    def __init__(self, runtime: ApplicationRuntime) -> None:
        self.runtime = runtime
        self.bot_service = GhostAttendBotService(runtime)
        self.log = get_logger(component="telegram_app")

    def build(self) -> Application | None:
        token = self.runtime.settings.telegram_bot_token
        if token is None or ApplicationBuilder is None:
            return None
        application = ApplicationBuilder().token(token.get_secret_value()).build()
        application.add_handler(CommandHandler("start", self.start_command))
        application.add_handler(CommandHandler("quit", self.quit_command))
        application.add_handler(CommandHandler("status", self.status_command))
        application.add_handler(CommandHandler("screenshot", self.screenshot_command))
        application.add_handler(MessageHandler(filters.PHOTO, self.photo_message))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_message))
        return application

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        message = await self.bot_service.handle_start(chat_id)
        await self._reply(update, message)

    async def quit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        message = await self.bot_service.handle_quit(chat_id)
        await self._reply(update, message)

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        message = await self.bot_service.handle_status(chat_id)
        await self._reply(update, message)

    async def screenshot_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        message = await self.bot_service.handle_screenshot(chat_id)
        await self._reply(update, message)

    async def text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        _ = context
        chat_id = self._chat_id(update)
        text = getattr(update.effective_message, "text", None)
        if chat_id is None or not text:
            return
        message = await self.bot_service.handle_text_message(chat_id, text)
        await self._reply(update, message)

    async def photo_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat_id = self._chat_id(update)
        if chat_id is None:
            return
        caption = getattr(update.effective_message, "caption", None)
        photos = getattr(update.effective_message, "photo", []) or []
        if not photos:
            return
        photo = photos[-1]
        file = await context.bot.get_file(photo.file_id)
        image_dir = self.runtime.settings.screenshot_dir
        image_dir.mkdir(parents=True, exist_ok=True)
        image_path = image_dir / f"telegram_upload_{chat_id}.jpg"
        await file.download_to_drive(custom_path=str(image_path))
        message = await self.bot_service.handle_photo_message(
            chat_id,
            Path(image_path),
            caption=caption,
        )
        await self._reply(update, message)

    async def _reply(self, update: Update, message: str) -> None:
        if getattr(update, "effective_message", None) is not None:
            await update.effective_message.reply_text(message)

    def _chat_id(self, update: Update) -> int | None:
        chat = getattr(update, "effective_chat", None)
        return None if chat is None else chat.id
