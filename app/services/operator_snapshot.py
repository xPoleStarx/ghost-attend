from __future__ import annotations

from dataclasses import dataclass

from app.browser.runtime import BrowserContextManager
from app.services.metrics import MetricsCollector
from app.services.task_queue import TaskQueueGateway


@dataclass(slots=True)
class OperatorSnapshotService:
    browser_contexts: BrowserContextManager
    task_queue: TaskQueueGateway
    metrics: MetricsCollector

    async def snapshot(self) -> dict[str, object]:
        active_contexts = await self.browser_contexts.list_contexts()
        return {
            "active_context_count": len(active_contexts),
            "active_contexts": [
                {
                    "user_id": handle.user_id,
                    "session_id": handle.session_id,
                    "meeting_state": handle.meeting_state.value,
                    "is_logged_in": handle.is_logged_in,
                    "active_course_name": handle.active_course_name,
                }
                for handle in active_contexts
            ],
            "queued_tasks": [record.task_name for record in self.task_queue.dispatched],
            "metrics": self.metrics.snapshot(),
        }
