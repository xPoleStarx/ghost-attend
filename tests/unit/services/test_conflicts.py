from app.services.conflicts import CourseWindow, ScheduleConflictDetector


def test_conflict_detector_finds_overlap() -> None:
    detector = ScheduleConflictDetector()
    conflicts = detector.find_conflicts(
        [
            CourseWindow(
                course_id=1,
                name="Kariyer Planlama",
                start_day_of_week_utc="MONDAY",
                start_time_utc="11:00",
                end_day_of_week_utc="MONDAY",
                end_time_utc="12:00",
            ),
            CourseWindow(
                course_id=2,
                name="Yazilim",
                start_day_of_week_utc="MONDAY",
                start_time_utc="11:30",
                end_day_of_week_utc="MONDAY",
                end_time_utc="12:30",
            ),
        ]
    )

    assert len(conflicts) == 1
    assert conflicts[0][0].name == "Kariyer Planlama"
    assert conflicts[0][1].name == "Yazilim"
