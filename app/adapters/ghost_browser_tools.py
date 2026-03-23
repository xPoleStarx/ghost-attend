"""browser-use Tools örneğine evaluate / find_elements / navigate sarmalayıcıları ekler."""

from __future__ import annotations

from typing import Any

from browser_use.agent.views import ActionResult
from browser_use.tools.service import Tools

from app.adapters.browser_action_guard import (
    NavigatePolicy,
    validate_evaluate_code,
    validate_find_elements_params,
    validate_navigate_url,
)


def _policy_from_session(browser_session: Any) -> NavigatePolicy | None:
    pol = getattr(browser_session, "_ghost_nav_policy", None)
    return pol if isinstance(pol, NavigatePolicy) else None


def build_ghost_guarded_tools() -> Tools:
    """Varsayılan Tools + GhostMyShit ön doğrulama (NavigatePolicy oturumda)."""
    tools = Tools()
    reg = tools.registry.registry

    # --- evaluate ---
    ra_ev = reg.actions["evaluate"]
    _orig_ev = ra_ev.function

    async def _evaluate_guarded(*, params: Any, browser_session: Any = None, **kw: Any) -> Any:
        err = validate_evaluate_code(getattr(params, "code", None))
        if err:
            return ActionResult(error=f"[Shitty guard] {err}")
        return await _orig_ev(params=params, browser_session=browser_session, **kw)

    reg.actions["evaluate"] = ra_ev.model_copy(update={"function": _evaluate_guarded})

    # --- find_elements ---
    ra_fe = reg.actions["find_elements"]
    _orig_fe = ra_fe.function

    async def _find_elements_guarded(*, params: Any, browser_session: Any = None, **kw: Any) -> Any:
        attrs = getattr(params, "attributes", None)
        if attrs is not None and not isinstance(attrs, list):
            attrs = list(attrs) if attrs else None
        err = validate_find_elements_params(getattr(params, "selector", None), attrs)
        if err:
            return ActionResult(error=f"[Shitty guard] {err}")
        return await _orig_fe(params=params, browser_session=browser_session, **kw)

    reg.actions["find_elements"] = ra_fe.model_copy(update={"function": _find_elements_guarded})

    # --- navigate ---
    ra_nav = reg.actions["navigate"]
    _orig_nav = ra_nav.function

    async def _navigate_guarded(*, params: Any, browser_session: Any = None, **kw: Any) -> Any:
        url = getattr(params, "url", None)
        pol = _policy_from_session(browser_session) if browser_session is not None else None
        err = validate_navigate_url(str(url) if url is not None else "", pol)
        if err:
            return ActionResult(error=f"[Shitty guard] {err}")
        return await _orig_nav(params=params, browser_session=browser_session, **kw)

    reg.actions["navigate"] = ra_nav.model_copy(update={"function": _navigate_guarded})

    return tools
