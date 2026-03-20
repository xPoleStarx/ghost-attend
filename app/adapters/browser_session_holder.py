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

# browser-use _navigate_and_wait çapraz alan için sabit 8 sn kullanır; holder üzerinden yüksütülür.
_nav_readiness_seconds: dict[str, float] = {"value": 18.0}
_nav_readiness_patch_done: bool = False


def _lock_for(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


def _ensure_nav_readiness_patch() -> None:
    """NavigateToUrlEvent timeout_ms vermediğinde kullanılan hazırlık süresini Settings ile hizala."""
    global _nav_readiness_patch_done

    if _nav_readiness_patch_done:
        return

    from browser_use.browser.session import BrowserSession

    _orig = BrowserSession._navigate_and_wait

    async def _patched_navigate_and_wait(
        self: Any,
        url: str,
        target_id: str,
        timeout: float | None = None,
        wait_until: str = "load",
    ) -> None:
        if timeout is None:
            target = self.session_manager.get_target(target_id)
            current_url = target.url
            same_domain = (
                url.split("/")[2] == current_url.split("/")[2]
                if url.startswith("http") and current_url.startswith("http")
                else False
            )
            timeout = 3.0 if same_domain else float(_nav_readiness_seconds["value"])
        await _orig(self, url, target_id, timeout=timeout, wait_until=wait_until)

    BrowserSession._navigate_and_wait = _patched_navigate_and_wait  # type: ignore[method-assign]
    _nav_readiness_patch_done = True


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
                    "Tarayıcı oturumu temizlendi (yeniden bağlanamadı). Sonraki görev yeni pencere açar. thread_id=%s",
                    thread_id,
                )

        asyncio.create_task(_deferred_cleanup())

    BaseWatchdog.attach_handler_to_session(sess, BrowserErrorEvent, on_BrowserErrorEvent)


async def get_session(thread_id: str, settings: "Settings") -> Any:
    """Aynı sohbet için yeniden kullanılan oturum; ilk çağrıda oluşturulur."""
    from browser_use import BrowserSession

    _nav_readiness_seconds["value"] = float(settings.browser_nav_readiness_timeout)
    _ensure_nav_readiness_patch()

    async with _lock_for(thread_id):
        existing = _sessions.get(thread_id)
        if existing is not None:
            return existing
        sess = BrowserSession(
            headless=settings.playwright_headless,
            keep_alive=True,
            cross_origin_iframes=settings.browser_cross_origin_iframes,
            minimum_wait_page_load_time=settings.browser_minimum_wait_page_load_time,
            wait_for_network_idle_page_load_time=settings.browser_wait_for_network_idle_page_load_time,
            wait_between_actions=settings.browser_wait_between_actions,
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
