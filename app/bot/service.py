from __future__ import annotations

from pathlib import Path

from app.domain.schemas import OnboardingPrompt
from app.services.app_runtime import ApplicationRuntime
from app.services.course_runtime import serialize_courses_for_agent


class GhostAttendBotService:
    def __init__(self, runtime: ApplicationRuntime) -> None:
        self.runtime = runtime

    async def handle_start(self, telegram_id: int) -> str:
        async with self.runtime.container() as container:
            coordinator = self.runtime.build_onboarding_coordinator(container)
            prompt = await coordinator.begin(telegram_id)
            return prompt.message

    async def handle_text_message(self, telegram_id: int, text: str) -> str:
        async with self.runtime.container() as container:
            onboarding = self.runtime.build_onboarding_coordinator(container)
            draft = self.runtime.bot_state_store.get_onboarding(telegram_id)
            if draft is not None and not draft.is_ready_to_activate():
                prompt = await onboarding.handle_text(telegram_id, text)
                if prompt.is_complete:
                    self.runtime.bot_state_store.clear_onboarding(telegram_id)
                return self._render_onboarding_prompt(prompt)

            user = await container.user_repository.get_by_telegram_id(telegram_id)
            if user is None:
                prompt = await onboarding.begin(telegram_id)
                return prompt.message
            active_session = await container.session_repository.get_active_for_user(user.id)
            if active_session is None:
                active_session = await container.session_repository.create(user.id, {"source": "chat"})
            courses = await container.course_repository.list_active_for_user(user.id)
            coordinator = self.runtime.build_agent_coordinator(container)
            return await coordinator.handle_message(
                session_id=str(active_session.id),
                user_id=telegram_id,
                user_timezone=user.timezone,
                message=text,
                schedule=serialize_courses_for_agent(courses),
            )

    async def handle_image_message(self, telegram_id: int, image_path: Path) -> str:
        async with self.runtime.container() as container:
            coordinator = self.runtime.build_onboarding_coordinator(container)
            prompt = await coordinator.handle_image(telegram_id, image_path)
            return self._render_onboarding_prompt(prompt)

    async def handle_photo_message(
        self,
        telegram_id: int,
        image_path: Path,
        caption: str | None = None,
    ) -> str:
        async with self.runtime.container() as container:
            coordinator = self.runtime.build_onboarding_coordinator(container)
            draft = self.runtime.bot_state_store.get_onboarding(telegram_id)
            if draft is None:
                await coordinator.begin(telegram_id)
            if caption and caption.strip():
                prompt = await coordinator.handle_text(telegram_id, caption)
                if prompt.is_complete:
                    self.runtime.bot_state_store.clear_onboarding(telegram_id)
                    return self._render_onboarding_prompt(prompt)
            prompt = await coordinator.handle_image(telegram_id, image_path)
            if prompt.is_complete:
                self.runtime.bot_state_store.clear_onboarding(telegram_id)
            return self._render_onboarding_prompt(prompt)

    async def handle_status(self, telegram_id: int) -> str:
        async with self.runtime.container() as container:
            user = await container.user_repository.get_by_telegram_id(telegram_id)
            if user is None:
                return "No user profile found. Send /start to begin onboarding."
            session = await container.session_repository.get_active_for_user(user.id)
            if session is None:
                return "No active session. Send /start to begin or resume."
            browser_handle = await container.browser_context_manager.get_context(telegram_id)
            if browser_handle is None:
                return f"Session {session.id} is active but no browser context is currently loaded."
            return (
                f"Session: {session.id}\n"
                f"Meeting state: {browser_handle.meeting_state.value}\n"
                f"Logged in: {browser_handle.is_logged_in}\n"
                f"Active course: {browser_handle.active_course_name or 'None'}"
            )

    async def handle_screenshot(self, telegram_id: int) -> str:
        return await self.handle_text_message(telegram_id, "/screenshot")

    async def handle_quit(self, telegram_id: int) -> str:
        async with self.runtime.container() as container:
            user = await container.user_repository.get_by_telegram_id(telegram_id)
            if user is None:
                return "No active profile found."
            session = await container.session_repository.close_active_for_user(user.id)
            await container.browser_context_manager.destroy_context(telegram_id)
            self.runtime.bot_state_store.clear_onboarding(telegram_id)
            if session is None:
                return "No active session to close."
            return f"Session {session.id} closed and browser context destroyed."

    def _render_onboarding_prompt(self, prompt: OnboardingPrompt) -> str:
        if prompt.schedule_candidate is None:
            return prompt.message
        course_lines = [
            f"- {course.name} | {course.day_of_week} | {course.start_local}-{course.end_local}"
            for course in prompt.schedule_candidate.courses
        ]
        warnings = "\n".join(f"Warning: {warning}" for warning in prompt.schedule_candidate.warnings)
        details = "\n".join(course_lines)
        blocks = [prompt.message]
        if details:
            blocks.append(details)
        if warnings:
            blocks.append(warnings)
        return "\n".join(blocks)
