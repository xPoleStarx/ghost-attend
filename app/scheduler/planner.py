from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.domain.enums import SchedulerJobType
from app.domain.schemas import SchedulerJobPlan
from app.scheduler.jobs import build_scheduler_job_id, schedule_job_windows

WEEKDAY_TO_INDEX = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}


@dataclass(slots=True)
class CourseScheduleSnapshot:
    user_id: int
    course_id: int
    start_day_of_week_utc: str
    start_time_utc: str


class SchedulerPlanner:
    def next_course_start(
        self, snapshot: CourseScheduleSnapshot, *, now: datetime | None = None
    ) -> datetime:
        reference = now or datetime.now(UTC)
        weekday_index = WEEKDAY_TO_INDEX[snapshot.start_day_of_week_utc]
        hour, minute = (int(part) for part in snapshot.start_time_utc.split(":"))
        days_ahead = (weekday_index - reference.weekday()) % 7
        candidate_date = reference.date() + timedelta(days=days_ahead)
        candidate = datetime.combine(candidate_date, time(hour, minute, tzinfo=UTC))
        if candidate <= reference:
            candidate = candidate + timedelta(days=7)
        return candidate

    def build_job_plans(
        self, snapshot: CourseScheduleSnapshot, *, now: datetime | None = None
    ) -> list[SchedulerJobPlan]:
        course_start = self.next_course_start(snapshot, now=now)
        windows = schedule_job_windows(course_start)
        plans: list[SchedulerJobPlan] = []
        for job_type in (
            SchedulerJobType.T_MINUS_3,
            SchedulerJobType.T_MINUS_1,
            SchedulerJobType.LEAVE,
        ):
            plans.append(
                SchedulerJobPlan(
                    user_id=snapshot.user_id,
                    course_id=snapshot.course_id,
                    job_type=job_type.value,
                    run_at=windows[job_type.value],
                    idempotency_key=build_scheduler_job_id(
                        user_id=snapshot.user_id,
                        course_id=snapshot.course_id,
                        course_start=course_start,
                        job_type=job_type,
                    ),
                )
            )
        return plans
