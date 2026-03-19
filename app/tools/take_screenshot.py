from pathlib import Path

from app.browser.runtime import BrowserContextManager
from app.domain.schemas import ToolResult
from app.tools.base import ToolExecutionMixin
from app.tools.schemas import TakeScreenshotInput


class TakeScreenshotTool(ToolExecutionMixin):
    def __init__(
        self,
        browser_contexts: BrowserContextManager,
        screenshot_dir: Path,
        timeout_seconds: int,
    ) -> None:
        self.browser_contexts = browser_contexts
        self.screenshot_dir = screenshot_dir
        self.timeout_seconds = timeout_seconds

    async def __call__(self, params: TakeScreenshotInput) -> ToolResult:
        async def operation() -> ToolResult:
            handle = await self.browser_contexts.get_context(params.user_id)
            if handle is None:
                return ToolResult(success=False, message="No active browser session.")
            screenshot_path = await self.browser_contexts.runtime.capture_screenshot(handle, "manual")
            return ToolResult(
                success=True,
                message="Screenshot captured.",
                screenshot_path=screenshot_path,
            )

        return await self.execute_with_timeout(self.timeout_seconds, operation)
