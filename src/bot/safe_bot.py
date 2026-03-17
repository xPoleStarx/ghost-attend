"""
GhostAttend — Safe Telegram Bot Wrapper

python-telegram-bot (PTB) üzerinden kullanıcıya giden metinlerin bazı durumlarda
yanlışlıkla JSON-escape edilmiş string olarak gönderilmesini önlemek için,
merkezi bir sanitize katmanı sağlar.
"""

from __future__ import annotations

from telegram.ext import ExtBot

from src.bot.utils.safe_text import maybe_unescape_json_string


class SafeExtBot(ExtBot):
    """Outgoing text/caption alanlarını güvenli şekilde normalize eden ExtBot."""

    async def send_message(self, *args, **kwargs):  # type: ignore[override]
        if "text" in kwargs and isinstance(kwargs["text"], str):
            kwargs["text"] = maybe_unescape_json_string(kwargs["text"])
        return await super().send_message(*args, **kwargs)

    async def edit_message_text(self, *args, **kwargs):  # type: ignore[override]
        if "text" in kwargs and isinstance(kwargs["text"], str):
            kwargs["text"] = maybe_unescape_json_string(kwargs["text"])
        return await super().edit_message_text(*args, **kwargs)

    async def send_photo(self, *args, **kwargs):  # type: ignore[override]
        if "caption" in kwargs and isinstance(kwargs["caption"], str):
            kwargs["caption"] = maybe_unescape_json_string(kwargs["caption"])
        return await super().send_photo(*args, **kwargs)

