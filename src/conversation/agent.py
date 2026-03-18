"""LLM-backed conversation agent."""

from __future__ import annotations

import json

from src.conversation.models import ConversationAgentRequest, ConversationAgentResponse, ToolCall
from src.core.config import settings


class ConversationAgent:
    """Plans post-setup actions using typed tools."""

    def __init__(self, llm_callable):
        self._llm_callable = llm_callable

    async def respond(self, request: ConversationAgentRequest) -> ConversationAgentResponse:
        system_prompt = (
            "You are GhostAttend's post-setup conversation agent. "
            "You must reply with strict JSON only. "
            "Choose either a natural reply or one or more tool calls. "
            "Use tools for schedule changes, course management, session control, runtime questions, and screenshots. "
            "Use session.ask_runtime for fresh class-session questions such as screenshots or activity checks. "
            "Never rely on regex; reason from the structured request."
        )
        tool_spec = {
            "tools": [
                "courses.list",
                "courses.update",
                "courses.add",
                "courses.deactivate",
                "schedule.replace_from_images",
                "schedule.patch_from_images",
                "schedule.patch_from_text",
                "session.start",
                "session.cancel",
                "session.status",
                "session.ask_runtime",
            ]
        }
        user_payload = {
            "request": request.model_dump(mode="json"),
            "tool_spec": tool_spec,
            "output_format": {
                "mode": "reply | tool",
                "message": "string",
                "tool_calls": [{"name": "tool.name", "args": {}}],
            },
        }
        raw = await self._llm_callable(
            settings.AGENT_LLM_PROVIDER,
            settings.AGENT_LLM_MODEL,
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False),
        )
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            payload = json.loads(raw[start : end + 1] if start != -1 and end != -1 else raw)
            tool_calls = [ToolCall.model_validate(item) for item in payload.get("tool_calls", [])]
            return ConversationAgentResponse(
                mode=payload.get("mode", "reply"),
                message=payload.get("message", ""),
                tool_calls=tool_calls,
            )
        except Exception:
            return self._fallback(request)

    def _fallback(self, request: ConversationAgentRequest) -> ConversationAgentResponse:
        lowered = request.message_text.casefold()
        if "screenshot" in lowered or "ekran" in lowered or "chat" in lowered or "konus" in lowered:
            return ConversationAgentResponse(
                mode="tool",
                message="Aktif oturuma bakiyorum.",
                tool_calls=[ToolCall(name="session.ask_runtime", args={"question": request.message_text})],
            )
        if "simdi" in lowered or "hemen" in lowered or "join" in lowered or "katil" in lowered:
            return ConversationAgentResponse(
                mode="tool",
                message="Dersi baslatmak icin kayitli dersleri kontrol ediyorum.",
                tool_calls=[ToolCall(name="session.start", args={"course_name_query": request.message_text})],
            )
        if request.attachments:
            return ConversationAgentResponse(
                mode="tool",
                message="Paylastigin gorseli kullanarak programi guncelliyorum.",
                tool_calls=[ToolCall(name="schedule.replace_from_images", args={})],
            )
        if "bugun" in lowered or "next" in lowered or "yak" in lowered or "ders" in lowered:
            return ConversationAgentResponse(
                mode="tool",
                message="Ders durumuna bakiyorum.",
                tool_calls=[ToolCall(name="session.status", args={})],
            )
        return ConversationAgentResponse(mode="reply", message="Nasil yardim etmemi istedigini biraz daha acik yazar misin?")
