from __future__ import annotations

from app.agent.state import AgentState
from app.domain.schemas import IntentMatch


class IntentClassifier:
    def classify(self, state: AgentState) -> IntentMatch | None:
        messages = state.get("messages", [])
        if not messages:
            return None
        latest = str(messages[-1]).lower()
        if "screenshot" in latest:
            return IntentMatch(tool_name="take_screenshot")
        if "leave" in latest or "ayril" in latest or "çık" in latest or "cik" in latest:
            return IntentMatch(tool_name="leave_meeting")
        if "join" in latest or "gir" in latest:
            matches = self._match_courses(state.get("schedule", []), latest)
            if not matches:
                return IntentMatch(tool_name="join_teams_meeting")
            if len(matches) == 1:
                match = matches[0]
                return IntentMatch(
                    tool_name="join_teams_meeting",
                    course_id=int(match["id"]),
                    course_name=str(match["name"]),
                )
            return IntentMatch(
                tool_name="join_teams_meeting",
                requires_confirmation=True,
                candidate_courses=matches,
            )
        return None

    def choose_from_reply(self, state: AgentState, reply: str) -> IntentMatch | None:
        payload = state.get("pending_tool_payload") or {}
        candidates = payload.get("candidate_courses", [])
        reply_lower = reply.lower()
        normalized = [candidate for candidate in candidates if str(candidate["name"]).lower() in reply_lower]
        if len(normalized) == 1:
            candidate = normalized[0]
            return IntentMatch(
                tool_name=str(state.get("pending_tool")),
                course_id=int(candidate["id"]),
                course_name=str(candidate["name"]),
            )
        if reply.isdigit():
            index = int(reply) - 1
            if 0 <= index < len(candidates):
                candidate = candidates[index]
                return IntentMatch(
                    tool_name=str(state.get("pending_tool")),
                    course_id=int(candidate["id"]),
                    course_name=str(candidate["name"]),
                )
        return None

    def _match_courses(self, schedule: list[dict[str, object]], latest: str) -> list[dict[str, object]]:
        return [
            course
            for course in schedule
            if str(course.get("name", "")).lower() in latest
            or any(token in str(course.get("name", "")).lower() for token in latest.split())
        ]
