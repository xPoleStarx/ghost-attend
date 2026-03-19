from __future__ import annotations

from typing import Any

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph.runtime import Runtime

from app.agent.prompts import TASK_AGENT_SYSTEM
from app.agent.tools import build_task_tools
from app.agent.web_task_gate import should_force_run_browser_automation
from app.config.settings import Settings


def build_compiled_graph(settings: Settings, checkpointer: BaseCheckpointSaver | None = None):
    """Gemini + araçlar (browser, screenshot, kullanıcıya sor).

    Web görevi (URL / giriş / ders programı vb.) algılanınca API düzeyinde
    `tool_choice=run_browser_automation` uygulanır; model düz metinle reddedemez.
    """
    base = ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        google_api_key=settings.google_api_key,
        temperature=0.1,
    )
    tools = build_task_tools(settings)

    def select_model(state: dict[str, Any], runtime: Runtime[Any]) -> Any:
        msgs = state.get("messages") or []
        if should_force_run_browser_automation(msgs):
            return base.bind_tools(tools, tool_choice="run_browser_automation")
        return base.bind_tools(tools)

    ckpt = checkpointer or MemorySaver()
    return create_react_agent(
        select_model,
        tools,
        prompt=TASK_AGENT_SYSTEM,
        checkpointer=ckpt,
    )
