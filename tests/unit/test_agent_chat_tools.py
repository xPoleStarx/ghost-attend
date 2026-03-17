"""
GhostAttend — Agent Chat Tool Tests

Yeni agentic chat tool'ları için unit seviyesinde davranış testleri.
"""

from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.bot.handlers.agent_chat import _compute_next_lesson


class DummyCourse:
    """_compute_next_lesson için basit ders modeli."""

    def __init__(self, name: str, day_of_week: int, start_time: time, end_time: time):
        self.name = name
        self.day_of_week = day_of_week
        self.start_time = start_time
        self.end_time = end_time


def test_compute_next_lesson_selects_closest_future(monkeypatch):
    """_compute_next_lesson şu andan sonraki en yakın dersi seçmeli."""
    # Pazartesi 10:00 olarak sabitle
    fake_now = SimpleNamespace(hour=10, minute=0, weekday=lambda: 0)

    class FakeDateTime:
        @staticmethod
        def now():
            return fake_now

        @staticmethod
        def weekday():
            return fake_now.weekday()

    monkeypatch.setattr("src.bot.handlers.agent_chat.datetime", FakeDateTime)

    courses = [
        DummyCourse("Ders1", day_of_week=0, start_time=time(9, 0), end_time=time(10, 0)),   # Geçmiş (aynı gün)
        DummyCourse("Ders2", day_of_week=0, start_time=time(11, 0), end_time=time(12, 0)),  # Aynı gün, ileride
        DummyCourse("Ders3", day_of_week=2, start_time=time(9, 0), end_time=time(10, 0)),   # Daha uzak
    ]

    next_course = _compute_next_lesson(courses)
    assert next_course is not None
    assert next_course.name == "Ders2"


@pytest.mark.asyncio
async def test_agent_chat_get_next_lesson_tool_flow(monkeypatch):
    """
    "en yakın ders hangi ders" benzeri bir istek geldiğinde
    LLM'den get_next_lesson tool'unu seçen bir JSON döndüğünde,
    handler'ın anlamlı bir yanıt üretip hata vermemesi gerekir.
    """
    from src.bot.handlers import agent_chat

    fake_json = {
        "action": "tool",
        "tool": "get_next_lesson",
        "args": {},
        "message": "En yakın dersi söylüyorum.",
    }

    # LLM çağrısını stub'la
    monkeypatch.setattr(
        agent_chat,
        "_call_llm",
        AsyncMock(return_value='```json\n' + __import__("json").dumps(fake_json) + "\n```"),
    )

    # Dummy course
    dummy_course = DummyCourse(
        "Kariyer Planlama",
        day_of_week=0,
        start_time=time(22, 22),
        end_time=time(23, 0),
    )

    # DB repository'lerini stub'la
    fake_session = MagicMock()
    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.get_session",
        lambda: AsyncMock().__aenter__.return_value.__aenter__.return_value,
        raising=False,
    )

    # update / context objeleri için basit stub
    sent_messages = []

    class FakeMessage:
        text = "en yakın ders hangi ders"

        async def reply_text(self, text, parse_mode=None):
            sent_messages.append((text, parse_mode))

        async def delete(self):
            pass

    class FakeChat:
        id = 123

    class FakeUpdate:
        effective_user = SimpleNamespace(id=123)
        effective_chat = FakeChat()
        message = FakeMessage()

    class FakeContext:
        bot_data = {}
        user_data = {}

    # handle_agent_chat içindeki DB çağrılarını minimal stub'larla patch'lemek
    async def fake_get_session():
        class _Ctx:
            async def __aenter__(self_inner):
                return fake_session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    monkeypatch.setattr("src.bot.handlers.agent_chat.get_session", fake_get_session, raising=False)

    from src.db.repositories.course import CourseRepository

    fake_repo = MagicMock(spec=CourseRepository)
    fake_repo.get_user_courses = AsyncMock(return_value=[dummy_course])

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CourseRepository",
        lambda session: fake_repo,
        raising=False,
    )

    await agent_chat.handle_agent_chat(FakeUpdate(), FakeContext())

    # Mesaj gerçekten üretildi mi?
    assert sent_messages, "Herhangi bir cevap üretilmedi."
    assert "Kariyer Planlama" in sent_messages[0][0]

