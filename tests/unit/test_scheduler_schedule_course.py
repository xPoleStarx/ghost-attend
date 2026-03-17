import pytest

from src.scheduler import lesson_scheduler


class DummyScheduler:
    def __init__(self):
        self.jobs = []

    def get_job(self, job_id):
        return None

    def add_job(self, func, trigger, id, name, kwargs, replace_existing=True):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "id": id,
                "name": name,
                "kwargs": kwargs,
            }
        )


@pytest.mark.asyncio
async def test_schedule_course_uses_early_minutes_offset(monkeypatch):
    dummy = DummyScheduler()

    monkeypatch.setattr(lesson_scheduler, "get_scheduler", lambda: dummy)

    job_id = await lesson_scheduler.schedule_course(
        user_id=1,
        course_id="course-uuid",
        course_name="Test Ders",
        day="Salı",
        start_time="10:00",
        end_time="11:00",
        dys_url="https://dys.example.com",
        direct_url=None,
        dys_search_hint=None,
        early_minutes=5,
    )

    assert job_id == "course_1_course-uuid"
    assert len(dummy.jobs) == 1
    # CronTrigger ile saat/minute atanmış olmalı
    trigger = dummy.jobs[0]["trigger"]
    assert trigger.hour == 9
    assert trigger.minute == 55

