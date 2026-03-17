"""
GhostAttend — Scheduler & Notification Unit Tests
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import time

from src.scheduler.lesson_scheduler import _parse_time, _get_cron_day_of_week


class TestParseTime:
    """Saat parse testleri."""

    def test_parse_morning(self):
        result = _parse_time("09:00")
        assert result == time(9, 0)

    def test_parse_afternoon(self):
        result = _parse_time("14:30")
        assert result == time(14, 30)

    def test_parse_midnight(self):
        result = _parse_time("00:00")
        assert result == time(0, 0)

    def test_parse_end_of_day(self):
        result = _parse_time("23:59")
        assert result == time(23, 59)


class TestGetCronDayOfWeek:
    """Türkçe gün → cron dönüşüm testleri."""

    def test_pazartesi(self):
        assert _get_cron_day_of_week("Pazartesi") == "mon"

    def test_sali(self):
        assert _get_cron_day_of_week("Salı") == "tue"

    def test_carsamba(self):
        assert _get_cron_day_of_week("Çarşamba") == "wed"

    def test_persembe(self):
        assert _get_cron_day_of_week("Perşembe") == "thu"

    def test_cuma(self):
        assert _get_cron_day_of_week("Cuma") == "fri"

    def test_cumartesi(self):
        assert _get_cron_day_of_week("Cumartesi") == "sat"

    def test_pazar(self):
        assert _get_cron_day_of_week("Pazar") == "sun"

    def test_unknown_defaults_mon(self):
        assert _get_cron_day_of_week("InvalidDay") == "mon"


class TestNotificationService:
    """NotificationService testleri."""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_message(123, "Test mesajı")

        assert result is True
        mock_bot.send_message.assert_called_once_with(
            chat_id=123,
            text="Test mesajı",
            parse_mode="Markdown",
        )

    @pytest.mark.asyncio
    async def test_send_message_failure(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        mock_bot.send_message.side_effect = Exception("API error")
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_message(123, "Test")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_screenshot(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_screenshot(
            user_id=123,
            screenshot_bytes=b"fake_png_data",
            caption="Test screenshot",
        )

        assert result is True
        mock_bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_error_known_code(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_error(123, "DYS_LOGIN_FAILED")

        assert result is True
        call_text = mock_bot.send_message.call_args[1]["text"]
        assert "DYS" in call_text
        assert "/reauth" in call_text

    @pytest.mark.asyncio
    async def test_send_lesson_reminder(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_lesson_reminder(123, "Fizik", "14:00")

        assert result is True
        call_text = mock_bot.send_message.call_args[1]["text"]
        assert "Fizik" in call_text
        assert "14:00" in call_text

    @pytest.mark.asyncio
    async def test_send_daily_summary(self):
        from src.notifications.service import NotificationService

        mock_bot = AsyncMock()
        service = NotificationService(bot_token="fake", bot=mock_bot)

        result = await service.send_daily_summary(
            user_id=123,
            completed=["Fizik", "Matematik"],
            failed=["İngilizce"],
            upcoming=["Kimya"],
        )

        assert result is True
        call_text = mock_bot.send_message.call_args[1]["text"]
        assert "Fizik" in call_text
        assert "İngilizce" in call_text
        assert "Kimya" in call_text
