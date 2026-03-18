from datetime import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


class DummyCourse:
    def __init__(self, course_id: str, name: str):
        self.id = course_id
        self.name = name
        self.day_of_week = 2
        self.start_time = time(10, 0)
        self.end_time = time(11, 0)
        self.platform = "teams"
        self.direct_url = "https://example.com/live"
        self.dys_search_hint = name
        self.is_online = True
        self.is_active = True


class FakeMessage:
    def __init__(self, text: str, sent_messages: list[str]):
        self.text = text
        self.caption = None
        self.photo = []
        self._sent_messages = sent_messages

    async def reply_text(self, text, parse_mode=None):
        self._sent_messages.append(text)
        return SimpleNamespace(delete=AsyncMock())


class FakeUpdate:
    def __init__(self, text: str, sent_messages: list[str]):
        self.effective_user = SimpleNamespace(id=123)
        self.message = FakeMessage(text, sent_messages)


class FakeContext:
    def __init__(self):
        self.user_data = {}
        self.bot = MagicMock()


def _install_common_patches(monkeypatch, courses: list[DummyCourse], active_session=None):
    fake_session = MagicMock()
    fake_session.commit = AsyncMock()

    class SessionCtx:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("src.db.connection.get_session", lambda: SessionCtx())

    class FakeUserRepo:
        async def get_by_id(self, user_id: int):
            return SimpleNamespace(timezone="Europe/Istanbul")

    class FakeCredRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    class FakeCourseRepo:
        async def get_user_courses(self, user_id: int, active_only: bool = True):
            return courses

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            lowered = query.casefold()
            return [course for course in courses if any(token in course.name.casefold() for token in lowered.split())]

    class FakeSessionRepo:
        async def get_active_session(self, user_id: int):
            return active_session

        async def update_metadata(self, *args, **kwargs):
            return None

    class FakeNotifier:
        def __init__(self, *args, **kwargs):
            self.sent = []

        async def send_screenshot(self, **kwargs):
            self.sent.append(kwargs)
            return True

        async def send_message(self, *args, **kwargs):
            return True

    monkeypatch.setattr("src.db.repositories.user.UserRepository", lambda session: FakeUserRepo())
    monkeypatch.setattr("src.db.repositories.credential.CredentialRepository", lambda session: FakeCredRepo())
    monkeypatch.setattr("src.db.repositories.course.CourseRepository", lambda session: FakeCourseRepo())
    monkeypatch.setattr("src.db.repositories.session.SessionRepository", lambda session: FakeSessionRepo())
    monkeypatch.setattr("src.notifications.service.NotificationService", FakeNotifier)
    monkeypatch.setattr("src.scheduler.lesson_scheduler.schedule_all_courses_for_user", AsyncMock())
    monkeypatch.setattr("redis.asyncio.from_url", lambda *args, **kwargs: SimpleNamespace(aclose=AsyncMock()))


def _install_fake_task(monkeypatch):
    class FakeTask:
        def __init__(self):
            self.calls = []

        def delay(self, **kwargs):
            self.calls.append(kwargs)

    fake_task = FakeTask()
    monkeypatch.setattr("src.scheduler.tasks.attend_lesson_task", fake_task)
    return fake_task


@pytest.mark.asyncio
async def test_handler_starts_manual_session_from_tool_call(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama")
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages: list[str] = []
    await agent_chat.handle_agent_chat(FakeUpdate("Kariyer Planlama dersine simdi katil", sent_messages), FakeContext())

    assert fake_task.calls
    assert fake_task.calls[0]["course_id"] == course.id
    assert "Kariyer Planlama" in sent_messages[-1]


@pytest.mark.asyncio
async def test_handler_starts_manual_session_from_prefix_join_phrase(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama")
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages: list[str] = []
    await agent_chat.handle_agent_chat(FakeUpdate("hadi kariyer planlama dersine gir", sent_messages), FakeContext())

    assert fake_task.calls
    assert fake_task.calls[0]["course_id"] == course.id


@pytest.mark.asyncio
async def test_handler_starts_manual_session_from_suffix_join_phrase(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama")
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages: list[str] = []
    await agent_chat.handle_agent_chat(FakeUpdate("derse gir hadi kariyer planlama dersine", sent_messages), FakeContext())

    assert fake_task.calls
    assert fake_task.calls[0]["course_id"] == course.id


@pytest.mark.asyncio
async def test_handler_answers_runtime_question(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama")
    active_session = SimpleNamespace(id="session-1", status="running", course=course)
    _install_common_patches(monkeypatch, [course], active_session=active_session)
    _install_fake_task(monkeypatch)

    class FakeRuntimeIPC:
        def decode_bytes(self, value: str):
            return b"fake-image"

        async def get_session(self, session_id: str):
            return SimpleNamespace(session_id=session_id, status="running")

        async def send_command(self, session_id: str, command_type: str, payload: dict):
            return SimpleNamespace(command_id="cmd-1")

        async def await_result(self, command_id: str):
            return SimpleNamespace(
                ok=True,
                payload={"answer": "Guncel ekran goruntusunu gonderiyorum.", "details": {}, "screenshot_b64": None},
                error=None,
            )

    monkeypatch.setattr("src.bot.handlers.agent_chat.RuntimeIPC", lambda redis_client: FakeRuntimeIPC())

    sent_messages: list[str] = []
    await agent_chat.handle_agent_chat(FakeUpdate("take a screenshot and send it to me", sent_messages), FakeContext())

    assert sent_messages[-1] == "Guncel ekran goruntusunu gonderiyorum."


@pytest.mark.asyncio
async def test_handler_routes_status_question_without_starting_session(monkeypatch):
    from src.bot.handlers import agent_chat

    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama")
    _install_common_patches(monkeypatch, [course])
    fake_task = _install_fake_task(monkeypatch)

    sent_messages: list[str] = []
    await agent_chat.handle_agent_chat(FakeUpdate("derse katilacak misin", sent_messages), FakeContext())

    assert not fake_task.calls
    assert "aktif bir ders oturumu yok" in sent_messages[-1].casefold()
