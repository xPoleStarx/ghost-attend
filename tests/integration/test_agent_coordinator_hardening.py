from datetime import UTC, datetime, timedelta

import pytest

from app.agent.dispatcher import AgentDispatcher
from app.agent.runtime import AgentRuntimeService
from app.bot.handlers import AgentCoordinator
from app.domain.schemas import ToolResult
from app.services.deduplication import CommandDeduplicator
from app.services.rate_limit import SlidingWindowRateLimiter


class FakeJoinTool:
    async def __call__(self, params: object) -> ToolResult:
        _ = params
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
async def test_agent_coordinator_blocks_duplicate_messages() -> None:
    current = datetime(2026, 3, 19, 12, 0, tzinfo=UTC)
    runtime = AgentRuntimeService(
        dispatcher=AgentDispatcher(
            tools={
                "join_teams_meeting": FakeJoinTool(),
                "leave_meeting": FakeLeaveTool(),
                "take_screenshot": FakeScreenshotTool(),
                "request_human_input": FakeHumanInputTool(),
            }
        )
    )
    coordinator = AgentCoordinator(
        runtime_service=runtime,
        rate_limiter=SlidingWindowRateLimiter(limit=10, window=timedelta(minutes=1), now=lambda: current),
        deduplicator=CommandDeduplicator(window=timedelta(seconds=30), now=lambda: current),
    )

    first = await coordinator.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="join class",
        schedule=[{"id": 1, "name": "class"}],
    )
    second = await coordinator.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="join class",
        schedule=[{"id": 1, "name": "class"}],
    )

    assert first == "joined"
    assert "Duplicate command ignored" in second


@pytest.mark.asyncio
async def test_agent_coordinator_rate_limits_messages() -> None:
    current = datetime(2026, 3, 19, 12, 0, tzinfo=UTC)
    runtime = AgentRuntimeService(
        dispatcher=AgentDispatcher(
            tools={
                "join_teams_meeting": FakeJoinTool(),
                "leave_meeting": FakeLeaveTool(),
                "take_screenshot": FakeScreenshotTool(),
                "request_human_input": FakeHumanInputTool(),
            }
        )
    )
    coordinator = AgentCoordinator(
        runtime_service=runtime,
        rate_limiter=SlidingWindowRateLimiter(limit=1, window=timedelta(minutes=1), now=lambda: current),
        deduplicator=CommandDeduplicator(window=timedelta(seconds=30), now=lambda: current + timedelta(seconds=31)),
    )

    first = await coordinator.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="join class",
        schedule=[{"id": 1, "name": "class"}],
    )
    second = await coordinator.handle_message(
        session_id="session-1",
        user_id=42,
        user_timezone="Europe/Istanbul",
        message="leave",
        schedule=[{"id": 1, "name": "class"}],
    )

    assert first == "joined"
    assert "Rate limit exceeded" in second
