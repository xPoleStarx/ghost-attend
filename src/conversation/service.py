"""End-to-end conversation service used by Telegram handlers."""

from __future__ import annotations

from datetime import datetime

from src.conversation.agent import ConversationAgent
from src.conversation.models import ConversationAgentRequest, SessionContext
from src.conversation.policy import decide_policy
from src.conversation.tools import ConversationToolRegistry


class ConversationService:
    """Builds conversation context, runs the agent, then executes typed tools."""

    def __init__(self, *, agent: ConversationAgent):
        self.agent = agent

    async def handle(
        self,
        *,
        user_id: int,
        message_text: str,
        attachments: list[dict],
        history: list[dict],
        courses,
        timezone_name: str,
        active_session,
        tool_registry: ConversationToolRegistry,
        conversation_state: dict | None = None,
    ) -> str:
        metadata = getattr(active_session, "metadata_", None) or {}
        runtime_snapshot = metadata.get("runtime_last_snapshot")
        runtime_summary = metadata.get("runtime_session")
        session_context = SessionContext(
            session_id=str(active_session.id) if active_session else None,
            status=getattr(active_session, "status", "idle") if active_session else "idle",
            course_name=getattr(getattr(active_session, "course", None), "name", None) if active_session else None,
            runtime_available=bool(runtime_summary),
            latest_runtime_snapshot=runtime_snapshot,
        )

        policy = decide_policy(
            message_text=message_text,
            courses=[
                {
                    "id": str(course.id),
                    "name": course.name,
                    "day_of_week": course.day_of_week,
                    "start_time": course.start_time.strftime("%H:%M"),
                    "end_time": course.end_time.strftime("%H:%M"),
                }
                for course in courses
            ],
            attachments=attachments,
            conversation_state=conversation_state,
        )
        if conversation_state is not None:
            if policy.intent_family in {"course_update", "schedule_update"}:
                conversation_state["last_schedule_intent"] = policy.intent_family
            course_query = str(policy.tool_args.get("course_name_query") or "").strip()
            if course_query:
                conversation_state["last_referenced_course_name"] = course_query
        if policy.requires_clarification:
            return policy.clarification_message
        if policy.tool_name:
            result = await tool_registry.execute(
                policy.tool_name,
                policy.tool_args,
                {
                    "message_text": message_text,
                    "images": [(item["bytes"], item["mime_type"]) for item in attachments if item.get("kind") == "image"],
                    "text_hint": message_text,
                    "attachments": attachments,
                    "courses": courses,
                    "conversation_state": conversation_state or {},
                },
            )
            return result.message or "Tamam."

        request = ConversationAgentRequest(
            user_id=user_id,
            message_text=message_text,
            attachments=attachments,
            history=history[-10:],
            courses=[
                {
                    "id": str(course.id),
                    "name": course.name,
                    "day_of_week": course.day_of_week,
                    "start_time": course.start_time.strftime("%H:%M"),
                    "end_time": course.end_time.strftime("%H:%M"),
                    "platform": course.platform,
                    "direct_url": course.direct_url,
                    "is_online": course.is_online,
                    "is_active": course.is_active,
                }
                for course in courses
            ],
            session=session_context,
            timezone=timezone_name,
            now_local_iso=datetime.utcnow().isoformat(),
        )
        response = await self.agent.respond(request)
        if response.mode != "tool":
            return response.message

        final_message = response.message
        for tool_call in response.tool_calls:
            result = await tool_registry.execute(
                tool_call.name,
                tool_call.args,
                {
                    "message_text": message_text,
                    "images": [(item["bytes"], item["mime_type"]) for item in attachments if item.get("kind") == "image"],
                    "text_hint": message_text,
                    "attachments": attachments,
                    "courses": courses,
                    "conversation_state": conversation_state or {},
                },
            )
            final_message = result.message or final_message
            if not result.ok:
                break
        return final_message or "Tamam."
