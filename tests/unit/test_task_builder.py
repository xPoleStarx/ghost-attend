"""
GhostAttend — Task Builder Unit Tests

Dinamik task string üretim testleri.
"""

import pytest

from src.agent.task_builder import (
    build_cookie_login_task,
    build_direct_url_task,
    build_dys_to_meeting_task,
)
from src.core.constants import (
    CHECKPOINT_COMPLETED,
    CHECKPOINT_DYS_LOGIN,
    CHECKPOINT_JOINED,
    CHECKPOINT_LINK_FOUND,
)


class TestBuildDirectUrlTask:
    """Direct URL task builder testleri."""

    def test_contains_course_name(self):
        task = build_direct_url_task("Kariyer Planlama", "https://teams.example.com/meet", "10:30")
        assert "Kariyer Planlama" in task

    def test_contains_url(self):
        url = "https://teams.microsoft.com/l/meetup-join/abc123"
        task = build_direct_url_task("Test", url, "10:30")
        assert url in task

    def test_contains_end_time(self):
        task = build_direct_url_task("Test", "https://example.com", "14:30")
        assert "14:30" in task

    def test_contains_checkpoints(self):
        task = build_direct_url_task("Test", "https://example.com", "10:30")
        assert CHECKPOINT_JOINED in task
        assert CHECKPOINT_COMPLETED in task

    def test_contains_safety_rules(self):
        task = build_direct_url_task("Test", "https://example.com", "10:30")
        assert "mikrofon" in task.lower()
        assert "kamera" in task.lower()
        assert "MFA_REQUIRED" in task


class TestBuildDysToMeetingTask:
    """DYS task builder testleri."""

    def test_contains_all_phases(self):
        task = build_dys_to_meeting_task(
            "Veri Yapıları", "https://obs.university.edu.tr",
            "test@edu.tr", "password123", "14:30",
        )
        assert "AŞAMA 1" in task
        assert "AŞAMA 2" in task
        assert "AŞAMA 3" in task
        assert "AŞAMA 4" in task

    def test_contains_credentials(self):
        task = build_dys_to_meeting_task(
            "Test", "https://obs.example.com",
            "user@test.edu.tr", "secret", "10:00",
        )
        assert "user@test.edu.tr" in task

    def test_contains_all_checkpoints(self):
        task = build_dys_to_meeting_task(
            "Test", "https://obs.example.com",
            "user", "pass", "10:00",
        )
        assert CHECKPOINT_DYS_LOGIN in task
        assert CHECKPOINT_LINK_FOUND in task
        assert CHECKPOINT_JOINED in task
        assert CHECKPOINT_COMPLETED in task

    def test_contains_dys_url(self):
        url = "https://obs.ege.edu.tr"
        task = build_dys_to_meeting_task("Test", url, "u", "p", "10:00")
        assert url in task

    def test_contains_search_hint(self):
        task = build_dys_to_meeting_task(
            "Kariyer", "https://obs.example.com",
            "u", "p", "10:00",
            dys_search_hint="KPL101",
        )
        assert "KPL101" in task

    def test_contains_error_codes(self):
        task = build_dys_to_meeting_task("T", "u", "u", "p", "10:00")
        assert "DYS_LOGIN_FAILED" in task
        assert "LINK_NOT_FOUND" in task
        assert "MFA_REQUIRED" in task
        assert "PAGE_FROZEN" in task


class TestBuildCookieLoginTask:
    """Cookie login task builder testleri."""

    def test_no_password_in_task(self):
        task = build_cookie_login_task(
            "Test", "https://obs.example.com", "10:00",
        )
        assert "password" not in task.lower()
        assert "şifre" not in task.lower()

    def test_contains_cookie_expired_error(self):
        task = build_cookie_login_task("Test", "https://obs.example.com", "10:00")
        assert "COOKIE_EXPIRED" in task

    def test_contains_checkpoints(self):
        task = build_cookie_login_task("Test", "https://obs.example.com", "10:00")
        assert CHECKPOINT_DYS_LOGIN in task
        assert CHECKPOINT_JOINED in task
        assert CHECKPOINT_COMPLETED in task
