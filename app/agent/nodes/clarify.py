from app.agent.state import AgentState


async def clarify_node(state: AgentState) -> AgentState:
    state["response"] = "Please clarify which course or action you want me to handle."
    return state
