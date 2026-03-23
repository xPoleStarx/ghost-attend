from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

_stop_events: dict[str, asyncio.Event] = {}
_browser_run_lock = asyncio.Lock()
_browser_run_active: set[str] = set()
_progress_senders: dict[str, Callable[[str], Awaitable[None]]] = {}
# Tarayıcı adımları sürerken Telegram metinleri (chat_turn kilidi dışında) burada birikir.
_mid_run_queues: dict[str, asyncio.Queue[str]] = {}


def _event_for(thread_id: str) -> asyncio.Event:
    tid = str(thread_id)
    ev = _stop_events.get(tid)
    if ev is None:
        ev = asyncio.Event()
        _stop_events[tid] = ev
    return ev


def _mid_run_queue_for(thread_id: str) -> asyncio.Queue[str]:
    tid = str(thread_id)
    q = _mid_run_queues.get(tid)
    if q is None:
        q = asyncio.Queue()
        _mid_run_queues[tid] = q
    return q


def clear_mid_run_queue(thread_id: str) -> None:
    """Durdurma veya iptal sonrası bekleyen ara mesajları at."""
    tid = str(thread_id)
    q = _mid_run_queues.pop(tid, None)
    if q is None:
        return
    while True:
        try:
            q.get_nowait()
        except asyncio.QueueEmpty:
            break


async def enqueue_user_correction(thread_id: str, text: str) -> None:
    """Tarayıcı çalışırken kullanıcı düzeltmesi — on_step bir sonraki adımda tüketir."""
    chunk = (text or "").strip()[:4000]
    if not chunk:
        return
    await _mid_run_queue_for(thread_id).put(chunk)


async def drain_mid_run_corrections(thread_id: str) -> list[str]:
    q = _mid_run_queues.get(str(thread_id))
    if q is None:
        return []
    out: list[str] = []
    while True:
        try:
            out.append(q.get_nowait())
        except asyncio.QueueEmpty:
            break
    return out


def request_stop(thread_id: str) -> None:
    """Telegram /stop: tarayıcı döngüsü should_stop ile kesilir."""
    clear_mid_run_queue(thread_id)
    _event_for(thread_id).set()


def clear_stop(thread_id: str) -> None:
    tid = str(thread_id)
    ev = _stop_events.get(tid)
    if ev is not None:
        ev.clear()
    clear_mid_run_queue(tid)


def is_stop_requested(thread_id: str) -> bool:
    ev = _stop_events.get(str(thread_id))
    return bool(ev and ev.is_set())


async def wait_stop(thread_id: str) -> None:
    """/stop ile request_stop çağrılana kadar bekle; agent.run ile asyncio.wait yarışında kullanılır."""
    await _event_for(thread_id).wait()


async def mark_browser_run_active(thread_id: str) -> None:
    async with _browser_run_lock:
        _browser_run_active.add(str(thread_id))


async def mark_browser_run_idle(thread_id: str) -> None:
    async with _browser_run_lock:
        _browser_run_active.discard(str(thread_id))


async def is_browser_run_active_async(thread_id: str) -> bool:
    async with _browser_run_lock:
        return str(thread_id) in _browser_run_active


def register_progress_sender(thread_id: str, send: Callable[[str], Awaitable[None]]) -> None:
    _progress_senders[str(thread_id)] = send


def unregister_progress_sender(thread_id: str) -> None:
    _progress_senders.pop(str(thread_id), None)


async def emit_progress(thread_id: str, text: str) -> None:
    tid = str(thread_id)
    fn = _progress_senders.get(tid)
    if fn is None:
        return
    chunk = (text or "").strip()[:4096]
    if not chunk:
        return
    try:
        await fn(chunk)
    except Exception:
        logger.exception("emit_progress failed thread_id=%s", tid)
