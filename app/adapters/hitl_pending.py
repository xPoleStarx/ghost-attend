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
    u = p.last_url or "(bilinmeyen)"
    r = p.hitl_reason or "bilinmiyor"
    _store.pop(tid, None)
    logger.info(
        "HITL yetim araç çağrısı: sentetik devam ipuçları enjekte edildi thread_id=%s url=%s reason=%s",
        tid,
        u,
        r,
    )
    return [
        "[Otomatik — önceki HITL kesintisi bekleniyordu; bu tur yeni bir araç çağrısı olabilir.]\n"
        f"Son durma nedeni: {r}\n"
        f"Son URL: {u}\n"
        "İlk eylemde görev metnindeki siteye tekrar navigate etme; mevcut sekmede kal. "
        "Sayfa giriş formuysa kullanıcıdan gelen e-posta/şifre ile doldur ve ilerle.",
    ]
