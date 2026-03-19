import pytest

from app.agent.dispatcher import AgentDispatcher
from app.agent.runtime import AgentRuntimeService
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
async def test_agent_runtime_resumes_after_human_input_reply() -> None:
    join_tool = FakeJoinTool()
    runtime = AgentRuntimeService(
        dispatcher=AgentDispatcher(
            tools={
                "join_teams_meeting": join_tool,
                "leave_meeting": FakeLeaveTool(),
                "take_screenshot": FakeScreenshotTool(),
                "request_human_input": FakeHumanInputTool(),
            }
        )
    )
    schedule = [
        {"id": 10, "name": "Kariyer Planlama"},
        {"id": 11, "name": "Kariyer Gelisimi"},
    ]

    first_state = await runtime.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="kariyer dersine gir",
        schedule=schedule,
    )
    assert first_state["awaiting_human_input"] is True
    assert first_state["response"] == "Human input requested: req-123"

    second_state = await runtime.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="1",
        schedule=schedule,
    )

    assert second_state["awaiting_human_input"] is False
    assert second_state["response"] == "joined"
    assert len(join_tool.calls) == 1
