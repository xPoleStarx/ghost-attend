"""
GhostAttend — Schedule Parser Unit Tests

Mock LLM response ile vision parser testleri.
architecture.md Section 15.2
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import ScheduleParseError
from src.core.models import ParsedCourse, ScheduleParseResult
from src.vision.schedule_parser import (
    _extract_json_block,
    format_courses_for_telegram,
    parse_schedule_image,
)


# ── Mock LLM Yanıtları ──

MOCK_VALID_RESPONSE = """
```json
{
  "courses": [
    {
      "ders_adi": "Kariyer Planlama",
      "gun": "Pazartesi",
      "baslangic_saati": "09:00",
      "bitis_saati": "10:30",
      "ogretim_uyesi": "Dr. Ahmet Yılmaz",
      "platform": "teams",
      "online_mi": true,
      "guvven_skoru": 0.95
    },
    {
      "ders_adi": "Veri Yapıları",
      "gun": "Salı",
      "baslangic_saati": "13:00",
      "bitis_saati": "14:30",
      "ogretim_uyesi": "Prof. Ayşe Kaya",
      "platform": "teams",
      "online_mi": true,
      "guvven_skoru": 0.90
    }
  ],
  "raw_text": "Ders programı görseli",
  "parse_warnings": []
}
```
"""

MOCK_WITH_WARNINGS = """
```json
{
  "courses": [
    {
      "ders_adi": "İngilizce",
      "gun": "Çarşamba",
      "baslangic_saati": "10:00",
      "bitis_saati": "11:30",
      "ogretim_uyesi": "Öğr. Gör. John Smith",
      "platform": "unknown",
      "online_mi": null,
      "guvven_skoru": 0.55
    }
  ],
  "raw_text": "Bulanık görsel",
  "parse_warnings": ["İngilizce dersinin platformu okunamadı", "Ders saatleri bulanık olabilir"]
}
```
"""

MOCK_EMPTY_COURSES = """
```json
{
  "courses": [],
  "raw_text": "Ders programı okunamadı",
  "parse_warnings": ["Görsel çok bulanık"]
}
```
"""

MOCK_BARE_JSON = """
{
  "courses": [
    {
      "ders_adi": "Fizik",
      "gun": "Perşembe",
      "baslangic_saati": "14:00",
      "bitis_saati": "15:30",
      "ogretim_uyesi": null,
      "platform": "zoom",
      "online_mi": true,
      "guvven_skoru": 0.80
    }
  ],
  "raw_text": "Fizik dersi",
  "parse_warnings": []
}
"""


# ── JSON Extraction Tests ──

class TestExtractJsonBlock:
    """_extract_json_block fonksiyon testleri."""

    def test_extract_from_markdown_block(self):
        """Markdown code block'tan JSON çıkarılmalı."""
        result = _extract_json_block(MOCK_VALID_RESPONSE)
        data = json.loads(result)
        assert "courses" in data
        assert len(data["courses"]) == 2

    def test_extract_bare_json(self):
        """Direkt JSON objesi çıkarılmalı."""
        result = _extract_json_block(MOCK_BARE_JSON)
        data = json.loads(result)
        assert data["courses"][0]["ders_adi"] == "Fizik"

    def test_extract_with_surrounding_text(self):
        """JSON öncesi/sonrası metin olsa bile çıkarılmalı."""
        text = "İşte sonuçlar:\n" + MOCK_BARE_JSON + "\n\nBu kadar."
        result = _extract_json_block(text)
        data = json.loads(result)
        assert "courses" in data

    def test_no_json_raises_error(self):
        """JSON bulunamazsa hata vermeli."""
        with pytest.raises(ScheduleParseError, match="JSON bloğu bulunamadı"):
            _extract_json_block("Bu geçerli JSON değil, sadece metin.")


# ── Parser Tests (Mock LLM) ──

class TestParseScheduleImage:
    """parse_schedule_image fonksiyon testleri."""

    @pytest.mark.asyncio
    async def test_parse_returns_valid_courses(self):
        """Geçerli yanıttan dersler doğru parse edilmeli."""
        with patch(
            "src.vision.schedule_parser._parse_with_google",
            new_callable=AsyncMock,
            return_value=MOCK_VALID_RESPONSE,
        ):
            result = await parse_schedule_image(b"fake_image", provider="google")

            assert isinstance(result, ScheduleParseResult)
            assert len(result.courses) == 2
            assert result.courses[0].ders_adi == "Kariyer Planlama"
            assert result.courses[0].online_mi is True
            assert result.courses[0].platform == "teams"
            assert result.courses[0].guvven_skoru == 0.95
            assert result.courses[1].ders_adi == "Veri Yapıları"

    @pytest.mark.asyncio
    async def test_parse_with_warnings(self):
        """Uyarılı dersler doğru parse edilmeli."""
        with patch(
            "src.vision.schedule_parser._parse_with_google",
            new_callable=AsyncMock,
            return_value=MOCK_WITH_WARNINGS,
        ):
            result = await parse_schedule_image(b"fake_image", provider="google")

            assert len(result.courses) == 1
            assert result.courses[0].online_mi is None
            assert result.courses[0].guvven_skoru == 0.55
            assert len(result.parse_warnings) == 2

    @pytest.mark.asyncio
    async def test_parse_empty_courses(self):
        """Boş ders listesi de geçerli sonuç olmalı."""
        with patch(
            "src.vision.schedule_parser._parse_with_google",
            new_callable=AsyncMock,
            return_value=MOCK_EMPTY_COURSES,
        ):
            result = await parse_schedule_image(b"fake_image", provider="google")

            assert len(result.courses) == 0
            assert len(result.parse_warnings) == 1

    @pytest.mark.asyncio
    async def test_parse_malformed_json(self):
        """Geçersiz JSON yanıtı hata vermeli."""
        with patch(
            "src.vision.schedule_parser._parse_with_google",
            new_callable=AsyncMock,
            return_value="Bu geçerli JSON değil, sadece düz metin.",
        ):
            with pytest.raises(ScheduleParseError):
                await parse_schedule_image(b"fake_image", provider="google")

    @pytest.mark.asyncio
    async def test_parse_invalid_provider(self):
        """Geçersiz provider hata vermeli."""
        with pytest.raises(ScheduleParseError, match="Desteklenmeyen LLM provider"):
            await parse_schedule_image(b"fake_image", provider="invalid_provider")

    @pytest.mark.asyncio
    async def test_parse_with_openai_provider(self):
        """OpenAI provider çağrılabilmeli."""
        with patch(
            "src.vision.schedule_parser._parse_with_openai",
            new_callable=AsyncMock,
            return_value=MOCK_VALID_RESPONSE,
        ):
            result = await parse_schedule_image(b"fake_image", provider="openai")
            assert len(result.courses) == 2

    @pytest.mark.asyncio
    async def test_parse_with_anthropic_provider(self):
        """Anthropic provider çağrılabilmeli."""
        with patch(
            "src.vision.schedule_parser._parse_with_anthropic",
            new_callable=AsyncMock,
            return_value=MOCK_VALID_RESPONSE,
        ):
            result = await parse_schedule_image(b"fake_image", provider="anthropic")
            assert len(result.courses) == 2


# ── Telegram Formatting Tests ──

class TestFormatCoursesForTelegram:
    """format_courses_for_telegram fonksiyon testleri."""

    def test_format_valid_courses(self):
        """Geçerli dersler düzgün formatlanmalı."""
        result = ScheduleParseResult(
            courses=[
                ParsedCourse(
                    ders_adi="Kariyer Planlama",
                    gun="Pazartesi",
                    baslangic_saati="09:00",
                    bitis_saati="10:30",
                    ogretim_uyesi="Dr. Ahmet Yılmaz",
                    platform="teams",
                    online_mi=True,
                    guvven_skoru=0.95,
                ),
            ],
            raw_text="test",
        )

        text = format_courses_for_telegram(result)
        assert "Kariyer Planlama" in text
        assert "Pazartesi" in text
        assert "09:00–10:30" in text
        assert "✅" in text

    def test_format_low_confidence(self):
        """Düşük güvenli dersler ❓ ile işaretlenmeli."""
        result = ScheduleParseResult(
            courses=[
                ParsedCourse(
                    ders_adi="Bulanık Ders",
                    gun="Cuma",
                    baslangic_saati="10:00",
                    bitis_saati="11:00",
                    platform="unknown",
                    online_mi=None,
                    guvven_skoru=0.4,
                ),
            ],
            raw_text="test",
        )

        text = format_courses_for_telegram(result)
        assert "❓" in text
        assert "Belirsiz" in text

    def test_format_empty_courses(self):
        """Boş ders listesi hata mesajı döndürmeli."""
        result = ScheduleParseResult(courses=[], raw_text="")
        text = format_courses_for_telegram(result)
        assert "hiç ders tespit edilemedi" in text

    def test_format_with_warnings(self):
        """Uyarılar mesajda görünmeli."""
        result = ScheduleParseResult(
            courses=[
                ParsedCourse(
                    ders_adi="Test",
                    gun="Salı",
                    baslangic_saati="09:00",
                    bitis_saati="10:00",
                    guvven_skoru=0.9,
                ),
            ],
            raw_text="test",
            parse_warnings=["Platform belirsiz"],
        )

        text = format_courses_for_telegram(result)
        assert "Uyarılar" in text
        assert "Platform belirsiz" in text
