from app.agent.state import build_initial_state


def test_initial_state_has_required_fields() -> None:
    state = build_initial_state("session-1", 42, "Europe/Istanbul")

    assert state["session_id"] == "session-1"
    assert state["user_id"] == 42
    assert state["meeting_state"] == "IDLE"
    assert state["awaiting_human_input"] is False
