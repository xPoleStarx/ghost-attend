from __future__ import annotations

import re

from app.domain.schemas import CourseCandidate, ScheduleCandidate


DAY_ALIASES = {
    "monday": "MONDAY",
    "mon": "MONDAY",
    "pazartesi": "MONDAY",
    "tuesday": "TUESDAY",
    "tue": "TUESDAY",
    "salı": "TUESDAY",
    "sali": "TUESDAY",
    "wednesday": "WEDNESDAY",
    "wed": "WEDNESDAY",
    "çarşamba": "WEDNESDAY",
    "carsamba": "WEDNESDAY",
    "thursday": "THURSDAY",
    "thu": "THURSDAY",
    "perşembe": "THURSDAY",
    "persembe": "THURSDAY",
    "friday": "FRIDAY",
    "fri": "FRIDAY",
    "cuma": "FRIDAY",
    "saturday": "SATURDAY",
    "sat": "SATURDAY",
    "cumartesi": "SATURDAY",
    "sunday": "SUNDAY",
    "sun": "SUNDAY",
    "pazar": "SUNDAY",
}


class ScheduleParser:
    def parse_text(self, raw_text: str) -> ScheduleCandidate:
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        courses: list[CourseCandidate] = []
        warnings: list[str] = []
        for line in lines:
            parsed = self._parse_pipe_delimited(line) or self._parse_natural_language(line)
            if parsed is None:
                warnings.append(f"Could not parse line: {line}")
                continue
            courses.append(parsed)
        confidence = 0.0 if not courses else sum(item.confidence for item in courses) / len(courses)
        return ScheduleCandidate(
            courses=courses,
            warnings=warnings,
            needs_confirmation=True,
            confidence=confidence,
        )

    def _parse_pipe_delimited(self, line: str) -> CourseCandidate | None:
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 4:
            return None
        teams_link = parts[4] if len(parts) > 4 and parts[4] else None
        return CourseCandidate(
            name=parts[0],
            day_of_week=self._normalize_day(parts[1]),
            start_local=self._normalize_time(parts[2]),
            end_local=self._normalize_time(parts[3]),
            teams_link=teams_link,
            confidence=0.85 if teams_link else 0.7,
            source_fragment=line,
        )

    def _parse_natural_language(self, line: str) -> CourseCandidate | None:
        lowered = line.lower()
        day = self._extract_day(lowered)
        times = re.findall(r"\b(\d{1,2}[:.]\d{2})\b", line)
        if day is None or len(times) < 2:
            return None
        teams_link_match = re.search(r"https?://[^\s,]+", line, re.I)
        name = self._extract_course_name(line)
        teams_link = teams_link_match.group(0) if teams_link_match else None
        return CourseCandidate(
            name=name,
            day_of_week=day,
            start_local=self._normalize_time(times[0]),
            end_local=self._normalize_time(times[1]),
            teams_link=teams_link,
            confidence=0.82 if teams_link else 0.76,
            source_fragment=line,
        )

    def _extract_day(self, lowered: str) -> str | None:
        for alias, normalized in DAY_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered):
                return normalized
        return None

    def _extract_course_name(self, line: str) -> str:
        before_comma = line.split(",", maxsplit=1)[0].strip()
        if before_comma:
            return before_comma
        day_match = re.search(
            r"\b(?:her\s+)?(pazartesi|sal[ıi]|çarşamba|carsamba|perşembe|persembe|cuma|cumartesi|pazar|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
            line,
            re.I,
        )
        if day_match:
            return line[: day_match.start()].strip(" ,-")
        return line.strip()

    def _normalize_day(self, value: str) -> str:
        stripped = value.strip().lower()
        if stripped in DAY_ALIASES:
            return DAY_ALIASES[stripped]
        return stripped.upper()

    def _normalize_time(self, value: str) -> str:
        stripped = value.strip().replace(".", ":")
        hour, minute = stripped.split(":", maxsplit=1)
        return f"{int(hour):02d}:{int(minute):02d}"
