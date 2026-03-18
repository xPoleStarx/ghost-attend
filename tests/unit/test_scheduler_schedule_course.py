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


@pytest.mark.asyncio
async def test_schedule_course_rolls_back_to_previous_day_when_t_minus_five_crosses_midnight(monkeypatch):
    dummy = DummyScheduler()

    monkeypatch.setattr(lesson_scheduler, "get_scheduler", lambda: dummy)

    await lesson_scheduler.schedule_course(
        user_id=1,
        course_id="course-uuid",
        course_name="Gece Dersi",
        day="Pazartesi",
        start_time="00:03",
        end_time="01:00",
        dys_url="https://dys.example.com",
        early_minutes=5,
        timezone_name="America/New_York",
    )

    trigger = dummy.jobs[0]["trigger"]
    assert trigger.hour == 23
    assert trigger.minute == 58
    assert str(trigger.fields[4]) == "sun"
