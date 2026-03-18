import pytest

from src.scheduler.tasks import AttendLessonTaskFailed, attend_lesson_task


def test_attend_lesson_task_returns_completed(monkeypatch):
    monkeypatch.setattr(
        "src.scheduler.tasks._run_async",
        lambda coro: {"status": "completed", "raw": "ok"},
    )

    result = attend_lesson_task.run(
        user_id=1,
        course_id="11111111-1111-1111-1111-111111111111",
        course_name="Test",
        dys_url="https://dys",
        end_time="10:00",
    )

    assert result["status"] == "completed"


def test_attend_lesson_task_returns_cancelled(monkeypatch):
    monkeypatch.setattr(
        "src.scheduler.tasks._run_async",
        lambda coro: {"status": "cancelled"},
    )

    result = attend_lesson_task.run(
        user_id=1,
        course_id="11111111-1111-1111-1111-111111111111",
        course_name="Test",
        dys_url="https://dys",
        end_time="10:00",
    )

    assert result["status"] == "cancelled"


@pytest.mark.parametrize("status", ["max_retry_exceeded", "fatal_error", "error", "mfa_timeout"])
def test_attend_lesson_task_raises_for_business_failures(monkeypatch, status):
    monkeypatch.setattr(
        "src.scheduler.tasks._run_async",
        lambda coro: {"status": status, "scenario": "test_failure"},
    )

    with pytest.raises(AttendLessonTaskFailed):
        attend_lesson_task.run(
            user_id=1,
            course_id="11111111-1111-1111-1111-111111111111",
            course_name="Test",
            dys_url="https://dys",
            end_time="10:00",
        )
