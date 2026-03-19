from datetime import datetime, timedelta

from app.domain.enums import SchedulerJobType
from app.services.idempotency import build_job_idempotency_key


def schedule_job_windows(course_start: datetime) -> dict[str, datetime]:
    return {
        SchedulerJobType.T_MINUS_3.value: course_start - timedelta(minutes=3),
        SchedulerJobType.T_MINUS_1.value: course_start - timedelta(minutes=1),
        SchedulerJobType.LEAVE.value: course_start + timedelta(minutes=90),
    }


def build_scheduler_job_id(
    *, user_id: int, course_id: int, course_start: datetime, job_type: SchedulerJobType
) -> str:
    return build_job_idempotency_key(
        user_id=user_id,
        course_id=course_id,
        scheduled_start_utc=course_start,
        job_type=job_type.value,
    )
