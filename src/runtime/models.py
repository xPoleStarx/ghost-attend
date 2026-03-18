"""Typed models for the snapshot-driven runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class BrowserElementRef(BaseModel):
    """Clickable or editable page element from a snapshot."""

    ref: str
    role: str = "generic"
    name: str = ""
    text: str = ""
    selector: str | None = None
    clickable: bool = False
    editable: bool = False
    disabled: bool = False
    frame: str | None = None
    bounds: dict[str, float] | None = None


class BrowserSnapshot(BaseModel):
    """Structured representation of the current page."""

    snapshot_id: str
    tab_id: str
    url: str
    title: str
    timestamp: datetime
    format: Literal["role", "aria", "dom-lite"] = "role"
    elements: list[BrowserElementRef] = Field(default_factory=list)
    page_signals: dict[str, Any] = Field(default_factory=dict)


class RuntimeGoal(BaseModel):
    """High-level objective for the runtime agent."""

    mode: Literal["join_lesson", "user_request"] = "join_lesson"
    instruction: str
    course_name: str | None = None
    end_time: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeStep(BaseModel):
    """Single planner/executor step."""

    index: int
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    snapshot_id_before: str | None = None
    snapshot_id_after: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RuntimeQuestionResult(BaseModel):
    """Answer to a user question during an active session."""

    answer: str
    screenshot_bytes: bytes | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class RuntimeStateStore(BaseModel):
    """Persistable runtime state."""

    session_id: str
    user_id: int
    mode: str = "custom"
    goal: RuntimeGoal | None = None
    fsm_state: str = "SESSION_STARTING"
    latest_snapshot: BrowserSnapshot | None = None
    steps: list[RuntimeStep] = Field(default_factory=list)
    decision_log: list[dict[str, Any]] = Field(default_factory=list)
    last_error: str | None = None
    joined_confirmed: bool = False


class PlannerDecision(BaseModel):
    """Validated planner output."""

    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class RuntimeSessionRecord(BaseModel):
    """Cross-process runtime session state."""

    session_id: str
    user_id: int
    status: str
    runtime_mode: str
    last_heartbeat_at: datetime
    snapshot_summary: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class RuntimeCommand(BaseModel):
    """Command sent from bot process to worker-owned runtime."""

    command_id: str
    session_id: str
    command_type: Literal["take_screenshot", "inspect_activity", "summarize_chat", "cancel"]
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RuntimeCommandResult(BaseModel):
    """Result returned by the worker-owned runtime."""

    command_id: str
    session_id: str
    ok: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)
