from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class LoginEntry:
    url: str
    provider_hint: str | None = None


class UniversityAdapter(Protocol):
    async def resolve_login_entry(self, university_url: str) -> LoginEntry: ...
    async def navigate_to_course_area(self, user_id: int, course_name: str) -> None: ...
    async def extract_meeting_link(self, user_id: int, course_name: str) -> str | None: ...
    async def post_login_healthcheck(self, user_id: int) -> bool: ...


class GenericDysAdapter:
    async def resolve_login_entry(self, university_url: str) -> LoginEntry:
        return LoginEntry(url=university_url)

    async def navigate_to_course_area(self, user_id: int, course_name: str) -> None:
        _ = (user_id, course_name)

    async def extract_meeting_link(self, user_id: int, course_name: str) -> str | None:
        _ = (user_id, course_name)
        slug = course_name.lower().replace(" ", "-")
        return f"https://teams.microsoft.com/l/meetup-join/{slug}"

    async def post_login_healthcheck(self, user_id: int) -> bool:
        _ = user_id
        return True
