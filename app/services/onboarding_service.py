from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from app.domain.enums import OnboardingStep
from app.domain.schemas import CourseCandidate, OnboardingPrompt
from app.repos.courses import CourseRepository
from app.repos.sessions import SessionRepository
from app.repos.users import UserRepository
from app.security.crypto import CredentialCipher
from app.services.llm_onboarding import LLMOnboardingAssistant
from app.services.conflicts import CourseWindow, ScheduleConflictDetector
from app.services.onboarding import OnboardingDraft
from app.services.schedule_ingestion import ScheduleIngestionService
from app.services.timezone import TimezoneNormalizer


class OnboardingService:
    def __init__(
        self,
        *,
        user_repository: UserRepository,
        course_repository: CourseRepository,
        session_repository: SessionRepository,
        cipher: CredentialCipher,
        schedule_ingestion: ScheduleIngestionService,
        timezone_normalizer: TimezoneNormalizer,
        llm_assistant: LLMOnboardingAssistant,
        conflict_detector: ScheduleConflictDetector | None = None,
    ) -> None:
        self.user_repository = user_repository
        self.course_repository = course_repository
        self.session_repository = session_repository
        self.cipher = cipher
        self.schedule_ingestion = schedule_ingestion
        self.timezone_normalizer = timezone_normalizer
        self.llm_assistant = llm_assistant
        self.conflict_detector = conflict_detector or ScheduleConflictDetector()

    async def begin(self, telegram_id: int) -> tuple[OnboardingDraft, OnboardingPrompt]:
        draft = OnboardingDraft(telegram_id=telegram_id)
        payload = await self.llm_assistant.compose_opening_prompt()
        return draft, OnboardingPrompt(
            step=draft.step,
            message=payload.message,
            is_complete=False,
        )

    async def handle_text(self, draft: OnboardingDraft, text: str) -> OnboardingPrompt:
        cleaned = text.strip()
        if draft.step == OnboardingStep.COMPLETED:
            return OnboardingPrompt(step=draft.step, message="Onboarding already completed.", is_complete=True)
        if draft.step == OnboardingStep.SCHEDULE_CONFIRMATION and self._has_confirmable_schedule(draft):
            analysis = await self.llm_assistant.analyze_message(
                message=cleaned,
                current_state=self._current_state(draft),
                has_schedule_candidate=self._has_confirmable_schedule(draft),
            )
            if analysis.confirmation or analysis.schedule_action == "confirm":
                draft.confirmation_received = True
                return await self._activate(draft)
            if self._apply_schedule_edit_command(
                draft,
                cleaned,
                courses_to_remove=analysis.courses_to_remove,
            ):
                draft.step = self._next_step(draft)
                return await self._build_followup_prompt(draft)
            draft.schedule_candidate = self.schedule_ingestion.parse_text(cleaned)
            if not self._has_confirmable_schedule(draft):
                draft.step = OnboardingStep.SCHEDULE_INPUT
            return await self._build_followup_prompt(draft)
        analysis = await self.llm_assistant.analyze_message(
            message=cleaned,
            current_state=self._current_state(draft),
            has_schedule_candidate=self._has_confirmable_schedule(draft),
        )
        if analysis.university_url:
            draft.university_url = analysis.university_url
        if analysis.email:
            draft.email = analysis.email
        if analysis.password:
            draft.password = analysis.password
        if analysis.timezone:
            draft.timezone = analysis.timezone
        if analysis.schedule_text:
            draft.schedule_candidate = self.schedule_ingestion.parse_text(analysis.schedule_text)
            draft.step = OnboardingStep.SCHEDULE_CONFIRMATION
        else:
            draft.step = self._next_step(draft)
        if analysis.confirmation and draft.schedule_candidate is not None:
            draft.confirmation_received = True
            return await self._activate(draft)
        return await self._build_followup_prompt(draft)

    async def handle_image(self, draft: OnboardingDraft, image_path: Path) -> OnboardingPrompt:
        parsed_candidate = await self.schedule_ingestion.parse_image(image_path)
        if parsed_candidate.courses or draft.schedule_candidate is None:
            draft.schedule_candidate = parsed_candidate
        else:
            draft.schedule_candidate.warnings.extend(parsed_candidate.warnings)
        draft.step = (
            OnboardingStep.SCHEDULE_CONFIRMATION
            if self._has_confirmable_schedule(draft)
            else OnboardingStep.SCHEDULE_INPUT
        )
        return await self._build_followup_prompt(draft)

    async def _activate(self, draft: OnboardingDraft) -> OnboardingPrompt:
        if not draft.is_ready_to_activate():
            return OnboardingPrompt(
                step=draft.step,
                message="Onboarding is not complete yet. Missing required fields.",
                schedule_candidate=draft.schedule_candidate,
            )
        course_rows: list[dict[str, str | None]] = []
        normalized_windows: list[CourseWindow] = []
        assert draft.schedule_candidate is not None
        for index, course in enumerate(draft.schedule_candidate.courses, start=1):
            normalized = self.timezone_normalizer.normalize_course_window(
                day_of_week=course.day_of_week,
                start_local=course.start_local,
                end_local=course.end_local,
                timezone_name=draft.timezone or "Europe/Istanbul",
            )
            course_rows.append(
                {
                    "name": course.name,
                    "start_day_of_week_utc": normalized.start_day_of_week_utc,
                    "end_day_of_week_utc": normalized.end_day_of_week_utc,
                    "start_time_utc": normalized.start_time_utc,
                    "end_time_utc": normalized.end_time_utc,
                    "teams_link": None if course.teams_link is None else str(course.teams_link),
                }
            )
            normalized_windows.append(
                CourseWindow(
                    course_id=index,
                    name=course.name,
                    start_day_of_week_utc=normalized.start_day_of_week_utc,
                    start_time_utc=normalized.start_time_utc,
                    end_day_of_week_utc=normalized.end_day_of_week_utc,
                    end_time_utc=normalized.end_time_utc,
                )
            )
        conflicts = self.conflict_detector.find_conflicts(normalized_windows)
        if conflicts:
            pairs = [f"{left.name} / {right.name}" for left, right in conflicts]
            return OnboardingPrompt(
                step=OnboardingStep.SCHEDULE_CONFIRMATION,
                message=(
                    "Conflicting classes detected. Manual confirmation is required before activation: "
                    + ", ".join(pairs)
                ),
                schedule_candidate=draft.schedule_candidate,
                is_complete=False,
            )
        encrypted_email = self.cipher.encrypt(draft.email or "")
        encrypted_password = self.cipher.encrypt(draft.password or "")
        user = await self.user_repository.create(
            telegram_id=draft.telegram_id,
            email=encrypted_email,
            password=encrypted_password,
            timezone=draft.timezone or "Europe/Istanbul",
            university_url=draft.university_url or "",
        )
        await self.course_repository.create_many(user.id, course_rows)
        session = await self.session_repository.create(user.id, {"source": "onboarding"})
        draft.step = OnboardingStep.COMPLETED
        return OnboardingPrompt(
            step=draft.step,
            message=f"Onboarding complete. Session {session.id} is ready.",
            schedule_candidate=draft.schedule_candidate,
            is_complete=True,
        )

    async def _build_followup_prompt(self, draft: OnboardingDraft) -> OnboardingPrompt:
        payload = await self.llm_assistant.compose_followup_prompt(
            current_state=self._current_state(draft),
            has_schedule_candidate=self._has_confirmable_schedule(draft),
            schedule_candidate=draft.schedule_candidate,
        )
        return OnboardingPrompt(
            step=draft.step,
            message=payload.message,
            schedule_candidate=draft.schedule_candidate,
            is_complete=False,
        )

    def _current_state(self, draft: OnboardingDraft) -> dict[str, str | None]:
        return {
            "university_url": draft.university_url,
            "email": draft.email,
            "password": "***" if draft.password else None,
            "timezone": draft.timezone,
        }

    def _next_step(self, draft: OnboardingDraft) -> OnboardingStep:
        if not draft.university_url:
            return OnboardingStep.UNIVERSITY_URL
        if not draft.email:
            return OnboardingStep.EMAIL
        if not draft.password:
            return OnboardingStep.PASSWORD
        if not draft.timezone:
            return OnboardingStep.TIMEZONE
        if not self._has_confirmable_schedule(draft):
            return OnboardingStep.SCHEDULE_INPUT
        return OnboardingStep.SCHEDULE_CONFIRMATION

    def _has_confirmable_schedule(self, draft: OnboardingDraft) -> bool:
        return draft.schedule_candidate is not None and bool(draft.schedule_candidate.courses)

    def _apply_schedule_edit_command(
        self,
        draft: OnboardingDraft,
        text: str,
        *,
        courses_to_remove: list[str] | None = None,
    ) -> bool:
        if draft.schedule_candidate is None or not draft.schedule_candidate.courses:
            return False
        normalized_message = self._normalize_text(text)
        requested_removals = [
            self._normalize_text(item)
            for item in (courses_to_remove or [])
            if self._normalize_text(item)
        ]
        has_remove_intent = any(
            keyword in normalized_message for keyword in ("kaldir", "sil", "cikar", "remove", "delete")
        )
        if not has_remove_intent and not requested_removals:
            return False
        matched_names: list[str] = []
        remaining_courses: list[CourseCandidate] = []
        for course in draft.schedule_candidate.courses:
            normalized_name = self._normalize_text(course.name)
            should_remove = normalized_name and normalized_name in normalized_message
            if not should_remove and requested_removals:
                should_remove = any(
                    candidate in normalized_name
                    or normalized_name in candidate
                    for candidate in requested_removals
                )
            if should_remove:
                matched_names.append(course.name)
                continue
            remaining_courses.append(course)
        if not matched_names:
            return False
        draft.schedule_candidate.courses = remaining_courses
        draft.schedule_candidate.warnings = [
            warning
            for warning in draft.schedule_candidate.warnings
            if not warning.startswith("Updated schedule:")
        ]
        removed_summary = ", ".join(sorted(set(matched_names)))
        draft.schedule_candidate.warnings.append(f"Updated schedule: removed {removed_summary}.")
        if not draft.schedule_candidate.courses:
            draft.step = OnboardingStep.SCHEDULE_INPUT
        return True

    def _normalize_text(self, value: str) -> str:
        ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()
