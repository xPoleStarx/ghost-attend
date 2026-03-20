"""Telegram thread başına tek browser-use Agent örneği — HITL sonrası add_new_task + run() ile devam.

Tarayıcı oturumu browser_session_holder'da kalır; Agent nesnesi de kesintisiz görev için burada tutulur.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

_agents: dict[str, Any] = {}
_locks: dict[str, asyncio.Lock] = {}


def _lock_for(thread_id: str) -> asyncio.Lock:
    if thread_id not in _locks:
        _locks[thread_id] = asyncio.Lock()
    return _locks[thread_id]


def get_cached_agent(thread_id: str) -> Any | None:
    return _agents.get(thread_id)


def set_cached_agent(thread_id: str, agent: Any) -> None:
    _agents[str(thread_id)] = agent


def pop_cached_agent(thread_id: str) -> Any | None:
    return _agents.pop(str(thread_id), None)


async def dispose_cached_agent(thread_id: str) -> None:
    """Önbellekteki ajanı kaldır; run() zaten close() çağırmış olabilir."""
    async with _lock_for(thread_id):
        agent = _agents.pop(str(thread_id), None)
    if agent is None:
        return
    try:
        await agent.close()
    except Exception:
        logger.debug("dispose_cached_agent: close atlandı veya hata (thread_id=%s)", thread_id, exc_info=True)


def clear_cached_agent_sync(thread_id: str) -> None:
    """kill_session gibi await kullanılamayan yerler için yalnızca referansı sil."""
    _agents.pop(str(thread_id), None)
