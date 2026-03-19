from app.agent.state import AgentState


async def tool_result_node(state: AgentState) -> AgentState:
    tool_result = state.get("tool_result")
    if tool_result is not None:
        state["response"] = tool_result.message
    return state
