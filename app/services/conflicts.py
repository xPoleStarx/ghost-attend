from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CourseWindow:
    course_id: int
    name: str
    start_day_of_week_utc: str
    start_time_utc: str
    end_day_of_week_utc: str
    end_time_utc: str


class ScheduleConflictDetector:
    def find_conflicts(self, courses: list[CourseWindow]) -> list[tuple[CourseWindow, CourseWindow]]:
        conflicts: list[tuple[CourseWindow, CourseWindow]] = []
        for index, left in enumerate(courses):
            for right in courses[index + 1 :]:
                if self._overlaps(left, right):
                    conflicts.append((left, right))
        return conflicts

    def _overlaps(self, left: CourseWindow, right: CourseWindow) -> bool:
        if left.start_day_of_week_utc != right.start_day_of_week_utc:
            return False
        return not (
            left.end_time_utc <= right.start_time_utc or right.end_time_utc <= left.start_time_utc
        )
