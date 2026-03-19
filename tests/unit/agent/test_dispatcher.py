import pytest

from app.agent.dispatcher import AgentDispatcher
from app.agent.state import build_initial_state
from app.domain.schemas import ToolResult


class FakeJoinTool:
    def __init__(self) -> None:
        self.calls: list[object] = []

    async def __call__(self, params: object) -> ToolResult:
        self.calls.append(params)
        return ToolResult(success=True, message="joined")


class FakeLeaveTool:
    async def __call__(self, params: object) -> ToolResult:
        _ = params
        return ToolResult(success=True, message="left")


class FakeScreenshotTool:
    async def __call__(self, params: object) -> ToolResult:
        _ = params
        return ToolResult(success=True, message="shot")


class FakeHumanInputTool:
    async def __call__(self, params: object) -> ToolResult:
        _ = params
        return ToolResult(success=True, message="Human input requested: req-123")


@pytest.mark.asyncio
async def test_dispatcher_routes_unique_course_join() -> None:
    join_tool = FakeJoinTool()
    dispatcher = AgentDispatcher(
        tools={
            "join_teams_meeting": join_tool,
            "leave_meeting": FakeLeaveTool(),
            "take_screenshot": FakeScreenshotTool(),
            "request_human_input": FakeHumanInputTool(),
        }
    )
    state = build_initial_state("session-1", 42, "Europe/Istanbul")
    state["schedule"] = [{"id": 10, "name": "Kariyer Planlama"}]
    state["messages"] = ["kariyer planlama dersine gir"]

    result = await dispatcher.dispatch(state)

    assert result.success is True
    assert result.message == "joined"
    assert len(join_tool.calls) == 1


@pytest.mark.asyncio
async def test_dispatcher_requests_human_input_for_ambiguous_course() -> None:
    dispatcher = AgentDispatcher(
        tools={
            "join_teams_meeting": FakeJoinTool(),
            "leave_meeting": FakeLeaveTool(),
            "take_screenshot": FakeScreenshotTool(),
            "request_human_input": FakeHumanInputTool(),
        }
    )
    state = build_initial_state("session-1", 42, "Europe/Istanbul")
    state["schedule"] = [
        {"id": 10, "name": "Kariyer Planlama"},
        {"id": 11, "name": "Kariyer Gelisimi"},
    ]
    state["messages"] = ["kariyer dersine gir"]

    result = await dispatcher.dispatch(state)

    assert result.success is True
    assert state["awaiting_human_input"] is True
    assert state["pending_tool"] == "join_teams_meeting"
    assert state["pending_human_input_request_id"] == "req-123"

