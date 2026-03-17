from types import SimpleNamespace
from datetime import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_manual_join_happy_path(monkeypatch):
    """
    \"sürdürülebilirlik dersine şimdi gir\" isteği:
    - manual_join_request intent'ine düşmeli,
    - tek eşleşen ders için DOĞRUDAN attend_lesson_task.delay çağrılmalı,
    - ekstra \"Evet, şimdi gir\" onayı gerekmemeli.
    """
    from src.bot.handlers import agent_chat

    # Dummy course modeli
    class DummyCourse:
        def __init__(self):
            self.id = "11111111-1111-1111-1111-111111111111"
            self.name = "Sürdürülebilirlik"
            self.day_of_week = 2
            self.start_time = time(0, 19)
            self.end_time = time(1, 19)
            self.platform = "teams"
            self.direct_url = "https://example.com"
            self.dys_search_hint = None
            self.is_online = True
            self.is_active = True

    dummy_course = DummyCourse()

    # get_session stub
    fake_session = MagicMock()

    async def fake_get_session():
        class _Ctx:
            async def __aenter__(self_inner):
                return fake_session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    monkeypatch.setattr("src.bot.handlers.agent_chat.get_session", fake_get_session, raising=False)

    # Credential repo stub
    class FakeCredRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CredentialRepository",
        lambda session: FakeCredRepo(),
        raising=False,
    )

    # Course repo stub
    class FakeCourseRepo:
        def __init__(self, _session):
            self._session = _session

        async def get_user_courses(self, user_id: int, active_only: bool = True):
            return [dummy_course]

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            return [dummy_course]

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CourseRepository",
        lambda session: FakeCourseRepo(session),
        raising=False,
    )

    sent_messages = []

    class FakeMessage:
        def __init__(self, text: str):
            self.text = text

        async def reply_text(self, text, parse_mode=None):
            sent_messages.append((text, parse_mode))

        async def delete(self):
            # processing mesajı için kullanılıyor, burada no-op
            pass

    class FakeChat:
        id = 123

    class FakeUpdate:
        def __init__(self, text: str):
            self.effective_user = SimpleNamespace(id=123)
            self.effective_chat = FakeChat()
            self.message = FakeMessage(text)

    class FakeContext:
        def __init__(self):
            self.bot_data = {}
            self.user_data = {}

    # 1) İlk mesaj: manuel join isteği
    update1 = FakeUpdate("sürdürülebilirlik dersine şimdi gir")
    context = FakeContext()

    # attend_lesson_task.delay'i stub'la
    fake_task = AsyncMock()
    fake_task.delay = MagicMock()

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.attend_lesson_task",
        fake_task,
        raising=False,
    )

    await agent_chat.handle_agent_chat(update1, context)

    # Celery task tek seferde tetiklenmiş olmalı
    fake_task.delay.assert_called_once()
    args, kwargs = fake_task.delay.call_args
    assert kwargs["user_id"] == 123
    assert kwargs["course_id"] == dummy_course.id
    assert kwargs["course_name"] == "Sürdürülebilirlik"
    assert kwargs["dys_url"] == "https://dys.example.com"
    assert kwargs["end_time"] == "01:19"
    assert kwargs["direct_url"] == dummy_course.direct_url
    assert kwargs["dys_search_hint"] is None

    # pending_manual_join kullanılmamalı
    assert "pending_manual_join" not in context.user_data


@pytest.mark.asyncio
async def test_manual_join_via_start_manual_session_tool(monkeypatch):
    """
    LLM'den gelen start_manual_session tool çağrısı:
    - hedef dersi bulmalı,
    - attend_lesson_task.delay çağırmalı,
    - pending_manual_join kullanmamalı.
    """
    from src.bot.handlers import agent_chat

    class DummyCourse:
        def __init__(self):
            self.id = "22222222-2222-2222-2222-222222222222"
            self.name = "Kariyer Planlama"
            self.day_of_week = 2
            self.start_time = time(0, 36)
            self.end_time = time(1, 21)
            self.platform = "teams"
            self.direct_url = "https://example.com/kariyer"
            self.dys_search_hint = "Kariyer Planlama"
            self.is_online = True
            self.is_active = True

    dummy_course = DummyCourse()

    fake_session = MagicMock()

    async def fake_get_session():
        class _Ctx:
            async def __aenter__(self_inner):
                return fake_session

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.get_session",
        fake_get_session,
        raising=False,
    )

    class FakeCredRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CredentialRepository",
        lambda session: FakeCredRepo(),
        raising=False,
    )

    class FakeCourseRepo:
        def __init__(self, _session):
            self._session = _session

        async def get_user_courses(self, user_id: int, active_only: bool = True):
            return [dummy_course]

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            return [dummy_course]

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CourseRepository",
        lambda session: FakeCourseRepo(session),
        raising=False,
    )

    sent_messages = []

    class FakeMessage:
        def __init__(self, text: str):
            self.text = text

        async def reply_text(self, text, parse_mode=None):
            sent_messages.append((text, parse_mode))

        async def delete(self):
            pass

    class FakeChat:
        id = 123

    class FakeUpdate:
        def __init__(self, text: str):
            self.effective_user = SimpleNamespace(id=123)
            self.effective_chat = FakeChat()
            self.message = FakeMessage(text)

    class FakeContext:
        def __init__(self):
            self.bot_data = {}
            self.user_data = {}

    # LLM cevabını stub'la: start_manual_session çağrısı
    async def fake_call_llm(provider, model, system_prompt, user_text):
        return """
```json
{
  "action": "tool",
  "tool": "start_manual_session",
  "args": {
    "course_name_query": "Kariyer Planlama"
  },
  "message": "Tamam, Kariyer Planlama dersi için hemen derse katılım oturumu başlatıyorum."
}
```"""

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat._call_llm",
        fake_call_llm,
        raising=False,
    )

    fake_task = AsyncMock()
    fake_task.delay = MagicMock()

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.attend_lesson_task",
        fake_task,
        raising=False,
    )

    update = FakeUpdate("Kariyer Planlama dersine şimdi katıl")
    context = FakeContext()

    await agent_chat.handle_agent_chat(update, context)

    fake_task.delay.assert_called_once()
    args, kwargs = fake_task.delay.call_args
    assert kwargs["user_id"] == 123
    assert kwargs["course_id"] == dummy_course.id
    assert kwargs["course_name"] == "Kariyer Planlama"
    assert kwargs["dys_url"] == "https://dys.example.com"
    assert kwargs["end_time"] == "01:21"
    assert kwargs["direct_url"] == dummy_course.direct_url
    assert kwargs["dys_search_hint"] == dummy_course.dys_search_hint

    assert "pending_manual_join" not in context.user_data

