from app.browser.adapters import UniversityAdapter
from app.browser.navigator import BrowserUseNavigator
from app.browser.runtime import BrowserContextManager
from app.domain.enums import MeetingState
from app.domain.schemas import ToolResult
from app.tools.base import ToolExecutionMixin
from app.tools.schemas import JoinTeamsMeetingInput


class JoinTeamsMeetingTool(ToolExecutionMixin):
    def __init__(
        self,
        browser_contexts: BrowserContextManager,
        university_adapter: UniversityAdapter,
        navigator: BrowserUseNavigator,
        page_timeout_ms: int,
        timeout_seconds: int,
    ) -> None:
        self.browser_contexts = browser_contexts
        self.university_adapter = university_adapter
        self.navigator = navigator
        self.page_timeout_ms = page_timeout_ms
        self.timeout_seconds = timeout_seconds

    async def __call__(self, params: JoinTeamsMeetingInput) -> ToolResult:
        async def operation() -> ToolResult:
            handle = await self.browser_contexts.get_or_create_context(params.user_id, params.session_id)
            if not handle.is_logged_in:
                return ToolResult(success=False, message="Login required before joining a meeting.")
            if handle.meeting_state == MeetingState.IN_MEETING:
                if handle.active_course_id == params.course_id:
                    return ToolResult(success=True, message="Already in the requested meeting.")
                return ToolResult(
                    success=False,
                    message="A different meeting is already active. Leave it before joining another.",
                )
            handle.meeting_state = MeetingState.JOINING
            meeting_link = await self.university_adapter.extract_meeting_link(
                params.user_id, params.course_name
            )
            if not meeting_link:
                waiting_handle = await self.browser_contexts.mark_waiting_room(
                    params.user_id, params.course_id, params.course_name
                )
                screenshot_path = None
                if waiting_handle is not None:
                    screenshot_path = await self.browser_contexts.runtime.capture_screenshot(
                        waiting_handle, "waiting-room"
                    )
                return ToolResult(
                    success=True,
                    message="Meeting is not available yet. Waiting room mode activated.",
                    screenshot_path=screenshot_path,
                )
            await self.browser_contexts.runtime.goto(handle, meeting_link, timeout_ms=self.page_timeout_ms)
            if handle.browser_context is not None:
                await self.navigator.run_task(
                    (
                        "Join the Microsoft Teams meeting with microphone and camera disabled. "
                        "If a pre-join page appears, complete the safe join flow."
                    ),
                    handle.browser_context,
                )
            joined_handle = await self.browser_contexts.mark_joined(
                params.user_id, params.course_id, params.course_name
            )
            screenshot_path = None
            if joined_handle is not None:
                screenshot_path = await self.browser_contexts.runtime.capture_screenshot(
                    joined_handle, "joined"
                )
            return ToolResult(
                success=True,
                message=f"Joined meeting for {params.course_name}.",
                screenshot_path=screenshot_path,
            )

        return await self.execute_with_timeout(self.timeout_seconds, operation)
