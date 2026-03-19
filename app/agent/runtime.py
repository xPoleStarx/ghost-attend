from __future__ import annotations

from dataclasses import dataclass, field

from app.agent.dispatcher import AgentDispatcher
from app.agent.graph import SimpleAgentGraph
from app.agent.state import AgentState, build_initial_state


@dataclass(slots=True)
class AgentRuntimeStore:
    states: dict[str, AgentState] = field(default_factory=dict)

    def get_or_create(self, session_id: str, user_id: int, user_timezone: str) -> AgentState:
        state = self.states.get(session_id)
        if state is None:
            state = build_initial_state(session_id, user_id, user_timezone)
            self.states[session_id] = state
        return state

    def clear(self, session_id: str) -> None:
        self.states.pop(session_id, None)


class AgentRuntimeService:
    def __init__(self, dispatcher: AgentDispatcher, store: AgentRuntimeStore | None = None) -> None:
        self.dispatcher = dispatcher
        self.store = store or AgentRuntimeStore()
        self.graph = SimpleAgentGraph(
            dispatcher=self.dispatcher.dispatch,
            resume_handler=self.dispatcher.resume,
        )

    async def handle_message(
        self,
        *,
        session_id: str,
        user_id: int,
        user_timezone: str,
        message: str,
        schedule: list[dict[str, object]] | None = None,
    ) -> AgentState:
        state = self.store.get_or_create(session_id, user_id, user_timezone)
        if schedule is not None:
            state["schedule"] = schedule
        state["messages"].append(message)
        result_state = await self.graph.run(state)
        self.store.states[session_id] = result_state
        return result_state
