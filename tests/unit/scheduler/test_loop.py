import pytest

from app.domain.schemas import SchedulerJobPlan
from app.scheduler.loop import APSchedulerLoop


class FakeSchedulingService:
    def __init__(self) -> None:
        self.dispatched: list[SchedulerJobPlan] = []

    async def schedule_course(self, snapshot: object) -> list[SchedulerJobPlan]:
        _ = snapshot
        return [
            SchedulerJobPlan(
                user_id=7,
                course_id=3,
                job_type="T_MINUS_1",
                run_at=__import__("datetime").datetime(2026, 1, 5, 10, 59, tzinfo=__import__("datetime").UTC),
                idempotency_key="job-1",
            )
        ]

    def dispatch_scheduled_job(self, plan: SchedulerJobPlan, *, session_id: str | None = None) -> str:
        _ = session_id
        self.dispatched.append(plan)
        return "queued"


@pytest.mark.asyncio
async def test_scheduler_loop_registers_plan_without_real_scheduler() -> None:
    loop = APSchedulerLoop(scheduling_service=FakeSchedulingService(), scheduler=None)  # type: ignore[arg-type]
    plans = await loop.register_course(snapshot=object())

    assert len(plans) == 1
    assert "job-1" in loop.registered_job_ids
