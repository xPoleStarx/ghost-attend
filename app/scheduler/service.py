from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import SchedulerJobType
from app.domain.schemas import RecoveryTaskPlan, SchedulerJobPlan
from app.repos.scheduler_jobs import SchedulerJobRepository
from app.scheduler.planner import CourseScheduleSnapshot, SchedulerPlanner
from app.services.task_queue import TaskQueueGateway


@dataclass(slots=True)
class InMemorySchedulerBackend:
    jobs: dict[str, SchedulerJobPlan] = field(default_factory=dict)

    def add_job(self, plan: SchedulerJobPlan) -> None:
        self.jobs[plan.idempotency_key] = plan


class SchedulingService:
    def __init__(
        self,
        *,
        planner: SchedulerPlanner,
        backend: InMemorySchedulerBackend,
        task_queue: TaskQueueGateway,
        scheduler_job_repository: SchedulerJobRepository | None = None,
    ) -> None:
        self.planner = planner
        self.backend = backend
        self.task_queue = task_queue
        self.scheduler_job_repository = scheduler_job_repository

    async def schedule_course(self, snapshot: CourseScheduleSnapshot) -> list[SchedulerJobPlan]:
        plans = self.planner.build_job_plans(snapshot)
        for plan in plans:
            self.backend.add_job(plan)
            if self.scheduler_job_repository is not None:
                await self.scheduler_job_repository.create_or_reactivate(
                    user_id=plan.user_id,
                    course_id=plan.course_id,
                    job_type=plan.job_type,
                    apscheduler_job_id=plan.idempotency_key,
                )
        return plans

    def dispatch_scheduled_job(self, plan: SchedulerJobPlan, *, session_id: str | None = None) -> str:
        task_name_map = {
            SchedulerJobType.T_MINUS_3.value: "notify_upcoming_class",
            SchedulerJobType.T_MINUS_1.value: "execute_join_flow",
            SchedulerJobType.LEAVE.value: "execute_leave_flow",
        }
        task_name = task_name_map[plan.job_type]
        if plan.job_type == SchedulerJobType.T_MINUS_3.value:
            return self.task_queue.enqueue(task_name, user_id=plan.user_id, course_id=plan.course_id)
        payload = {
            "user_id": plan.user_id,
            "course_id": plan.course_id,
            "session_id": session_id,
        }
        return self.task_queue.enqueue(task_name, **payload)

    def dispatch_recovery(self, plan: RecoveryTaskPlan) -> str:
        return self.task_queue.enqueue(
            "recover_active_session",
            user_id=plan.user_id,
            session_id=plan.session_id,
            requires_login=plan.requires_login,
        )
