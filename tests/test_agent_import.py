def test_build_compiled_graph_importable():
    from app.agent.task_agent import build_compiled_graph

    assert callable(build_compiled_graph)


def test_last_assistant_text_empty():
    from app.agent.output import last_assistant_text_for_telegram

    assert last_assistant_text_for_telegram([]) == ""


def test_has_open_tool_calls():
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.telegram.handlers import _has_open_tool_calls

    tc = [{"name": "x", "args": {}, "id": "call-1", "type": "tool_call"}]
    assert _has_open_tool_calls(
        [HumanMessage("hi"), AIMessage(content="", tool_calls=tc)]
    )
    assert not _has_open_tool_calls(
        [
            HumanMessage("hi"),
            AIMessage(content="", tool_calls=tc),
            ToolMessage(content="ok", tool_call_id="call-1"),
        ]
    )
