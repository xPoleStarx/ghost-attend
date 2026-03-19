from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.domain.enums import HumanInputStatus, MeetingState, OnboardingStep


class ToolResult(BaseModel):
    success: bool
    message: str
    screenshot_path: str | None = None


class CourseCandidate(BaseModel):
    name: str
    day_of_week: str
    start_local: str
    end_local: str
    teams_link: HttpUrl | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    source_fragment: str | None = None


class ScheduleCandidate(BaseModel):
    courses: list[CourseCandidate]
    warnings: list[str] = Field(default_factory=list)
    needs_confirmation: bool = True
    confidence: float = Field(ge=0.0, le=1.0)


class HumanInputRequestPayload(BaseModel):
    request_id: str
    session_id: str
    user_id: int
    tool_name: str
    reason: str
    prompt: str
    screenshot_path: str | None = None
    status: HumanInputStatus
    expires_at: datetime


class AuditEvent(BaseModel):
    user_id: int
    event_type: str
    session_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SessionRuntimeView(BaseModel):
    session_id: str
    user_id: int
    meeting_state: MeetingState
    awaiting_human_input: bool
    pending_tool: str | None = None


class IntentMatch(BaseModel):
    tool_name: str
    course_id: int | None = None
    course_name: str | None = None
    requires_confirmation: bool = False
    candidate_courses: list[dict[str, Any]] = Field(default_factory=list)


class SchedulerJobPlan(BaseModel):
    user_id: int
    course_id: int
    job_type: str
    run_at: datetime
    idempotency_key: str


class RecoveryTaskPlan(BaseModel):
    user_id: int
    session_id: str
    requires_login: bool = True


class ConflictReport(BaseModel):
    has_conflicts: bool
    pairs: list[tuple[str, str]] = Field(default_factory=list)


class OnboardingPrompt(BaseModel):
    step: OnboardingStep
    message: str
    schedule_candidate: ScheduleCandidate | None = None
    is_complete: bool = False
