from uuid import UUID

from app.domain.schemas import ToolResult
from app.repos.human_input import HumanInputRepository
from app.tools.base import ToolExecutionMixin
from app.tools.schemas import RequestHumanInputInput


class RequestHumanInputTool(ToolExecutionMixin):
    def __init__(self, human_inputs: HumanInputRepository, timeout_seconds: int) -> None:
        self.human_inputs = human_inputs
        self.timeout_seconds = timeout_seconds

    async def __call__(self, params: RequestHumanInputInput) -> ToolResult:
        async def operation() -> ToolResult:
            request = await self.human_inputs.create(
                session_id=UUID(params.session_id),
                user_id=params.user_id,
                tool_name=params.tool_name,
                reason=params.reason,
                prompt=params.prompt,
                screenshot_path=params.screenshot_path,
                timeout_seconds=self.timeout_seconds,
            )
            return ToolResult(
                success=True,
                message=f"Human input requested: {request.id}",
                screenshot_path=params.screenshot_path,
            )

        return await self.execute_with_timeout(self.timeout_seconds, operation)
