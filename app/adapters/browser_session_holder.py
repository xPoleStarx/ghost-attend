"""Telegram thread başına tek browser-use BrowserSession — HITL sonrası sayfa/CAPTCHA korunur.

Sekme veya pencereyi elle kapatmak, browser-use SessionManager'ın sekme kurtarma döngüsüne
girmesine yol açabilir; kapatma için Telegram'da kill_session (/tarayici) kullanılmalı.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from app.adapters.browser_agent_holder import clear_cached_agent_sync
from app.adapters.hitl_pending import clear_pending_hitl

if TYPE_CHECKING:
    from app.config.settings import Settings

logger = logging.getLogger(__name__)

_sessions: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}

# Son bilinen sekme URL'si (thread başına) — boş-hint takip görevlerinde aynı Agent/add_new_task ile devam için.
_thread_last_browser_url: dict[str, str] = {}


def record_thread_last_browser_url(thread_id: str, url: str | None) -> None:
    if not url or not str(url).strip():
        return
    _thread_last_browser_url[str(thread_id)] = str(url).strip()


def get_thread_last_browser_url(thread_id: str) -> str | None:
    u = _thread_last_browser_url.get(str(thread_id))
    return u if u else None


def clear_thread_browser_continuity(thread_id: str) -> None:
    """kill_session / farklı domain ile yeni Agent öncesi: takip URL önbelleğini sil."""
    _thread_last_browser_url.pop(str(thread_id), None)

# browser-use _navigate_and_wait çapraz alan için sabit 8 sn kullanır; holder üzerinden yüksütülür.
_nav_readiness_seconds: dict[str, float] = {"value": 12.0}
# Aynı site içi navigate için readiness (eski 3 sn SPA’larda kırılıyordu).
_same_origin_nav_timeout: dict[str, float] = {"value": 12.0}
# Bu anahtar hostlar için her zaman tam readiness (youtube.com aynı-origin kısayolu yok).
_nav_always_full_readiness_hosts: dict[str, str] = {"value": "youtube.com,www.youtube.com,m.youtube.com"}
# NavigateToUrlEvent varsayılanı 'load'; SPA / YouTube için domcontentloaded (Settings ile hizalı).
_nav_wait_until: dict[str, str] = {"value": "domcontentloaded"}
_nav_readiness_patch_done: bool = False


def _host_key(netloc: str) -> str:
    h = (netloc or "").lower()
    if h.startswith("www."):
        return h[4:]
    return h


def _parse_readiness_host_list(raw: str) -> frozenset[str]:
    parts = []
    for x in (raw or "").split(","):
        s = x.strip().lower()
        if not s:
            continue
        if s.startswith("www."):
            s = s[4:]
        parts.append(s)
    return frozenset(parts)


def _host_needs_full_readiness(netloc: str, always_full: frozenset[str]) -> bool:
    hk = _host_key(netloc)
    if hk in always_full:
        return True
    return any(hk.endswith("." + p) for p in always_full)


def resolve_nav_readiness_timeout_seconds(
    url: str,
    current_url: str,
    *,
    full_readiness: float,
    same_origin_timeout: float,
    always_full_readiness_hosts_csv: str,
) -> float:
    """Aynı site / tam readiness kuralı — birim testi ve _patched_navigate_and_wait için."""
    if not url.startswith("http") or not current_url.startswith("http"):
        return float(full_readiness)
    pu, pc = urlparse(url), urlparse(current_url)
    same_site = _host_key(pu.netloc) == _host_key(pc.netloc)
    always_full = _parse_readiness_host_list(always_full_readiness_hosts_csv)
    if same_site:
        if _host_needs_full_readiness(pu.netloc, always_full):
            return float(full_readiness)
        return float(same_origin_timeout)
    return float(full_readiness)


def apply_browser_use_event_timeouts(settings: "Settings") -> None:
    """bubus TIMEOUT_* env — browser_use.events içindeki event_timeout default_factory ilk olay öncesi okunur."""
    os.environ.setdefault("TIMEOUT_ScreenshotEvent", str(float(settings.browser_timeout_screenshot_event)))
    os.environ.setdefault(
        "TIMEOUT_BrowserStateRequestEvent",
        str(float(settings.browser_timeout_browser_state_request)),
    )
    os.environ.setdefault(
        "TIMEOUT_NavigateToUrlEvent",
        str(float(settings.browser_timeout_navigate_url_event)),
    )


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
            timeout = resolve_nav_readiness_timeout_seconds(
                url,
                current_url,
                full_readiness=float(_nav_readiness_seconds["value"]),
                same_origin_timeout=float(_same_origin_nav_timeout["value"]),
                always_full_readiness_hosts_csv=str(_nav_always_full_readiness_hosts["value"]),
            )
        wu = str(_nav_wait_until["value"])
        await _orig(self, url, target_id, timeout=timeout, wait_until=wu)

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
    apply_browser_use_event_timeouts(settings)
    _nav_readiness_seconds["value"] = float(settings.browser_nav_readiness_timeout)
    _same_origin_nav_timeout["value"] = float(settings.browser_same_origin_nav_timeout)
    _nav_always_full_readiness_hosts["value"] = str(settings.browser_nav_always_full_readiness_hosts)
    _nav_wait_until["value"] = str(settings.browser_navigate_wait_until)
    _ensure_nav_readiness_patch()

    from browser_use import BrowserSession

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
    clear_thread_browser_continuity(thread_id)
    async with _lock_for(thread_id):
        sess = _sessions.pop(thread_id, None)
    if sess is not None:
        try:
            await sess.kill()  # type: ignore[misc]
        except Exception:
            logger.exception("BrowserSession.kill failed thread_id=%s", thread_id)
