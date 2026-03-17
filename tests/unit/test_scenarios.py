"""
GhostAttend — Senaryo Matrisi Unit Tests

Senaryo tespiti, recovery action, retry logic, ve bildirim testleri.
"""

import pytest
from unittest.mock import AsyncMock

from src.agent.scenarios import (
    RecoveryAction,
    ScenarioConfig,
    ScenarioHandler,
    ScenarioType,
    SCENARIO_MATRIX,
)
from src.core.exceptions import (
    AgentJoinFailed,
    AgentLoginFailed,
    AgentLinkNotFound,
    AgentMFARequired,
    AgentPageFrozen,
    CookieExpired,
    MeetingNotStarted,
)


class TestScenarioDetection:
    """detect_scenario testleri."""

    def setup_method(self):
        self.handler = ScenarioHandler()

    def test_happy_path(self):
        result = self.handler.detect_scenario("Görev tamamlandı")
        assert result == ScenarioType.HAPPY_PATH

    def test_dys_login_fail(self):
        result = self.handler.detect_scenario("", AgentLoginFailed("test"))
        assert result == ScenarioType.DYS_LOGIN_FAIL

    def test_link_not_found(self):
        result = self.handler.detect_scenario("", AgentLinkNotFound("test"))
        assert result == ScenarioType.LINK_NOT_FOUND

    def test_mfa_sms(self):
        error = AgentMFARequired("sms")
        result = self.handler.detect_scenario("", error)
        assert result == ScenarioType.MFA_SMS

    def test_mfa_authenticator(self):
        error = AgentMFARequired("authenticator")
        result = self.handler.detect_scenario("", error)
        assert result == ScenarioType.MFA_AUTHENTICATOR

    def test_join_failed(self):
        result = self.handler.detect_scenario("", AgentJoinFailed("test"))
        assert result == ScenarioType.JOIN_FAILED

    def test_page_frozen(self):
        result = self.handler.detect_scenario("", AgentPageFrozen("test"))
        assert result == ScenarioType.PAGE_FROZEN

    def test_cookie_expired(self):
        result = self.handler.detect_scenario("", CookieExpired("test"))
        assert result == ScenarioType.COOKIE_EXPIRED

    def test_meeting_not_started(self):
        result = self.handler.detect_scenario("", MeetingNotStarted("test"))
        assert result == ScenarioType.MEETING_NOT_STARTED

    def test_network_error(self):
        result = self.handler.detect_scenario("", ConnectionError("timeout"))
        assert result == ScenarioType.NETWORK_ERROR

    def test_maintenance_from_text(self):
        result = self.handler.detect_scenario("Sistem şu anda bakım modundadır")
        assert result == ScenarioType.DYS_MAINTENANCE

    def test_session_kicked_from_text(self):
        result = self.handler.detect_scenario("kicked from meeting")
        assert result == ScenarioType.SESSION_KICKED


class TestScenarioRetry:
    """Retry logic testleri."""

    def setup_method(self):
        self.handler = ScenarioHandler()

    def test_should_retry_page_frozen(self):
        assert self.handler.should_retry(ScenarioType.PAGE_FROZEN) is True

    def test_should_not_retry_after_max(self):
        config = SCENARIO_MATRIX[ScenarioType.PAGE_FROZEN]
        for _ in range(config.max_retries):
            self.handler.increment_retry(ScenarioType.PAGE_FROZEN)
        assert self.handler.should_retry(ScenarioType.PAGE_FROZEN) is False

    def test_increment_retry_returns_count(self):
        assert self.handler.increment_retry(ScenarioType.JOIN_FAILED) == 1
        assert self.handler.increment_retry(ScenarioType.JOIN_FAILED) == 2

    def test_reset_retries(self):
        self.handler.increment_retry(ScenarioType.PAGE_FROZEN)
        self.handler.increment_retry(ScenarioType.JOIN_FAILED)
        self.handler.reset_retries()
        assert self.handler.should_retry(ScenarioType.PAGE_FROZEN) is True
        assert self.handler.should_retry(ScenarioType.JOIN_FAILED) is True

    def test_meeting_not_started_high_retries(self):
        """Toplantı başlamamışsa 5 kez dene."""
        config = SCENARIO_MATRIX[ScenarioType.MEETING_NOT_STARTED]
        assert config.max_retries == 5
        assert config.retry_delay_seconds == 60


class TestScenarioConfig:
    """SCENARIO_MATRIX yapılandırma testleri."""

    def test_all_scenarios_have_config(self):
        for scenario_type in ScenarioType:
            assert scenario_type in SCENARIO_MATRIX, f"Missing config for {scenario_type}"

    def test_fatal_scenarios(self):
        """Fatal senaryolar doğru işaretlenmiş mi?"""
        assert SCENARIO_MATRIX[ScenarioType.DYS_LOGIN_FAIL].is_fatal is True
        assert SCENARIO_MATRIX[ScenarioType.PAGE_FROZEN].is_fatal is False

    def test_mfa_scenarios_request_mfa(self):
        """MFA senaryoları REQUEST_MFA action'ı kullanmalı."""
        assert SCENARIO_MATRIX[ScenarioType.MFA_SMS].recovery_action == RecoveryAction.REQUEST_MFA
        assert SCENARIO_MATRIX[ScenarioType.MFA_AUTHENTICATOR].recovery_action == RecoveryAction.REQUEST_MFA

    def test_cookie_expired_relogin(self):
        """Cookie expired RELOGIN action'ı kullanmalı."""
        assert SCENARIO_MATRIX[ScenarioType.COOKIE_EXPIRED].recovery_action == RecoveryAction.RELOGIN


class TestScenarioNotification:
    """Bildirim formatı testleri."""

    def setup_method(self):
        self.handler = ScenarioHandler()

    def test_format_happy_path(self):
        msg = self.handler.format_notification(ScenarioType.HAPPY_PATH, "Fizik")
        assert "Fizik" in msg
        assert "✅" in msg

    def test_format_login_fail(self):
        msg = self.handler.format_notification(ScenarioType.DYS_LOGIN_FAIL)
        assert "❌" in msg
        assert "/reauth" in msg

    def test_no_notification_for_silent_scenarios(self):
        msg = self.handler.format_notification(ScenarioType.PAGE_FROZEN)
        assert msg is None

    def test_format_with_retry_count(self):
        self.handler.increment_retry(ScenarioType.NETWORK_ERROR)
        msg = self.handler.format_notification(ScenarioType.NETWORK_ERROR)
        assert "1/5" in msg  # retry_count/max_retries


class TestRecoveryExecution:
    """execute_recovery testleri."""

    @pytest.mark.asyncio
    async def test_happy_path_continues(self):
        handler = ScenarioHandler()
        action = await handler.execute_recovery(ScenarioType.HAPPY_PATH, 123, "Test")
        assert action == RecoveryAction.CONTINUE

    @pytest.mark.asyncio
    async def test_fatal_scenario_aborts(self):
        handler = ScenarioHandler()
        # DYS login fail is fatal with max 1 retry
        handler.increment_retry(ScenarioType.DYS_LOGIN_FAIL)
        action = await handler.execute_recovery(ScenarioType.DYS_LOGIN_FAIL, 123)
        assert action == RecoveryAction.ABORT

    @pytest.mark.asyncio
    async def test_retry_increments_count(self):
        handler = ScenarioHandler()
        action = await handler.execute_recovery(ScenarioType.PAGE_FROZEN, 123)
        assert action in (RecoveryAction.RETRY, RecoveryAction.RETRY_WITH_DELAY)
        assert handler.retry_counts[ScenarioType.PAGE_FROZEN] == 1

    @pytest.mark.asyncio
    async def test_mfa_returns_request_mfa(self):
        handler = ScenarioHandler()
        action = await handler.execute_recovery(ScenarioType.MFA_SMS, 123)
        assert action == RecoveryAction.REQUEST_MFA
