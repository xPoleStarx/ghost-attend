from pathlib import Path

import pytest

from app.browser.runtime import BrowserContextManager, BrowserRuntime
from app.services.metrics import MetricsCollector
from app.services.operator_snapshot import OperatorSnapshotService
from app.services.task_queue import TaskQueueGateway, TaskQueueRecord


@pytest.mark.asyncio
async def test_operator_snapshot_reports_contexts_and_metrics(tmp_path: Path) -> None:
    runtime = BrowserRuntime(headless=True, screenshot_dir=tmp_path)
    manager = BrowserContextManager(runtime=runtime)
    handle = await manager.get_or_create_context(user_id=7, session_id="session-1")
    handle.is_logged_in = True
    handle.active_course_name = "Kariyer Planlama"

    queue = TaskQueueGateway()
    queue.dispatched.append(
        TaskQueueRecord(task_name="prepare_browser_session", kwargs={"user_id": 7}, task_id="task-1")
    )
    metrics = MetricsCollector()
    metrics.increment("join.success")

    snapshot = await OperatorSnapshotService(
        browser_contexts=manager,
        task_queue=queue,
        metrics=metrics,
    ).snapshot()

    assert snapshot["active_context_count"] == 1
    assert snapshot["queued_tasks"] == ["prepare_browser_session"]
    assert snapshot["metrics"] == {"join.success": 1}
