import pytest

from app.agent.nodes.router import router_node
from app.agent.state import build_initial_state


@pytest.mark.asyncio
async def test_router_prioritizes_human_input() -> None:
    state = build_initial_state("session-1", 42, "Europe/Istanbul")
    state["awaiting_human_input"] = True

    route = await router_node(state)

    assert route == "HUMAN_INPUT"


@pytest.mark.asyncio
async def test_router_routes_tool_call_keywords() -> None:
    state = build_initial_state("session-1", 42, "Europe/Istanbul")
    state["messages"] = ["kariyer dersine gir"]

    route = await router_node(state)

    assert route == "TOOL_CALL"
