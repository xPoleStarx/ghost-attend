"""Telegram thread_id ile PNG teslim: Tool çıktılarında base64 taşımadan state dışı kısa yol."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_pending_png: dict[str, bytes] = {}


def stash_screenshot_png(thread_id: str, png: bytes | None) -> None:
    if not png:
        return
    with _lock:
        _pending_png[thread_id] = png


def pop_screenshot_png(thread_id: str) -> bytes | None:
    with _lock:
        return _pending_png.pop(thread_id, None)
