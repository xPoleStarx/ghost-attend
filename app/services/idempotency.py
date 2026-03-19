from datetime import datetime


def build_job_idempotency_key(
    *, user_id: int, course_id: int, scheduled_start_utc: datetime, job_type: str
) -> str:
    timestamp = scheduled_start_utc.isoformat()
    return f"{user_id}:{course_id}:{timestamp}:{job_type}"
