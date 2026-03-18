from datetime import time
from types import SimpleNamespace
from uuid import UUID

import pytest

from src.bot.handlers.agent_chat import _compute_next_lesson
from src.conversation.policy import decide_policy
from src.conversation.tools import ConversationToolRegistry


class DummyCourse:
    def __init__(self, course_id: str, name: str, start_time: time, end_time: time):
        self.id = course_id
        self.name = name
        self.day_of_week = 0
        self.start_time = start_time
        self.end_time = end_time
        self.direct_url = "https://example.com/live"
        self.dys_search_hint = None
        self.platform = "teams"
        self.is_online = True
        self.is_active = True


def test_compute_next_lesson_selects_closest_future(monkeypatch):
    fake_now = SimpleNamespace(hour=10, minute=0, weekday=lambda: 0, astimezone=lambda tz: fake_now)

    class FakeDateTime:
        @staticmethod
        def now(*args, **kwargs):
            return fake_now

    monkeypatch.setattr("src.bot.handlers.agent_chat.datetime", FakeDateTime)

    courses = [
        DummyCourse("1", "Ders1", time(9, 0), time(10, 0)),
        DummyCourse("2", "Ders2", time(11, 0), time(12, 0)),
        DummyCourse("3", "Ders3", time(13, 0), time(14, 0)),
    ]

    next_course = _compute_next_lesson(courses)
    assert next_course is not None
    assert next_course.name == "Ders2"


@pytest.mark.asyncio
async def test_session_start_tool_dispatches_attend_task():
    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama", time(10, 0), time(11, 0))

    class FakeCourseRepo:
        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            return [course]

    class FakeCredRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    class FakeSessionRepo:
        async def get_active_session(self, user_id: int):
            return None

    class FakeSession:
        async def commit(self):
            return None

    class FakeTask:
        def __init__(self):
            self.calls = []

        def delay(self, **kwargs):
            self.calls.append(kwargs)

    fake_task = FakeTask()
    registry = ConversationToolRegistry(
        user_id=123,
        session=FakeSession(),
        course_repo=FakeCourseRepo(),
        credential_repo=FakeCredRepo(),
        session_repo=FakeSessionRepo(),
        attend_task=fake_task,
    )

    result = await registry.execute(
        "session.start",
        {"course_name_query": "Kariyer Planlama"},
        {"message_text": "Kariyer Planlama dersine simdi katil", "courses": [course]},
    )

    assert result.ok is True
    assert fake_task.calls
    assert fake_task.calls[0]["course_id"] == course.id
    assert fake_task.calls[0]["start_time"] == "10:00"


@pytest.mark.asyncio
async def test_session_start_tool_cleans_join_filler_words_before_lookup():
    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama", time(10, 0), time(11, 0))

    class FakeCourseRepo:
        def __init__(self):
            self.queries = []

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            self.queries.append(query)
            return [course]

    class FakeCredRepo:
        async def get_dys_url_for_user(self, user_id: int):
            return "https://dys.example.com"

    class FakeSessionRepo:
        async def get_active_session(self, user_id: int):
            return None

    class FakeSession:
        async def commit(self):
            return None

    class FakeTask:
        def __init__(self):
            self.calls = []

        def delay(self, **kwargs):
            self.calls.append(kwargs)

    fake_task = FakeTask()
    repo = FakeCourseRepo()
    registry = ConversationToolRegistry(
        user_id=123,
        session=FakeSession(),
        course_repo=repo,
        credential_repo=FakeCredRepo(),
        session_repo=FakeSessionRepo(),
        attend_task=fake_task,
    )

    result = await registry.execute(
        "session.start",
        {"course_name_query": "derse gir hadi kariyer planlama dersine"},
        {"message_text": "derse gir hadi kariyer planlama dersine", "courses": [course]},
    )

    assert result.ok is True
    assert fake_task.calls
    assert "kariyer planlama" in repo.queries


@pytest.mark.asyncio
async def test_courses_update_uses_single_course_and_preserves_duration():
    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama", time(18, 0), time(18, 45))

    class FakeCourseRepo:
        def __init__(self):
            self.updated = None
            self.direct_url = None

        async def get_by_id(self, course_id: UUID):
            assert str(course_id) == course.id
            return course

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            return []

        async def update_schedule(self, course_id, **values):
            self.updated = (course_id, values)

        async def update_direct_url(self, course_id, url: str):
            self.direct_url = (course_id, url)

    class FakeSession:
        async def commit(self):
            return None

    called = []

    async def fake_schedule_all(user_id: int):
        called.append(user_id)

    state = {"last_referenced_course_id": course.id, "last_schedule_intent": "course_update"}
    repo = FakeCourseRepo()
    registry = ConversationToolRegistry(
        user_id=123,
        session=FakeSession(),
        course_repo=repo,
        credential_repo=object(),
        session_repo=object(),
        schedule_all_courses=fake_schedule_all,
    )

    result = await registry.execute(
        "courses.update",
        {"raw_text": "dersin saatini 18.12 yap"},
        {"message_text": "dersin saatini 18.12 yap", "courses": [course], "conversation_state": state},
    )

    assert result.ok is True
    assert repo.updated is not None
    _, updated_values = repo.updated
    assert updated_values["start_time"] == time(18, 12)
    assert updated_values["end_time"] == time(18, 57)
    assert called == [123]
    assert state["last_referenced_course_name"] == "Kariyer Planlama"


@pytest.mark.asyncio
async def test_courses_update_prefers_conversation_memory_when_query_missing():
    course = DummyCourse("11111111-1111-1111-1111-111111111111", "Kariyer Planlama", time(18, 0), time(18, 45))

    class FakeCourseRepo:
        def __init__(self):
            self.updated = None

        async def get_by_id(self, course_id: UUID):
            return course if str(course_id) == course.id else None

        async def find_by_name(self, user_id: int, query: str, active_only: bool = True, limit: int = 5):
            return []

        async def update_schedule(self, course_id, **values):
            self.updated = (course_id, values)

        async def update_direct_url(self, course_id, url: str):
            raise AssertionError("direct url should not be updated")

    class FakeSession:
        async def commit(self):
            return None

    state = {
        "last_referenced_course_id": course.id,
        "last_referenced_course_name": course.name,
        "last_schedule_intent": "course_update",
    }
    repo = FakeCourseRepo()
    registry = ConversationToolRegistry(
        user_id=123,
        session=FakeSession(),
        course_repo=repo,
        credential_repo=object(),
        session_repo=object(),
    )

    result = await registry.execute(
        "courses.update",
        {"raw_text": "çarşambaya al"},
        {"message_text": "çarşambaya al", "courses": [course], "conversation_state": state},
    )

    assert result.ok is True
    assert repo.updated[1]["day_of_week"] == 2


@pytest.mark.asyncio
async def test_session_ask_runtime_sends_screenshot(monkeypatch):
    class FakeNotifier:
        def __init__(self):
            self.calls = []

        async def send_screenshot(self, **kwargs):
            self.calls.append(kwargs)
            return True

    class FakeSession:
        async def commit(self):
            return None

    class FakeSessionRepo:
        async def get_active_session(self, user_id: int):
            return SimpleNamespace(id="session-1", status="running")

    class FakeRuntimeIPC:
        def encode_bytes(self, value: bytes | None):
            return "ZmFrZS1pbWFnZQ==" if value else None

        def decode_bytes(self, value: str):
            assert value == "ZmFrZS1pbWFnZQ=="
            return b"fake-image"

        async def get_session(self, session_id: str):
            return SimpleNamespace(session_id=session_id, status="running")

        async def send_command(self, session_id: str, command_type: str, payload: dict):
            assert command_type == "take_screenshot"
            return SimpleNamespace(command_id="cmd-1")

        async def await_result(self, command_id: str):
            return SimpleNamespace(
                ok=True,
                payload={
                    "answer": "Guncel ekran goruntusunu gonderiyorum.",
                    "details": {"snapshot_id": "snap-1"},
                    "screenshot_b64": "ZmFrZS1pbWFnZQ==",
                },
                error=None,
            )

    notifier = FakeNotifier()
    registry = ConversationToolRegistry(
        user_id=123,
        session=FakeSession(),
        course_repo=object(),
        credential_repo=object(),
        session_repo=FakeSessionRepo(),
        notifier=notifier,
        runtime_ipc=FakeRuntimeIPC(),
    )

    result = await registry.execute(
        "session.ask_runtime",
        {"question": "take a screenshot and send it to me"},
        {"message_text": "take a screenshot and send it to me"},
    )

    assert result.ok is True
    assert notifier.calls
    assert notifier.calls[0]["caption"] == "Guncel ekran goruntusunu gonderiyorum."


def test_policy_routes_status_question_to_status_tool():
    decision = decide_policy(
        message_text="derse katilacak misin",
        courses=[],
        attachments=[],
        conversation_state={},
    )
    assert decision.tool_name == "session.status"


def test_policy_routes_explicit_join_to_start_tool():
    decision = decide_policy(
        message_text="Kariyer Planlama dersine katil simdi",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={},
    )
    assert decision.tool_name == "session.start"
    assert decision.tool_args["course_name_query"] == "kariyer planlama"


def test_policy_extracts_course_from_prefix_join_phrase():
    decision = decide_policy(
        message_text="hadi kariyer planlama dersine gir",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={},
    )
    assert decision.tool_name == "session.start"
    assert decision.tool_args["course_name_query"] == "kariyer planlama"


def test_policy_extracts_course_from_suffix_join_phrase():
    decision = decide_policy(
        message_text="derse gir hadi kariyer planlama dersine",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={},
    )
    assert decision.tool_name == "session.start"
    assert decision.tool_args["course_name_query"] == "kariyer planlama"


def test_policy_keeps_generic_join_ambiguous_for_multiple_courses():
    decision = decide_policy(
        message_text="derse gir",
        courses=[{"name": "Kariyer Planlama"}, {"name": "Veri Yapilari"}],
        attachments=[],
        conversation_state={},
    )
    assert decision.requires_clarification is True


def test_policy_starts_single_course_for_generic_join():
    decision = decide_policy(
        message_text="derse gir",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={},
    )
    assert decision.tool_name == "session.start"
    assert decision.tool_args["course_name_query"] == "Kariyer Planlama"


def test_policy_routes_single_course_time_change_to_courses_update():
    decision = decide_policy(
        message_text="dersin saatini 18.12 yap",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={"last_schedule_intent": "course_update"},
    )

    assert decision.tool_name == "courses.update"
    assert decision.tool_args["start_time"] == "18:12"
