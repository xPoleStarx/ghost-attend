from app.browser.runtime import BrowserContextManager
from app.domain.enums import MeetingState
from app.domain.schemas import ToolResult
from app.tools.base import ToolExecutionMixin
from app.tools.schemas import LeaveMeetingInput


class LeaveMeetingTool(ToolExecutionMixin):
    def __init__(self, browser_contexts: BrowserContextManager, timeout_seconds: int) -> None:
        self.browser_contexts = browser_contexts
        self.timeout_seconds = timeout_seconds

    async def __call__(self, params: LeaveMeetingInput) -> ToolResult:
        async def operation() -> ToolResult:
            handle = await self.browser_contexts.get_context(params.user_id)
            if handle is None:
                return ToolResult(success=False, message="No active browser session.")
            if handle.meeting_state == MeetingState.IDLE:
                return ToolResult(success=True, message="No meeting is currently active.")
            handle.meeting_state = MeetingState.LEAVING
            left_handle = await self.browser_contexts.mark_left(params.user_id)
            screenshot_path = None
            if left_handle is not None:
                screenshot_path = await self.browser_contexts.runtime.capture_screenshot(
                    left_handle, "left"
                )
            return ToolResult(success=True, message="Left meeting.", screenshot_path=screenshot_path)

        return await self.execute_with_timeout(self.timeout_seconds, operation)
