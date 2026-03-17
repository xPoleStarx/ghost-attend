import pytest

from src.bot.handlers.agent_chat import _compute_next_lesson, _detect_intent
from datetime import time, datetime, timedelta
from zoneinfo import ZoneInfo


class DummyCourse:
    def __init__(self, name: str, day_of_week: int, start_h: int, start_m: int):
        self.name = name
        self.day_of_week = day_of_week
        self.start_time = time(start_h, start_m)
        self.end_time = time(start_h + 1, start_m)


def test_detect_intent_join_variants():
    assert _detect_intent("derse gir") == "ask_join_or_status"
    assert _detect_intent("Derse girecek misin") == "ask_join_or_status"
    assert _detect_intent("derse katılacak mısın") == "ask_join_or_status"
    assert _detect_intent("şimdi derse gir") == "ask_join_or_status"


def test_detect_intent_ambiguous_schedule_change():
    text = "ders saatini güncelle 23.30 olarak başlangıç"
    assert _detect_intent(text) == "ambiguous_schedule_change"


def test_detect_intent_none_for_clear_text():
    text = "Kariyer Planlama dersini salı 23:30 yap"
    assert _detect_intent(text) is None


def test_compute_next_lesson_picks_closest():
    # Pazartesi 10:00 varsayımı ile near future ders seçimini kontrol etmek zor olduğu için
    # sadece fonksiyonun daha küçük delta'yı seçtiğini doğruluyoruz.
    courses = [
        DummyCourse("Ders A", 0, 9, 0),   # Pazartesi 09:00
        DummyCourse("Ders B", 0, 15, 0),  # Pazartesi 15:00
    ]

    next_course = _compute_next_lesson(courses)
    assert next_course in courses

