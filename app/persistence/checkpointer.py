from __future__ import annotations

import os

import aiosqlite
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.config.settings import Settings


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(os.path.abspath(path))
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


async def create_checkpointer(settings: Settings) -> BaseCheckpointSaver:
    """LangGraph `ainvoke` / async yol için: dosya yolu → AsyncSqliteSaver; yoksa MemorySaver."""
    path = (settings.checkpoint_path or "").strip()
    if not path or path in (":memory:",):
        return MemorySaver()
    _ensure_parent_dir(path)
    abs_path = os.path.abspath(path)
    conn = await aiosqlite.connect(abs_path)
    return AsyncSqliteSaver(conn)
