from __future__ import annotations

from dataclasses import dataclass, field

from app.repos.courses import CourseRepository
from app.scheduler.loop import APSchedulerLoop
from app.scheduler.service import SchedulingService
from app.services.course_runtime import build_schedule_snapshots


@dataclass(slots=True)
class SchedulerBootstrapResult:
    scheduled_course_count: int
    scheduled_job_count: int
    idempotency_keys: list[str] = field(default_factory=list)


class SchedulerBootstrapService:
    def __init__(
        self,
        course_repository: CourseRepository,
        scheduling_service: SchedulingService,
        scheduler_loop: APSchedulerLoop,
    ) -> None:
        self.course_repository = course_repository
        self.scheduling_service = scheduling_service
        self.scheduler_loop = scheduler_loop

    async def bootstrap_for_user(self, user_id: int) -> SchedulerBootstrapResult:
        courses = await self.course_repository.list_active_for_user(user_id)
        return await self._bootstrap_courses(courses)

    async def bootstrap_all_active_courses(self) -> SchedulerBootstrapResult:
        courses = await self.course_repository.list_all_active()
        return await self._bootstrap_courses(courses)

    async def _bootstrap_courses(self, courses: list[object]) -> SchedulerBootstrapResult:
        snapshots = build_schedule_snapshots(courses)  # type: ignore[arg-type]
        job_ids: list[str] = []
        for snapshot in snapshots:
            plans = await self.scheduler_loop.register_course(snapshot)
            job_ids.extend(plan.idempotency_key for plan in plans)
        return SchedulerBootstrapResult(
            scheduled_course_count=len(snapshots),
            scheduled_job_count=len(job_ids),
            idempotency_keys=job_ids,
        )
