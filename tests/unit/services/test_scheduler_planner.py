from datetime import UTC, datetime

from app.scheduler.planner import CourseScheduleSnapshot, SchedulerPlanner


def test_scheduler_planner_builds_three_job_plans() -> None:
    planner = SchedulerPlanner()
    snapshot = CourseScheduleSnapshot(
        user_id=7,
        course_id=3,
        start_day_of_week_utc="MONDAY",
        start_time_utc="11:00",
    )

    plans = planner.build_job_plans(snapshot, now=datetime(2026, 1, 4, 10, 0, tzinfo=UTC))

    assert len(plans) == 3
    assert plans[0].job_type == "T_MINUS_3"
    assert plans[1].job_type == "T_MINUS_1"
    assert plans[2].job_type == "LEAVE"
    assert plans[0].idempotency_key.startswith("7:3:")
