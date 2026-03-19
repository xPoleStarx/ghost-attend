from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


REFERENCE_WEEK = {
    "MONDAY": datetime(2026, 1, 5, tzinfo=UTC),
    "TUESDAY": datetime(2026, 1, 6, tzinfo=UTC),
    "WEDNESDAY": datetime(2026, 1, 7, tzinfo=UTC),
    "THURSDAY": datetime(2026, 1, 8, tzinfo=UTC),
    "FRIDAY": datetime(2026, 1, 9, tzinfo=UTC),
    "SATURDAY": datetime(2026, 1, 10, tzinfo=UTC),
    "SUNDAY": datetime(2026, 1, 11, tzinfo=UTC),
}


@dataclass(slots=True)
class NormalizedCourseTime:
    start_day_of_week_utc: str
    end_day_of_week_utc: str
    start_time_utc: str
    end_time_utc: str


class TimezoneNormalizer:
    def normalize_course_window(
        self,
        *,
        day_of_week: str,
        start_local: str,
        end_local: str,
        timezone_name: str,
    ) -> NormalizedCourseTime:
        if day_of_week not in REFERENCE_WEEK:
            msg = f"Unsupported day_of_week: {day_of_week}"
            raise ValueError(msg)
        zone = ZoneInfo(timezone_name)
        base_date = REFERENCE_WEEK[day_of_week].astimezone(zone).date()
        start_dt = datetime.fromisoformat(f"{base_date.isoformat()}T{start_local}:00").replace(tzinfo=zone)
        end_dt = datetime.fromisoformat(f"{base_date.isoformat()}T{end_local}:00").replace(tzinfo=zone)
        if end_dt <= start_dt:
            msg = "Course end time must be after start time."
            raise ValueError(msg)
        start_utc = start_dt.astimezone(UTC)
        end_utc = end_dt.astimezone(UTC)
        return NormalizedCourseTime(
            start_day_of_week_utc=start_utc.strftime("%A").upper(),
            end_day_of_week_utc=end_utc.strftime("%A").upper(),
            start_time_utc=start_utc.strftime("%H:%M"),
            end_time_utc=end_utc.strftime("%H:%M"),
        )
