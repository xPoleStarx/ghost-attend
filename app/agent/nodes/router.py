from app.agent.state import AgentState


async def router_node(state: AgentState) -> str:
    if state.get("awaiting_human_input"):
        return "HUMAN_INPUT"
    messages = state.get("messages", [])
    if not messages:
        return "CLARIFY"
    latest = str(messages[-1]).lower()
    tool_keywords = ["join", "gir", "screenshot", "/screenshot", "leave", "ayril", "çık", "cik"]
    if any(keyword in latest for keyword in tool_keywords):
        return "TOOL_CALL"
    if "?" in latest:
        return "CLARIFY"
    return "CHAT"
