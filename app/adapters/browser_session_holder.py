"""Telegram thread başına tek browser-use BrowserSession — HITL sonrası sayfa/CAPTCHA korunur.

Sekme veya pencereyi elle kapatmak, browser-use SessionManager'ın sekme kurtarma döngüsüne
girmesine yol açabilir; kapatma için Telegram'da kill_session (/tarayici) kullanılmalı.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from app.adapters.browser_agent_holder import clear_cached_agent_sync
from app.adapters.hitl_pending import clear_pending_hitl

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)

_sessions: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


def _register_reconnection_failed_cleanup(sess: Any, thread_id: str) -> None:
    """Pencere manuel kapanınca CDP düşer; browser-use yeniden bağlanamazsa sonsuz kurtarma döngüsüne girer.

    ReconnectionFailed sonrası oturumu önbellekten silip kill() ile _intentional_stop tetiklenir.
    """
    from browser_use.browser.events import BrowserErrorEvent
    from browser_use.browser.watchdog_base import BaseWatchdog

    async def on_BrowserErrorEvent(event: BrowserErrorEvent) -> None:
        if getattr(event, "error_type", None) != "ReconnectionFailed":
            return

        async def _deferred_cleanup() -> None:
            await asyncio.sleep(0)
            async with _lock_for(thread_id):
                if _sessions.get(thread_id) is not sess:
                    return
                _sessions.pop(thread_id, None)
            try:
                await sess.kill()  # type: ignore[misc]
            except Exception:
                logger.exception("BrowserSession.kill after ReconnectionFailed thread_id=%s", thread_id)
            else:
                logger.info(
                    "Tarayıcı oturumu temizlendi (yeniden bağlanılamadı). Sonraki görev yeni pencere açar. thread_id=%s",
                    thread_id,
                )

        asyncio.create_task(_deferred_cleanup())

    BaseWatchdog.attach_handler_to_session(sess, BrowserErrorEvent, on_BrowserErrorEvent)


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
        _register_reconnection_failed_cleanup(sess, thread_id)
        _sessions[thread_id] = sess
        logger.info("Yeni BrowserSession (keep_alive) thread_id=%s", thread_id)
        return sess


async def kill_session(thread_id: str) -> None:
    """Sohbet için önbellekteki oturumu kapat (manuel /tarayici veya sıfırlama)."""
    clear_pending_hitl(thread_id)
    clear_cached_agent_sync(thread_id)
    async with _lock_for(thread_id):
        sess = _sessions.pop(thread_id, None)
    if sess is not None:
        try:
            await sess.kill()  # type: ignore[misc]
        except Exception:
            logger.exception("BrowserSession.kill failed thread_id=%s", thread_id)
