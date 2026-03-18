from __future__ import annotations

from datetime import time
from types import SimpleNamespace

import pytest

from src.scheduler import lesson_scheduler


@pytest.mark.asyncio
async def test_schedule_all_courses_for_user_passes_user_timezone(monkeypatch):
    scheduled_calls: list[dict] = []

    async def fake_schedule_course(**kwargs):
        scheduled_calls.append(kwargs)
        return "job-1"

    class FakeCourseRepo:
        async def get_user_courses(self, user_id: int, active_only: bool = True):
            return [
                SimpleNamespace(
                    id="course-1",
                    name="Fizik",
                    day_of_week=0,
                    start_time=time(9, 0),
                    end_time=time(10, 0),
                    direct_url=None,
                    dys_search_hint="Fizik",
                    is_online=True,
                )
            ]

    class FakeCredentialRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    class FakeUserRepo:
        async def get_by_id(self, user_id: int):
            return SimpleNamespace(timezone="America/New_York")

    class FakeScheduler:
        running = True

        def get_jobs(self):
            return []

    class SessionCtx:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(lesson_scheduler, "get_scheduler", lambda: FakeScheduler())
    monkeypatch.setattr(lesson_scheduler, "schedule_course", fake_schedule_course)
    monkeypatch.setattr("src.db.connection.get_session", lambda: SessionCtx())
    monkeypatch.setattr("src.db.repositories.user.UserRepository", lambda session: FakeUserRepo())
    monkeypatch.setattr("src.db.repositories.course.CourseRepository", lambda session: FakeCourseRepo())
    monkeypatch.setattr("src.db.repositories.credential.CredentialRepository", lambda session: FakeCredentialRepo())

    job_ids = await lesson_scheduler.schedule_all_courses_for_user(1)

    assert job_ids == ["job-1"]
    assert scheduled_calls
    assert scheduled_calls[0]["timezone_name"] == "America/New_York"
