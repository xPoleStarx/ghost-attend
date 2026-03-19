from datetime import UTC, datetime

from app.services.idempotency import build_job_idempotency_key


def test_idempotency_key_is_stable() -> None:
    key = build_job_idempotency_key(
        user_id=7,
        course_id=3,
        scheduled_start_utc=datetime(2026, 3, 19, 11, 0, tzinfo=UTC),
        job_type="T_MINUS_1",
    )

    assert key == "7:3:2026-03-19T11:00:00+00:00:T_MINUS_1"
