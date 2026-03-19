from collections.abc import Awaitable, Callable

from app.agent.nodes.chat import chat_response_node
from app.agent.nodes.clarify import clarify_node
from app.agent.nodes.dispatch import tool_dispatch_node
from app.agent.nodes.result import tool_result_node
from app.agent.nodes.resume import human_input_resume_node
from app.agent.nodes.router import router_node
from app.agent.state import AgentState
from app.domain.schemas import ToolResult


class SimpleAgentGraph:
    def __init__(
        self,
        dispatcher: Callable[[AgentState], Awaitable[ToolResult]],
        resume_handler: Callable[[AgentState], Awaitable[ToolResult]],
    ) -> None:
        self.dispatcher = dispatcher
        self.resume_handler = resume_handler

    async def run(self, state: AgentState) -> AgentState:
        route = await router_node(state)
        if route == "HUMAN_INPUT":
            resumed = await human_input_resume_node(state)
            resumed["tool_result"] = await self.resume_handler(resumed)
            return await tool_result_node(resumed)
        if route == "CHAT":
            return await chat_response_node(state)
        if route == "CLARIFY":
            return await clarify_node(state)
        dispatched = await tool_dispatch_node(state, self.dispatcher)
        return await tool_result_node(dispatched)
