from pathlib import Path

import pytest

from app.browser.navigator import BrowserUseNavigator
from app.browser.runtime import BrowserContextManager, BrowserRuntime
from app.domain.enums import MeetingState
from app.tools.join_teams_meeting import JoinTeamsMeetingTool
from app.tools.leave_meeting import LeaveMeetingTool
from app.tools.login_to_dys import LoginToDysTool
from app.tools.request_human_input import RequestHumanInputTool
from app.tools.schemas import JoinTeamsMeetingInput, LeaveMeetingInput, LoginToDysInput, TakeScreenshotInput
from app.tools.take_screenshot import TakeScreenshotTool


class FakeAdapter:
    async def resolve_login_entry(self, university_url: str) -> object:
        return type("LoginEntry", (), {"url": university_url})()

    async def navigate_to_course_area(self, user_id: int, course_name: str) -> None:
        _ = (user_id, course_name)

    async def extract_meeting_link(self, user_id: int, course_name: str) -> str | None:
        _ = (user_id, course_name)
        return "https://teams.microsoft.com/l/meetup-join/test"

    async def post_login_healthcheck(self, user_id: int) -> bool:
        _ = user_id
        return True


class WaitingRoomAdapter(FakeAdapter):
    async def extract_meeting_link(self, user_id: int, course_name: str) -> str | None:
        _ = (user_id, course_name)
        return None


class FakeHumanInputRepository:
    def __init__(self) -> None:
        self.created = 0

    async def create(self, **_: object) -> object:
        self.created += 1
        return type("HumanInput", (), {"id": "req-2fa"})()


@pytest.mark.asyncio
async def test_join_requires_login(tmp_path: Path) -> None:
    runtime = BrowserRuntime(headless=True, screenshot_dir=tmp_path)
    manager = BrowserContextManager(runtime=runtime)
    tool = JoinTeamsMeetingTool(
        manager,
        FakeAdapter(),
        BrowserUseNavigator(),
        page_timeout_ms=5000,
        timeout_seconds=5,
    )

    result = await tool(
        JoinTeamsMeetingInput(
            user_id=1,
            session_id="session-1",
            course_id=10,
            course_name="Kariyer Planlama",
        )
    )

    assert result.success is False
    assert "Login required" in result.message


@pytest.mark.asyncio
async def test_login_join_screenshot_leave_flow(tmp_path: Path) -> None:
    runtime = BrowserRuntime(headless=True, screenshot_dir=tmp_path)
    manager = BrowserContextManager(runtime=runtime)
    request_tool = RequestHumanInputTool(FakeHumanInputRepository(), timeout_seconds=5)
    login_tool = LoginToDysTool(
        manager,
        FakeAdapter(),
        BrowserUseNavigator(),
        request_tool,
        page_timeout_ms=5000,
        timeout_seconds=5,
    )
    join_tool = JoinTeamsMeetingTool(
        manager,
        FakeAdapter(),
        BrowserUseNavigator(),
        page_timeout_ms=5000,
        timeout_seconds=5,
    )
    screenshot_tool = TakeScreenshotTool(manager, tmp_path, timeout_seconds=5)
    leave_tool = LeaveMeetingTool(manager, timeout_seconds=5)

    login_result = await login_tool(
        LoginToDysInput(
            user_id=1,
            session_id="session-1",
            email="student@example.edu",
            password="pass123",
            university_url="https://dys.example.edu",
        )
    )
    assert login_result.success is True

    join_result = await join_tool(
        JoinTeamsMeetingInput(
            user_id=1,
            session_id="session-1",
            course_id=10,
            course_name="Kariyer Planlama",
        )
    )
    assert join_result.success is True

    shot_result = await screenshot_tool(TakeScreenshotInput(user_id=1, session_id="session-1"))
    assert shot_result.success is True
    assert shot_result.screenshot_path is not None

    leave_result = await leave_tool(LeaveMeetingInput(user_id=1, session_id="session-1"))
    assert leave_result.success is True

    handle = await manager.get_context(1)
    assert handle is not None
    assert handle.meeting_state == MeetingState.IDLE


@pytest.mark.asyncio
async def test_login_2fa_requests_human_input(tmp_path: Path) -> None:
    runtime = BrowserRuntime(headless=True, screenshot_dir=tmp_path)
    manager = BrowserContextManager(runtime=runtime)
    human_inputs = FakeHumanInputRepository()
    request_tool = RequestHumanInputTool(human_inputs, timeout_seconds=5)
    login_tool = LoginToDysTool(
        manager,
        FakeAdapter(),
        BrowserUseNavigator(),
        request_tool,
        page_timeout_ms=5000,
        timeout_seconds=5,
    )

    result = await login_tool(
        LoginToDysInput(
            user_id=1,
            session_id="session-1",
            email="student+2fa@example.edu",
            password="pass123",
            university_url="https://dys.example.edu",
        )
    )

    handle = await manager.get_context(1)
    assert result.success is True
    assert "Human input requested" in result.message
    assert human_inputs.created == 1
    assert handle is not None
    assert handle.meeting_state == MeetingState.PAUSED_HUMAN_INPUT


@pytest.mark.asyncio
async def test_join_enters_waiting_room_when_link_missing(tmp_path: Path) -> None:
    runtime = BrowserRuntime(headless=True, screenshot_dir=tmp_path)
    manager = BrowserContextManager(runtime=runtime)
    request_tool = RequestHumanInputTool(FakeHumanInputRepository(), timeout_seconds=5)
    login_tool = LoginToDysTool(
        manager,
        WaitingRoomAdapter(),
        BrowserUseNavigator(),
        request_tool,
        page_timeout_ms=5000,
        timeout_seconds=5,
    )
    join_tool = JoinTeamsMeetingTool(
        manager,
        WaitingRoomAdapter(),
        BrowserUseNavigator(),
        page_timeout_ms=5000,
        timeout_seconds=5,
    )

    await login_tool(
        LoginToDysInput(
            user_id=1,
            session_id="session-1",
            email="student@example.edu",
            password="pass123",
            university_url="https://dys.example.edu",
        )
    )

    result = await join_tool(
        JoinTeamsMeetingInput(
            user_id=1,
            session_id="session-1",
            course_id=10,
            course_name="Kariyer Planlama",
        )
    )

    handle = await manager.get_context(1)
    assert result.success is True
    assert "Waiting room mode" in result.message
    assert handle is not None
    assert handle.meeting_state == MeetingState.WAITING_ROOM
