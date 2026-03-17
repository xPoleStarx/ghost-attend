"""
GhostAttend — Agent Runner Unit Tests

AgentRunner result parsing ve hata yönetimi testleri.
(Gerçek browser çalıştırmadan, mock ile)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.runner import AgentRunner
from src.core.exceptions import (
    AgentJoinFailed,
    AgentLoginFailed,
    AgentLinkNotFound,
    AgentMaxRetryExceeded,
    AgentMFARequired,
    AgentPageFrozen,
    CookieExpired,
    MeetingNotStarted,
)


class TestAgentRunnerParseResult:
    """_parse_result metod testleri."""

    def setup_method(self):
        self.runner = AgentRunner(
            session_id="test-session",
            user_id=123,
        )

    def test_successful_result(self):
        result = self.runner._parse_result("Görev başarılı.")
        assert result["status"] == "completed"
        assert "başarılı" in result["raw"]

    def test_dys_login_failed(self):
        with pytest.raises(AgentLoginFailed):
            self.runner._parse_result("HATA_KODU: DYS_LOGIN_FAILED")

    def test_link_not_found(self):
        with pytest.raises(AgentLinkNotFound):
            self.runner._parse_result("HATA_KODU: LINK_NOT_FOUND")

    def test_mfa_required(self):
        with pytest.raises(AgentMFARequired):
            self.runner._parse_result("HATA_KODU: MFA_REQUIRED")

    def test_join_failed(self):
        with pytest.raises(AgentJoinFailed):
            self.runner._parse_result("HATA_KODU: JOIN_FAILED")

    def test_page_frozen(self):
        with pytest.raises(AgentPageFrozen):
            self.runner._parse_result("HATA_KODU: PAGE_FROZEN")

    def test_cookie_expired(self):
        with pytest.raises(CookieExpired):
            self.runner._parse_result("HATA_KODU: COOKIE_EXPIRED")

    def test_meeting_not_started(self):
        with pytest.raises(MeetingNotStarted):
            self.runner._parse_result("HATA_KODU: MEETING_NOT_STARTED")

    def test_error_in_middle_of_text(self):
        """Hata kodu metin içinde de tespit edilmeli."""
        with pytest.raises(AgentLoginFailed):
            self.runner._parse_result(
                "Adım 3 sonrası... HATA_KODU: DYS_LOGIN_FAILED ... devam"
            )

    def test_no_error_code(self):
        """Hata kodu olmayan sonuç başarılı sayılmalı."""
        result = self.runner._parse_result("Tüm adımlar tamamlandı.")
        assert result["status"] == "completed"


class TestAgentRunnerRetry:
    """run_with_retry metod testleri."""

    @pytest.mark.asyncio
    async def test_retry_on_page_frozen(self):
        """PAGE_FROZEN hatası retry'lanmalı."""
        runner = AgentRunner(session_id="t", user_id=1)

        call_count = 0

        async def mock_run(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise AgentPageFrozen("Sayfa dondu")
            return {"status": "completed", "raw": "ok"}

        runner.run = mock_run

        result = await runner.run_with_retry(
            max_retry=3,
            course_name="Test",
            end_time="10:00",
        )

        assert result["status"] == "completed"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_mfa_not_retried(self):
        """MFA hatası retry'lanMAMALI (kullanıcı müdahalesi gerekli)."""
        runner = AgentRunner(session_id="t", user_id=1)

        async def mock_run(**kwargs):
            raise AgentMFARequired("sms")

        runner.run = mock_run

        with pytest.raises(AgentMFARequired):
            await runner.run_with_retry(max_retry=3, course_name="Test", end_time="10:00")

    @pytest.mark.asyncio
    async def test_login_failed_not_retried(self):
        """Login hatası retry'lanMAMALI (şifre yanlışsa tekrar da yanlış)."""
        runner = AgentRunner(session_id="t", user_id=1)

        async def mock_run(**kwargs):
            raise AgentLoginFailed("DYS giriş başarısız")

        runner.run = mock_run

        with pytest.raises(AgentLoginFailed):
            await runner.run_with_retry(max_retry=3, course_name="Test", end_time="10:00")

    @pytest.mark.asyncio
    async def test_max_retry_exceeded(self):
        """Tüm retry'lar başarısız olursa AgentMaxRetryExceeded."""
        runner = AgentRunner(session_id="t", user_id=1)

        async def mock_run(**kwargs):
            raise AgentPageFrozen("Sayfa dondu")

        runner.run = mock_run

        with pytest.raises(AgentMaxRetryExceeded):
            await runner.run_with_retry(max_retry=2, course_name="Test", end_time="10:00")
