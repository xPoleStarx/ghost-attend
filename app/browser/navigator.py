from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class BrowserUseNavigator:
    llm_client: Any | None = None

    async def run_task(self, task: str, browser_context: Any) -> bool:
        try:
            from browser_use import Agent as BrowserUseAgent
        except Exception:  # noqa: BLE001
            return False
        if self.llm_client is None:
            return False
        agent = BrowserUseAgent(task=task, llm=self.llm_client, browser_context=browser_context)
        try:
            await agent.run()
        except Exception:  # noqa: BLE001
            return False
        return True
