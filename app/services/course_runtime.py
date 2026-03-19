from __future__ import annotations

from app.db.models import Course
from app.scheduler.planner import CourseScheduleSnapshot


def serialize_courses_for_agent(courses: list[Course]) -> list[dict[str, object]]:
    return [{"id": course.id, "name": course.name} for course in courses]


def build_schedule_snapshots(courses: list[Course]) -> list[CourseScheduleSnapshot]:
    return [
        CourseScheduleSnapshot(
            user_id=course.user_id,
            course_id=course.id,
            start_day_of_week_utc=course.start_day_of_week_utc,
            start_time_utc=course.start_time_utc,
        )
        for course in courses
        if course.is_active
    ]
