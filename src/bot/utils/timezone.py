"""Timezone helpers shared by bot handlers."""

from __future__ import annotations

from zoneinfo import ZoneInfo


COMMON_TIMEZONES: list[tuple[str, str]] = [
    ("Europe/Istanbul", "Istanbul"),
    ("Europe/Berlin", "Berlin"),
    ("Europe/London", "London"),
    ("America/New_York", "New York"),
    ("America/Los_Angeles", "Los Angeles"),
]


def normalize_timezone_name(value: str) -> str:
    """Normalize user-provided timezone text."""
    return (value or "").strip().replace(" ", "_")


def is_valid_timezone(value: str) -> bool:
    """Return whether the timezone name is a valid IANA timezone."""
    try:
        ZoneInfo(normalize_timezone_name(value))
    except Exception:
        return False
    return True
