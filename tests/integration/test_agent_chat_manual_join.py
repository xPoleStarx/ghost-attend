from datetime import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


class DummyCourse:
    def __init__(
        self,
        course_id: str,
        name: str,
        *,
        direct_url: str,
        dys_search_hint: str | None = None,
    ):
        self.id = course_id
        self.name = name
        self.day_of_week = 2
        self.start_time = time(0, 36)
        self.end_time = time(1, 21)
        self.platform = "teams"
        self.direct_url = direct_url
        self.dys_search_hint = dys_search_hint
        self.is_online = True
        self.is_active = True


class FakeMessage:
    def __init__(self, text: str, sent_messages: list[tuple[str, str | None]]):
        self.text = text
        self._sent_messages = sent_messages

    async def reply_text(self, text, parse_mode=None):
        self._sent_messages.append((text, parse_mode))

    async def delete(self):
        return None


class FakeUpdate:
    def __init__(self, text: str, sent_messages: list[tuple[str, str | None]]):
        self.effective_user = SimpleNamespace(id=123)
        self.effective_chat = SimpleNamespace(id=123)
        self.message = FakeMessage(text, sent_messages)


class FakeContext:
    def __init__(self):
        self.bot_data = {}
        self.user_data = {}


def _install_common_patches(monkeypatch, courses: list[DummyCourse]):
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

    class FakeUserRepo:
        async def get_by_id(self, user_id: int):
            return SimpleNamespace(timezone="Europe/Istanbul")

    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.UserRepository",
        lambda session: FakeUserRepo(),
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
            self.last_query = None

        async def get_user_courses(self, user_id: int, active_only: bool = True):
            return courses

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            self.last_query = query
            lowered = query.casefold()
            return [course for course in courses if any(token in course.name.casefold() for token in lowered.split())]

    repo = FakeCourseRepo(fake_session)
    monkeypatch.setattr(
        "src.bot.handlers.agent_chat.CourseRepository",
        lambda session: repo,
        raising=False,
    )
    return repo


def _install_fake_task(monkeypatch):
    class FakeTask:
        def __init__(self):
            self.calls = []

        def delay(self, **kwargs):
            self.calls.append(kwargs)

    fake_task = FakeTask()
    monkeypatch.setattr("src.scheduler.tasks.attend_lesson_task", fake_task, raising=False)
    return fake_task


@pytest.mark.asyncio
async def test_manual_join_happy_path(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse(
        "11111111-1111-1111-1111-111111111111",
        "Sürdürülebilirlik",
        direct_url="https://example.com",
    )
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages = []
    context = FakeContext()
    update = FakeUpdate("sürdürülebilirlik dersine şimdi gir", sent_messages)

    await agent_chat.handle_agent_chat(update, context)

    assert len(fake_task.calls) == 1
    assert fake_task.calls[0]["course_id"] == course.id
    assert fake_task.calls[0]["course_name"] == "Sürdürülebilirlik"
    assert fake_task.calls[0]["dys_url"] == "https://dys.example.com"
    assert fake_task.calls[0]["dys_search_hint"] is None
    assert "pending_manual_join" not in context.user_data


@pytest.mark.asyncio
async def test_manual_join_generic_phrase_asks_for_course_name(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse(
        "11111111-1111-1111-1111-111111111111",
        "Kariyer Planlama",
        direct_url="https://example.com",
    )
    repo = _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages = []
    context = FakeContext()
    update = FakeUpdate("derse katılım şimdi", sent_messages)

    await agent_chat.handle_agent_chat(update, context)

    assert fake_task.calls == []
    assert repo.last_query is None
    assert "Hangi ders" in sent_messages[-1][0]


@pytest.mark.asyncio
async def test_manual_join_ambiguous_match_requires_clarification(monkeypatch):
    from src.bot.handlers import agent_chat

    courses = [
        DummyCourse("1", "Kariyer Planlama", direct_url="https://example.com/1"),
        DummyCourse("2", "Kariyer Yönetimi", direct_url="https://example.com/2"),
    ]
    _install_common_patches(monkeypatch, courses)
    fake_task = _install_fake_task(monkeypatch)

    sent_messages = []
    context = FakeContext()
    update = FakeUpdate("kariyer dersine katıl", sent_messages)

    await agent_chat.handle_agent_chat(update, context)

    assert fake_task.calls == []
    assert context.user_data["pending_manual_join"]["status"] == "ambiguous"
    assert "Birden fazla uygun ders buldum" in sent_messages[-1][0]


@pytest.mark.asyncio
async def test_manual_join_generic_yes_without_single_target_does_not_start(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse(
        "11111111-1111-1111-1111-111111111111",
        "Kariyer Planlama",
        direct_url="https://example.com",
    )
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages = []
    context = FakeContext()
    context.user_data["pending_manual_join"] = {"status": "ambiguous", "candidate_ids": [course.id]}
    update = FakeUpdate("evet", sent_messages)

    await agent_chat.handle_agent_chat(update, context)

    assert fake_task.calls == []
    assert "Hangi dersi kastettiğini" in sent_messages[-1][0]


@pytest.mark.asyncio
async def test_manual_join_via_start_manual_session_tool(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse(
        "22222222-2222-2222-2222-222222222222",
        "Kariyer Planlama",
        direct_url="https://example.com/kariyer",
        dys_search_hint="Kariyer Planlama",
    )
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

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

    sent_messages = []
    context = FakeContext()
    update = FakeUpdate("Kariyer Planlama dersine şimdi katıl", sent_messages)

    await agent_chat.handle_agent_chat(update, context)

    assert len(fake_task.calls) == 1
    assert fake_task.calls[0]["course_id"] == course.id
    assert fake_task.calls[0]["dys_search_hint"] == course.dys_search_hint
    assert "pending_manual_join" not in context.user_data
