from __future__ import annotations

from datetime import datetime, timezone

from src.scheduler import lesson_scheduler


class DummyJob:
    def __init__(self, job_id: str, name: str, next_run_time=None):
        self.id = job_id
        self.name = name
        self.next_run_time = next_run_time


class DummyScheduler:
    def __init__(self, jobs: list[DummyJob], *, running: bool = False):
        self._jobs = jobs
        self.running = running
        self.started_with_paused: bool | None = None
        self.shutdown_called = False

    def start(self, paused: bool = False):
        self.started_with_paused = paused
        self.running = True

    def shutdown(self, wait: bool = True):
        self.shutdown_called = True
        self.running = False

    def get_jobs(self):
        return list(self._jobs)


def test_get_user_jobs_starts_and_shuts_down_when_not_running(monkeypatch):
    dummy = DummyScheduler(
        jobs=[
            DummyJob(
                "course_1_abc",
                "Test (Salı 10:00)",
                next_run_time=datetime(2026, 3, 18, 10, 0, tzinfo=timezone.utc),
            )
        ],
        running=False,
    )

    monkeypatch.setattr(lesson_scheduler, "get_scheduler", lambda: dummy)

    jobs = lesson_scheduler.get_user_jobs(1)

    assert dummy.started_with_paused is True
    assert dummy.shutdown_called is True
    assert jobs and jobs[0]["id"] == "course_1_abc"


def test_get_user_jobs_does_not_shutdown_when_already_running(monkeypatch):
    dummy = DummyScheduler(jobs=[DummyJob("course_1_abc", "Test")], running=True)
    monkeypatch.setattr(lesson_scheduler, "get_scheduler", lambda: dummy)

    lesson_scheduler.get_user_jobs(1)

    assert dummy.started_with_paused is None
    assert dummy.shutdown_called is False

