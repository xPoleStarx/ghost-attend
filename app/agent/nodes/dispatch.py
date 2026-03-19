from collections.abc import Awaitable, Callable

from app.agent.state import AgentState
from app.domain.schemas import ToolResult


async def tool_dispatch_node(
    state: AgentState,
    dispatch: Callable[[AgentState], Awaitable[ToolResult]],
) -> AgentState:
    state["tool_result"] = await dispatch(state)
    return state
