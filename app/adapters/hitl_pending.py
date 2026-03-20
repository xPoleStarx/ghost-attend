"""HITL kesintisi sonrası yeni bir run_browser_automation çağrısı (hints boş) geldiğinde
LangGraph resume kaçırılsa bile giriş döngüsünü kırmak için işlem-içi durum.

Telegram thread_id ile anahtarlanır; tarayıcı oturumu gibi süreç-içi bellekte tutulur.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TTL_SEC = 30 * 60


@dataclass
class _Pending:
    last_url: str | None
    hitl_reason: str | None
    monotonic_ts: float


_store: dict[str, _Pending] = {}


def record_pending_hitl(thread_id: str, last_url: str | None, hitl_reason: str | None) -> None:
    _store[str(thread_id)] = _Pending(
        last_url=last_url,
        hitl_reason=hitl_reason,
        monotonic_ts=time.monotonic(),
    )


def clear_pending_hitl(thread_id: str) -> None:
    _store.pop(str(thread_id), None)


def take_synthetic_hints_if_orphan(thread_id: str) -> list[str] | None:
    """hints=[] ile gelen yeni araç çağrısı: önceki NEEDS_HUMAN hâlâ geçerliyse sentetik ipuçları üret (bir kez tüketilir)."""
    tid = str(thread_id)
    p = _store.get(tid)
    if p is None:
        return None
    if time.monotonic() - p.monotonic_ts > _TTL_SEC:
        _store.pop(tid, None)
        return None
    u = p.last_url or "(unknown)"
    r = p.hitl_reason or "unknown"
    _store.pop(tid, None)
    logger.info(
        "HITL yetim araç çağrısı: sentetik devam ipuçları enjekte edildi thread_id=%s url=%s reason=%s",
        tid,
        u,
        r,
    )
    return [
        "[Auto — a prior HITL interrupt was expected; this turn may be a fresh tool call.]\n"
        f"Last stop reason: {r}\n"
        f"Last URL: {u}\n"
        "Do not navigate again to the site's home in your first action; stay on the current tab. "
        "If the page is a login form, use the email/password from the user's latest message and proceed.",
    ]
