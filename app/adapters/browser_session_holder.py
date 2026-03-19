"""Telegram thread başına tek browser-use BrowserSession — HITL sonrası sayfa/CAPTCHA korunur."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)

_sessions: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


async def get_session(thread_id: str, settings: "Settings") -> Any:
    """Aynı sohbet için yeniden kullanılan oturum; ilk çağrıda oluşturulur."""
    from browser_use import BrowserSession

    async with _lock_for(thread_id):
        existing = _sessions.get(thread_id)
        if existing is not None:
            return existing
        sess = BrowserSession(
            headless=settings.playwright_headless,
            keep_alive=True,
        )
        _sessions[thread_id] = sess
        logger.info("Yeni BrowserSession (keep_alive) thread_id=%s", thread_id)
        return sess


async def kill_session(thread_id: str) -> None:
    """İsteğe bağlı: sohbet sıfırlanınca veya /reset ile tarayıcıyı kapat."""
    async with _lock_for(thread_id):
        sess = _sessions.pop(thread_id, None)
    if sess is not None:
        try:
            await sess.kill()  # type: ignore[misc]
        except Exception:
            logger.exception("BrowserSession.kill failed thread_id=%s", thread_id)
