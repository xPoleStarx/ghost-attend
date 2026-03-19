from app.agent.state import AgentState


async def chat_response_node(state: AgentState) -> AgentState:
    state["response"] = "I am here and ready to help with your attendance flow."
    return state
