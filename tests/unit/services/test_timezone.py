from app.services.timezone import TimezoneNormalizer


def test_timezone_normalizer_converts_local_course_window_to_utc() -> None:
    normalizer = TimezoneNormalizer()

    normalized = normalizer.normalize_course_window(
        day_of_week="MONDAY",
        start_local="14:00",
        end_local="15:30",
        timezone_name="Europe/Istanbul",
    )

    assert normalized.start_day_of_week_utc == "MONDAY"
    assert normalized.start_time_utc == "11:00"
    assert normalized.end_time_utc == "12:30"
