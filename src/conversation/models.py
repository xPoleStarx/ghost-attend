"""Typed conversation agent models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Single typed tool call."""

    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Result returned by a tool."""

    ok: bool = True
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SessionContext(BaseModel):
    """Minimal active-session summary for conversation planning."""

    session_id: str | None = None
    status: str = "idle"
    course_name: str | None = None
    runtime_available: bool = False
    latest_runtime_snapshot: dict[str, Any] | None = None


class ConversationAgentRequest(BaseModel):
    """Input to the conversation agent."""

    user_id: int
    message_text: str
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    courses: list[dict[str, Any]] = Field(default_factory=list)
    session: SessionContext = Field(default_factory=SessionContext)
    timezone: str = "Europe/Istanbul"
    now_local_iso: str


class ConversationAgentResponse(BaseModel):
    """Planner output from the conversation agent."""

    mode: Literal["reply", "tool"] = "reply"
    message: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ConversationPolicyDecision(BaseModel):
    """Deterministic decision made before the LLM planner runs."""

    intent_family: str = "general"
    tool_name: str | None = None
    tool_args: dict[str, Any] = Field(default_factory=dict)
    requires_clarification: bool = False
    clarification_message: str = ""
    allowed_tools: list[str] = Field(default_factory=list)
