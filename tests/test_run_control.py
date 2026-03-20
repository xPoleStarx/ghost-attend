"""app.run_control: /stop bayrağı, tarayıcı aktifliği, progress gönderici kaydı."""

from __future__ import annotations

import asyncio

import pytest

from app.run_control import (
    clear_stop,
    emit_progress,
    is_browser_run_active_async,
    is_stop_requested,
    mark_browser_run_active,
    mark_browser_run_idle,
    register_progress_sender,
    request_stop,
    unregister_progress_sender,
    wait_stop,
)


@pytest.mark.asyncio
async def test_stop_request_and_clear():
    tid = "test-thread-1"
    clear_stop(tid)
    assert not is_stop_requested(tid)
    request_stop(tid)
    assert is_stop_requested(tid)
    clear_stop(tid)
    assert not is_stop_requested(tid)


@pytest.mark.asyncio
async def test_browser_active_tracking():
    tid = "test-thread-2"
    await mark_browser_run_idle(tid)
    assert not await is_browser_run_active_async(tid)
    await mark_browser_run_active(tid)
    assert await is_browser_run_active_async(tid)
    await mark_browser_run_idle(tid)
    assert not await is_browser_run_active_async(tid)


@pytest.mark.asyncio
async def test_progress_emit_calls_sender():
    tid = "test-thread-3"
    received: list[str] = []

    async def send(t: str) -> None:
        received.append(t)

    register_progress_sender(tid, send)
    try:
        await emit_progress(tid, "  hello  ")
        assert received == ["hello"]
        await emit_progress(tid, "")
        assert len(received) == 1
    finally:
        unregister_progress_sender(tid)

    await emit_progress(tid, "after")
    assert len(received) == 1


@pytest.mark.asyncio
async def test_wait_stop_unblocks_when_request_stop_fires():
    tid = "test-wait-stop-1"
    clear_stop(tid)

    async def fire_stop_soon() -> None:
        await asyncio.sleep(0.05)
        request_stop(tid)

    bg = asyncio.create_task(fire_stop_soon())
    try:
        await asyncio.wait_for(wait_stop(tid), timeout=2.0)
    finally:
        await bg
        clear_stop(tid)


@pytest.mark.asyncio
async def test_wait_stop_race_run_finishes_first_cancel_stop_task():
    tid = "test-wait-stop-2"
    clear_stop(tid)

    async def short_work() -> str:
        await asyncio.sleep(0.02)
        return "done"

    run_task = asyncio.create_task(short_work())
    stop_task = asyncio.create_task(wait_stop(tid))
    await asyncio.wait({run_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)

    assert run_task.done() and not run_task.cancelled()
    stop_task.cancel()
    try:
        await stop_task
    except asyncio.CancelledError:
        pass

    assert run_task.result() == "done"
    assert not is_stop_requested(tid)
