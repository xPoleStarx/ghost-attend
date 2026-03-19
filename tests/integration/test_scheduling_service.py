from dataclasses import dataclass

import pytest

from app.domain.schemas import RecoveryTaskPlan
from app.scheduler.planner import CourseScheduleSnapshot, SchedulerPlanner
from app.scheduler.service import InMemorySchedulerBackend, SchedulingService
from app.services.task_queue import TaskQueueGateway


class FakeSchedulerJobRepository:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    async def create_or_reactivate(
        self,
        *,
        user_id: int,
        course_id: int,
        job_type: str,
        apscheduler_job_id: str,
    ) -> object:
        self.records.append(
            {
                "user_id": user_id,
                "course_id": course_id,
                "job_type": job_type,
                "apscheduler_job_id": apscheduler_job_id,
            }
        )
        return self.records[-1]


@dataclass
class FakeAsyncResult:
    id: str


@pytest.mark.asyncio
async def test_scheduling_service_plans_and_dispatches_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = FakeSchedulerJobRepository()
    backend = InMemorySchedulerBackend()
    gateway = TaskQueueGateway()
    monkeypatch.setattr(
        "app.services.task_queue.celery_app.send_task",
        lambda task_name, kwargs: FakeAsyncResult(id=f"{task_name}-{kwargs['user_id']}"),
    )
    service = SchedulingService(
        planner=SchedulerPlanner(),
        backend=backend,
        task_queue=gateway,
        scheduler_job_repository=repo,  # type: ignore[arg-type]
    )
    snapshot = CourseScheduleSnapshot(
        user_id=7,
        course_id=3,
        start_day_of_week_utc="MONDAY",
        start_time_utc="11:00",
    )

    plans = await service.schedule_course(snapshot)
    assert len(plans) == 3
    assert len(repo.records) == 3
    assert len(backend.jobs) == 3

    dispatch_id = service.dispatch_scheduled_job(plans[1], session_id="session-1")
    assert dispatch_id == "execute_join_flow-7"
    assert gateway.dispatched[0].task_name == "execute_join_flow"


def test_scheduling_service_dispatches_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = TaskQueueGateway()
    monkeypatch.setattr(
        "app.services.task_queue.celery_app.send_task",
        lambda task_name, kwargs: FakeAsyncResult(id=f"{task_name}-{kwargs['user_id']}"),
    )
    service = SchedulingService(
        planner=SchedulerPlanner(),
        backend=InMemorySchedulerBackend(),
        task_queue=gateway,
        scheduler_job_repository=None,
    )

    dispatch_id = service.dispatch_recovery(
        RecoveryTaskPlan(user_id=9, session_id="session-9", requires_login=True)
    )

    assert dispatch_id == "recover_active_session-9"
    assert gateway.dispatched[0].kwargs["requires_login"] is True
