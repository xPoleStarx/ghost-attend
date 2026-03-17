"""
GhostAttend — Pydantic Model Unit Tests

Domain model validasyon testleri.
"""

import pytest
from pydantic import ValidationError

from src.core.models import ParsedCourse, ScheduleParseResult, CourseInfo, CheckpointEvent


class TestParsedCourse:
    """ParsedCourse model testleri."""

    def test_valid_course(self):
        """Geçerli ders parse edilmeli."""
        course = ParsedCourse(
            ders_adi="Kariyer Planlama",
            gun="Pazartesi",
            baslangic_saati="09:00",
            bitis_saati="10:30",
            ogretim_uyesi="Dr. Ahmet Yılmaz",
            platform="teams",
            online_mi=True,
            guvven_skoru=0.95,
        )
        assert course.ders_adi == "Kariyer Planlama"
        assert course.gun == "Pazartesi"
        assert course.platform == "teams"

    def test_invalid_day(self):
        """Geçersiz gün Literal hatası vermeli."""
        with pytest.raises(ValidationError):
            ParsedCourse(
                ders_adi="Test",
                gun="InvalidDay",
                baslangic_saati="09:00",
                bitis_saati="10:30",
                guvven_skoru=0.5,
            )

    def test_invalid_platform(self):
        """Geçersiz platform hatası vermeli."""
        with pytest.raises(ValidationError):
            ParsedCourse(
                ders_adi="Test",
                gun="Pazartesi",
                baslangic_saati="09:00",
                bitis_saati="10:30",
                platform="discord",
                guvven_skoru=0.5,
            )

    def test_confidence_score_bounds(self):
        """Güven skoru 0-1 arasında olmalı."""
        with pytest.raises(ValidationError):
            ParsedCourse(
                ders_adi="Test",
                gun="Pazartesi",
                baslangic_saati="09:00",
                bitis_saati="10:30",
                guvven_skoru=1.5,
            )

        with pytest.raises(ValidationError):
            ParsedCourse(
                ders_adi="Test",
                gun="Pazartesi",
                baslangic_saati="09:00",
                bitis_saati="10:30",
                guvven_skoru=-0.1,
            )

    def test_optional_fields(self):
        """Opsiyonel alanlar None olabilmeli."""
        course = ParsedCourse(
            ders_adi="Test",
            gun="Salı",
            baslangic_saati="09:00",
            bitis_saati="10:30",
            guvven_skoru=0.8,
        )
        assert course.ogretim_uyesi is None
        assert course.online_mi is None
        assert course.platform == "unknown"


class TestScheduleParseResult:
    """ScheduleParseResult model testleri."""

    def test_valid_result(self, sample_courses):
        """Geçerli parse sonucu oluşturulabilmeli."""
        result = ScheduleParseResult(
            courses=[ParsedCourse(**c) for c in sample_courses],
            raw_text="Ders programından okunan metin",
        )
        assert len(result.courses) == 3
        assert result.parse_warnings == []

    def test_with_warnings(self):
        """Uyarılarla birlikte sonuç oluşturulabilmeli."""
        result = ScheduleParseResult(
            courses=[],
            raw_text="Boş program",
            parse_warnings=["Hiç ders bulunamadı"],
        )
        assert len(result.parse_warnings) == 1


class TestCheckpointEvent:
    """CheckpointEvent model testleri."""

    def test_minimal_checkpoint(self):
        """Minimum alanlarla checkpoint oluşturulabilmeli."""
        event = CheckpointEvent(checkpoint_name="dys_login")
        assert event.checkpoint_name == "dys_login"
        assert event.screenshot_path is None
        assert event.metadata == {}

    def test_full_checkpoint(self):
        """Tüm alanlarla checkpoint oluşturulabilmeli."""
        event = CheckpointEvent(
            checkpoint_name="derse_girildi",
            screenshot_path="/app/screenshots/123.png",
            message="Derse başarıyla katıldın!",
            metadata={"step": 5, "url": "https://teams.microsoft.com/meeting/123"},
        )
        assert event.screenshot_path == "/app/screenshots/123.png"
        assert event.metadata["step"] == 5
