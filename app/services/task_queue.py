from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.worker.celery_app import celery_app


@dataclass(slots=True)
class TaskQueueRecord:
    task_name: str
    kwargs: dict[str, Any]
    task_id: str


@dataclass(slots=True)
class TaskQueueGateway:
    dispatched: list[TaskQueueRecord] = field(default_factory=list)

    def enqueue(self, task_name: str, **kwargs: Any) -> str:
        async_result = celery_app.send_task(task_name, kwargs=kwargs)
        self.dispatched.append(
            TaskQueueRecord(task_name=task_name, kwargs=kwargs, task_id=str(async_result.id))
        )
        return str(async_result.id)
