"""Runtime planner that turns goals and snapshots into validated tool calls."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from src.core.config import settings
from src.runtime.models import BrowserSnapshot, PlannerDecision, RuntimeGoal


class RuntimePlanner:
    """Small LLM planner for the runtime loop."""

    def __init__(self, llm_callable):
        self._llm_callable = llm_callable

    async def plan(
        self,
        *,
        goal: RuntimeGoal,
        snapshot: BrowserSnapshot,
        recent_steps: list[dict[str, Any]],
    ) -> dict[str, Any]:
        system_prompt = (
            "You are GhostAttend's runtime browser planner. "
            "Reply with strict JSON only. "
            "Output schema: {\"tool\": string, \"args\": object, \"reason\": string}. "
            "Allowed tools: browser.snapshot, browser.click, browser.type, browser.press, "
            "browser.navigate, browser.wait_for, browser.evaluate, browser.screenshot, "
            "browser.network_summary, browser.console_summary, finish, fail."
        )
        user_payload = {
            "goal": goal.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "recent_steps": recent_steps[-6:],
        }
        raw = await self._llm_callable(
            settings.AGENT_LLM_PROVIDER,
            settings.AGENT_LLM_MODEL,
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False),
        )
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            parsed = json.loads(raw[start : end + 1] if start != -1 and end != -1 else raw)
            decision = PlannerDecision.model_validate(parsed)
            return {
                "ok": True,
                "tool": decision.tool,
                "args": decision.args,
                "reason": decision.reason,
                "raw": raw,
            }
        except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            return {
                "ok": False,
                "error": f"planner_decode_failed: {exc}",
                "raw": raw,
            }
