from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

_locks: dict[int, asyncio.Lock] = {}


def _lock_for(chat_id: int) -> asyncio.Lock:
    if chat_id not in _locks:
        _locks[chat_id] = asyncio.Lock()
    return _locks[chat_id]


@asynccontextmanager
async def chat_turn(chat_id: int) -> AsyncIterator[None]:
    """Aynı sohbette tek seferde bir graf çalıştır (tarayıcı çakışmasını önler)."""
    async with _lock_for(chat_id):
        yield None
