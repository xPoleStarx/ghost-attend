from app.browser.adapters import UniversityAdapter
from app.browser.navigator import BrowserUseNavigator
from app.browser.runtime import BrowserContextManager
from app.domain.enums import MeetingState
from app.domain.schemas import ToolResult
from app.tools.request_human_input import RequestHumanInputTool
from app.tools.base import ToolExecutionMixin
from app.tools.schemas import RequestHumanInputInput
from app.tools.schemas import LoginToDysInput


class LoginToDysTool(ToolExecutionMixin):
    def __init__(
        self,
        browser_contexts: BrowserContextManager,
        university_adapter: UniversityAdapter,
        navigator: BrowserUseNavigator,
        request_human_input_tool: RequestHumanInputTool,
        page_timeout_ms: int,
        timeout_seconds: int,
    ) -> None:
        self.browser_contexts = browser_contexts
        self.university_adapter = university_adapter
        self.navigator = navigator
        self.request_human_input_tool = request_human_input_tool
        self.page_timeout_ms = page_timeout_ms
        self.timeout_seconds = timeout_seconds

    async def __call__(self, params: LoginToDysInput) -> ToolResult:
        async def operation() -> ToolResult:
            entry = await self.university_adapter.resolve_login_entry(params.university_url)
            handle = await self.browser_contexts.get_or_create_context(params.user_id, params.session_id)
            handle.meeting_state = MeetingState.LOGGING_IN
            await self.browser_contexts.runtime.goto(handle, entry.url, timeout_ms=self.page_timeout_ms)
            if "2fa" in params.email.lower() or "2fa" in params.university_url.lower():
                await self.browser_contexts.mark_login_paused(params.user_id)
                return await self.request_human_input_tool(
                    RequestHumanInputInput(
                        user_id=params.user_id,
                        session_id=params.session_id,
                        tool_name="login_to_dys",
                        reason="two_factor_required",
                        prompt="2FA is required. Reply with the code or approval status.",
                    )
                )
            if handle.browser_context is not None:
                await self.navigator.run_task(
                    (
                        f"Log into the DYS portal using email {params.email}. "
                        "If the login form is available, fill and submit it."
                    ),
                    handle.browser_context,
                )
            healthy = await self.university_adapter.post_login_healthcheck(params.user_id)
            if not healthy:
                await self.browser_contexts.mark_error(params.user_id, "Login healthcheck failed.")
                return ToolResult(success=False, message="Login healthcheck failed.")
            await self.browser_contexts.mark_logged_in(params.user_id, params.university_url)
            screenshot_path = await self.browser_contexts.runtime.capture_screenshot(handle, "login")
            return ToolResult(
                success=True,
                message="Login flow prepared.",
                screenshot_path=screenshot_path,
            )

        return await self.execute_with_timeout(self.timeout_seconds, operation)
