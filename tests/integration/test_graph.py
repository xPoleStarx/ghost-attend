import pytest

from app.agent.graph import SimpleAgentGraph
from app.agent.state import build_initial_state
from app.domain.schemas import ToolResult


@pytest.mark.asyncio
async def test_graph_runs_tool_path() -> None:
    async def dispatcher(_state: dict[str, object]) -> ToolResult:
        return ToolResult(success=True, message="joined")

    async def resume_handler(_state: dict[str, object]) -> ToolResult:
        return ToolResult(success=True, message="resumed")

    graph = SimpleAgentGraph(dispatcher=dispatcher, resume_handler=resume_handler)
    state = build_initial_state("session-1", 42, "Europe/Istanbul")
    state["messages"] = ["join my class"]

    result = await graph.run(state)

    assert result["response"] == "joined"
