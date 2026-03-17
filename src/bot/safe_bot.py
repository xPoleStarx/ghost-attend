"""
GhostAttend — Safe Telegram Bot Wrapper

python-telegram-bot (PTB) üzerinden kullanıcıya giden metinlerin bazı durumlarda
yanlışlıkla JSON-escape edilmiş string olarak gönderilmesini önlemek için,
merkezi bir sanitize katmanı sağlar.
"""

from __future__ import annotations

import re

from telegram.error import BadRequest
from telegram.ext import ExtBot

from src.bot.utils.safe_text import normalize_outgoing_text
from src.core.logging import get_logger

log = get_logger(__name__)

_BYTE_OFFSET_RE = re.compile(r"byte offset (\d+)")


def _snippet_around_byte_offset(text: str, offset: int, *, radius: int = 80) -> str:
    """
    Telegram BadRequest hataları UTF-8 byte offset verir.
    Offset etrafından küçük bir snippet çıkarıp debug etmeyi kolaylaştırır.
    """
    b = text.encode("utf-8", errors="replace")
    start = max(0, offset - radius)
    end = min(len(b), offset + radius)
    return b[start:end].decode("utf-8", errors="replace")


def _log_parse_entities_error(err: Exception, *, text: str | None = None, caption: str | None = None) -> None:
    raw = str(err)
    match = _BYTE_OFFSET_RE.search(raw)
    offset = int(match.group(1)) if match else None

    payload = text if text is not None else caption
    if offset is not None and isinstance(payload, str) and payload:
        snippet = _snippet_around_byte_offset(payload, offset)
        log.error(
            "telegram.bad_request_parse_entities",
            error=raw,
            byte_offset=offset,
            snippet=snippet,
        )
    else:
        log.error("telegram.bad_request_parse_entities", error=raw)


class SafeExtBot(ExtBot):
    """Outgoing text/caption alanlarını güvenli şekilde normalize eden ExtBot."""

    async def send_message(self, *args, **kwargs):  # type: ignore[override]
        if "text" in kwargs and isinstance(kwargs["text"], str):
            kwargs["text"] = normalize_outgoing_text(kwargs["text"], parse_mode=kwargs.get("parse_mode"))
        original_parse_mode = kwargs.get("parse_mode")
        original_text = kwargs.get("text")
        try:
            return await super().send_message(*args, **kwargs)
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                _log_parse_entities_error(e, text=kwargs.get("text"))
                # Markdown parse'ı bozulduysa aynı metni düz metin olarak tekrar dene.
                if original_parse_mode and isinstance(original_text, str):
                    retry_kwargs = dict(kwargs)
                    retry_kwargs.pop("parse_mode", None)
                    retry_kwargs["text"] = original_text
                    return await super().send_message(*args, **retry_kwargs)
            raise

    async def edit_message_text(self, *args, **kwargs):  # type: ignore[override]
        if "text" in kwargs and isinstance(kwargs["text"], str):
            kwargs["text"] = normalize_outgoing_text(kwargs["text"], parse_mode=kwargs.get("parse_mode"))
        original_parse_mode = kwargs.get("parse_mode")
        original_text = kwargs.get("text")
        try:
            return await super().edit_message_text(*args, **kwargs)
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                _log_parse_entities_error(e, text=kwargs.get("text"))
                if original_parse_mode and isinstance(original_text, str):
                    retry_kwargs = dict(kwargs)
                    retry_kwargs.pop("parse_mode", None)
                    retry_kwargs["text"] = original_text
                    return await super().edit_message_text(*args, **retry_kwargs)
            raise

    async def send_photo(self, *args, **kwargs):  # type: ignore[override]
        if "caption" in kwargs and isinstance(kwargs["caption"], str):
            kwargs["caption"] = normalize_outgoing_text(kwargs["caption"], parse_mode=kwargs.get("parse_mode"))
        original_parse_mode = kwargs.get("parse_mode")
        original_caption = kwargs.get("caption")
        try:
            return await super().send_photo(*args, **kwargs)
        except BadRequest as e:
            if "Can't parse entities" in str(e):
                _log_parse_entities_error(e, caption=kwargs.get("caption"))
                if original_parse_mode and isinstance(original_caption, str):
                    retry_kwargs = dict(kwargs)
                    retry_kwargs.pop("parse_mode", None)
                    retry_kwargs["caption"] = original_caption
                    return await super().send_photo(*args, **retry_kwargs)
            raise

