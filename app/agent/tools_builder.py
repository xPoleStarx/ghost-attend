from app.container import AppContainer
from app.agent.dispatcher import AgentDispatcher
from app.agent.runtime import AgentRuntimeService, AgentRuntimeStore
from app.agent.dispatcher import ToolCallable
from app.browser.navigator import BrowserUseNavigator
from app.tools.join_teams_meeting import JoinTeamsMeetingTool
from app.tools.leave_meeting import LeaveMeetingTool
from app.tools.login_to_dys import LoginToDysTool
from app.tools.request_human_input import RequestHumanInputTool
from app.tools.take_screenshot import TakeScreenshotTool


def build_tools(container: AppContainer) -> dict[str, ToolCallable]:
    navigator = BrowserUseNavigator()
    request_human_input_tool = RequestHumanInputTool(
        container.human_input_repository,
        container.settings.human_input_timeout_seconds,
    )
    return {
        "login_to_dys": LoginToDysTool(
            container.browser_context_manager,
            container.university_adapter,
            navigator,
            request_human_input_tool,
            container.settings.page_timeout_ms,
            container.settings.max_tool_timeout_seconds,
        ),
        "join_teams_meeting": JoinTeamsMeetingTool(
            container.browser_context_manager,
            container.university_adapter,
            navigator,
            container.settings.page_timeout_ms,
            container.settings.max_tool_timeout_seconds,
        ),
        "leave_meeting": LeaveMeetingTool(
            container.browser_context_manager,
            container.settings.max_tool_timeout_seconds,
        ),
        "take_screenshot": TakeScreenshotTool(
            container.browser_context_manager,
            container.settings.screenshot_dir,
            container.settings.max_tool_timeout_seconds,
        ),
        "request_human_input": request_human_input_tool,
    }


def build_agent_runtime(
    container: AppContainer, store: AgentRuntimeStore | None = None
) -> AgentRuntimeService:
    tools = build_tools(container)
    dispatcher = AgentDispatcher(tools=tools)
    return AgentRuntimeService(dispatcher=dispatcher, store=store)
