from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC

from app.domain.schemas import SchedulerJobPlan
from app.scheduler.planner import CourseScheduleSnapshot
from app.scheduler.service import SchedulingService

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # noqa: BLE001
    AsyncIOScheduler = None  # type: ignore[assignment]
    CronTrigger = None  # type: ignore[assignment]


WEEKDAY_NAME_MAP = {
    0: "mon",
    1: "tue",
    2: "wed",
    3: "thu",
    4: "fri",
    5: "sat",
    6: "sun",
}


@dataclass(slots=True)
class APSchedulerLoop:
    scheduling_service: SchedulingService
    scheduler: object | None = None
    registered_job_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.scheduler is None and AsyncIOScheduler is not None:
            self.scheduler = AsyncIOScheduler(timezone=UTC)

    async def start(self) -> None:
        if self.scheduler is not None and hasattr(self.scheduler, "running") and not self.scheduler.running:
            self.scheduler.start()

    async def stop(self) -> None:
        if self.scheduler is not None and hasattr(self.scheduler, "shutdown"):
            self.scheduler.shutdown(wait=False)

    async def register_course(self, snapshot: CourseScheduleSnapshot) -> list[SchedulerJobPlan]:
        plans = await self.scheduling_service.schedule_course(snapshot)
        for plan in plans:
            self._register_plan(plan)
        return plans

    def _register_plan(self, plan: SchedulerJobPlan) -> None:
        if self.scheduler is None or CronTrigger is None:
            self.registered_job_ids.add(plan.idempotency_key)
            return
        if plan.idempotency_key in self.registered_job_ids:
            return
        trigger = CronTrigger(
            day_of_week=WEEKDAY_NAME_MAP[plan.run_at.weekday()],
            hour=plan.run_at.hour,
            minute=plan.run_at.minute,
            timezone=UTC,
        )
        self.scheduler.add_job(
            self._dispatch_job,
            trigger=trigger,
            args=[plan],
            id=plan.idempotency_key,
            replace_existing=True,
        )
        self.registered_job_ids.add(plan.idempotency_key)

    def _dispatch_job(self, plan: SchedulerJobPlan) -> str:
        return self.scheduling_service.dispatch_scheduled_job(plan, session_id=None)


def create_scheduler() -> object | None:
    if AsyncIOScheduler is None:
        return None
    return AsyncIOScheduler(timezone=UTC)
