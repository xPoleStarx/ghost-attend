from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeAlias

from app.agent.intents import IntentClassifier
from app.agent.state import AgentState
from app.domain.schemas import IntentMatch, ToolResult
from app.tools.schemas import (
    JoinTeamsMeetingInput,
    LeaveMeetingInput,
    RequestHumanInputInput,
    TakeScreenshotInput,
)

ToolCallable: TypeAlias = Callable[[object], Awaitable[ToolResult]]


class AgentDispatcher:
    def __init__(self, tools: dict[str, ToolCallable], classifier: IntentClassifier | None = None) -> None:
        self.tools = tools
        self.classifier = classifier or IntentClassifier()

    async def dispatch(self, state: AgentState) -> ToolResult:
        intent = self.classifier.classify(state)
        if intent is None:
            return ToolResult(success=False, message="I could not determine which tool to call.")
        if intent.requires_confirmation:
            return await self._request_confirmation(state, intent)
        if intent.tool_name == "take_screenshot":
            tool = self.tools["take_screenshot"]
            return await tool(
                TakeScreenshotInput(user_id=state["user_id"], session_id=state["session_id"])
            )
        if intent.tool_name == "leave_meeting":
            tool = self.tools["leave_meeting"]
            return await tool(LeaveMeetingInput(user_id=state["user_id"], session_id=state["session_id"]))
        if intent.tool_name == "join_teams_meeting" and intent.course_id is not None and intent.course_name:
            tool = self.tools["join_teams_meeting"]
            return await tool(
                JoinTeamsMeetingInput(
                    user_id=state["user_id"],
                    session_id=state["session_id"],
                    course_id=int(intent.course_id),
                    course_name=intent.course_name,
                )
            )
        return ToolResult(
            success=False,
            message="I could not map this request to a concrete course. Please name the course.",
        )

    async def resume(self, state: AgentState) -> ToolResult:
        latest_message = str((state.get("messages") or [""])[-1])
        match = self.classifier.choose_from_reply(state, latest_message)
        if match is None or match.course_id is None or match.course_name is None:
            return ToolResult(
                success=False,
                message="I still could not resolve the course. Reply with the course name or number.",
            )
        tool = self.tools["join_teams_meeting"]
        result = await tool(
            JoinTeamsMeetingInput(
                user_id=state["user_id"],
                session_id=state["session_id"],
                course_id=int(match.course_id),
                course_name=match.course_name,
            )
        )
        if result.success:
            state["awaiting_human_input"] = False
            state["pending_tool"] = None
            state["pending_human_input_request_id"] = None
            state["pending_tool_payload"] = None
        return result

    async def _request_confirmation(self, state: AgentState, intent: IntentMatch) -> ToolResult:
        tool = self.tools["request_human_input"]
        course_lines = [
            f"{index + 1}. {candidate['name']}" for index, candidate in enumerate(intent.candidate_courses)
        ]
        prompt = "Which course should I join?\n" + "\n".join(course_lines)
        result = await tool(
            RequestHumanInputInput(
                user_id=state["user_id"],
                session_id=state["session_id"],
                tool_name=intent.tool_name,
                reason="ambiguous_course_match",
                prompt=prompt,
            )
        )
        request_id = None
        message = result.message
        if ": " in message:
            request_id = message.split(": ", maxsplit=1)[1]
        state["awaiting_human_input"] = True
        state["pending_tool"] = intent.tool_name
        state["pending_human_input_request_id"] = request_id
        state["pending_tool_payload"] = {"candidate_courses": intent.candidate_courses}
        return result
