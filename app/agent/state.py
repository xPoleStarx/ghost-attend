from typing import Any

try:
    from langgraph.graph import MessagesState
except Exception:  # noqa: BLE001
    class MessagesState(dict[str, Any]):  # type: ignore[misc,valid-type]
        pass


class AgentState(MessagesState):
    session_id: str
    user_id: int
    user_timezone: str
    schedule: list[dict[str, Any]]
    awaiting_human_input: bool
    pending_tool: str | None
    pending_human_input_request_id: str | None
    pending_tool_payload: dict[str, Any] | None
    meeting_state: str
    last_screenshot_path: str | None


def build_initial_state(session_id: str, user_id: int, user_timezone: str) -> AgentState:
    return AgentState(
        session_id=session_id,
        user_id=user_id,
        user_timezone=user_timezone,
        schedule=[],
        awaiting_human_input=False,
        pending_tool=None,
        pending_human_input_request_id=None,
        pending_tool_payload=None,
        meeting_state="IDLE",
        last_screenshot_path=None,
        messages=[],
    )
