from types import SimpleNamespace

import pytest

from src.core.exceptions import AgentJoinFailed
from src.runtime.engine import RuntimeEngine
from src.runtime.guardrails import RuntimeGuardrails
from src.runtime.models import BrowserElementRef, BrowserSnapshot, RuntimeGoal


def test_guardrails_block_microphone_actions():
    guardrails = RuntimeGuardrails()
    with pytest.raises(AgentJoinFailed):
        guardrails.assert_action_allowed(
            "browser.click",
            element=BrowserElementRef(ref="e1", role="button", name="Microphone", text="Turn mic on"),
        )


@pytest.mark.asyncio
async def test_runtime_engine_answers_activity_question_from_snapshot():
    class FakeBrowserService:
        async def snapshot(self, session_id: str):
            return BrowserSnapshot(
                snapshot_id="snap-1",
                tab_id="tab-1",
                url="https://example.com",
                title="Meeting",
                timestamp=__import__("datetime").datetime.utcnow(),
                elements=[],
                page_signals={"meeting_ui_detected": True, "modal_present": False, "mfa_prompt_detected": False},
            )

        async def screenshot(self, session_id: str):
            return b"img"

    runtime = RuntimeEngine(
        session_id="session-1",
        user_id=123,
        browser_service=FakeBrowserService(),
        planner=SimpleNamespace(plan=None),
    )

    result = await runtime.answer_user_request("is anyone speaking in the class, is there any activity in the chat?")
    assert "meeting arayuzu gorunuyor" in result.answer


@pytest.mark.asyncio
async def test_runtime_engine_executes_planner_until_finish():
    snapshots = [
        BrowserSnapshot(
            snapshot_id="snap-1",
            tab_id="tab-1",
            url="https://example.com",
            title="Page 1",
            timestamp=__import__("datetime").datetime.utcnow(),
            elements=[BrowserElementRef(ref="e1", role="link", name="Join", text="Join", selector="a:nth-of-type(1)", clickable=True)],
            page_signals={},
        ),
        BrowserSnapshot(
            snapshot_id="snap-2",
            tab_id="tab-1",
            url="https://example.com/meeting",
            title="Meeting",
            timestamp=__import__("datetime").datetime.utcnow(),
            elements=[],
            page_signals={"meeting_ui_detected": True},
        ),
    ]

    class FakeBrowserService:
        def __init__(self):
            self.calls = []
            self.snapshot_index = 0

        async def snapshot(self, session_id: str):
            snap = snapshots[min(self.snapshot_index, len(snapshots) - 1)]
            self.snapshot_index += 1
            return snap

        async def click(self, session_id: str, ref: str):
            self.calls.append(("click", ref))
            return {"clicked": ref}

        async def type(self, session_id: str, ref: str, text: str):
            raise AssertionError("type should not be called")

        async def press(self, session_id: str, key: str):
            raise AssertionError("press should not be called")

        async def navigate(self, session_id: str, url: str):
            raise AssertionError("navigate should not be called")

        async def evaluate(self, session_id: str, expression: str):
            raise AssertionError("evaluate should not be called")

        async def wait_for(self, session_id: str, milliseconds: int):
            return {"waited_ms": milliseconds}

        async def screenshot(self, session_id: str):
            return b"img"

        async def network_summary(self, session_id: str):
            return {}

        async def console_summary(self, session_id: str):
            return {}

    class FakePlanner:
        def __init__(self):
            self.calls = 0

        async def plan(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"ok": True, "tool": "browser.click", "args": {"ref": "e1"}, "reason": "join button found"}
            return {"ok": True, "tool": "finish", "args": {}, "reason": "joined"}

    engine = RuntimeEngine(
        session_id="session-1",
        user_id=123,
        browser_service=FakeBrowserService(),
        planner=FakePlanner(),
    )

    result = await engine.run_goal(RuntimeGoal(instruction="join the meeting"))
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_runtime_engine_invalid_planner_output_fails_closed():
    class FakeBrowserService:
        async def snapshot(self, session_id: str):
            return BrowserSnapshot(
                snapshot_id="snap-1",
                tab_id="tab-1",
                url="https://example.com",
                title="Page 1",
                timestamp=__import__("datetime").datetime.utcnow(),
                elements=[],
                page_signals={},
            )

    class FakePlanner:
        async def plan(self, **kwargs):
            return {"ok": False, "error": "planner_decode_failed: invalid json", "raw": "oops"}

    engine = RuntimeEngine(
        session_id="session-1",
        user_id=123,
        browser_service=FakeBrowserService(),
        planner=FakePlanner(),
    )

    with pytest.raises(AgentJoinFailed):
        await engine.run_goal(RuntimeGoal(instruction="join the meeting"))


@pytest.mark.asyncio
async def test_runtime_engine_emits_progress_updates_for_custom_runtime():
    class FakeNotifier:
        def __init__(self):
            self.screenshots = []
            self.messages = []

        async def send_screenshot(self, **kwargs):
            self.screenshots.append(kwargs)
            return True

        async def send_message(self, **kwargs):
            self.messages.append(kwargs)
            return True

    snapshots = [
        BrowserSnapshot(
            snapshot_id="snap-1",
            tab_id="tab-1",
            url="https://example.com/login",
            title="Login",
            timestamp=__import__("datetime").datetime.utcnow(),
            elements=[BrowserElementRef(ref="e1", role="button", name="Login", text="Login", selector="button", clickable=True)],
            page_signals={"login_form_detected": True},
        ),
        BrowserSnapshot(
            snapshot_id="snap-2",
            tab_id="tab-1",
            url="https://example.com/meeting",
            title="Meeting",
            timestamp=__import__("datetime").datetime.utcnow(),
            elements=[],
            page_signals={"meeting_ui_detected": True},
        ),
    ]

    class FakeBrowserService:
        def __init__(self):
            self.snapshot_index = 0

        def attach_session(self, session):
            return None

        def detach_session(self, session_id: str):
            return None

        async def snapshot(self, session_id: str):
            snap = snapshots[min(self.snapshot_index, len(snapshots) - 1)]
            self.snapshot_index += 1
            return snap

        async def screenshot(self, session_id: str):
            return b"img"

        async def click(self, session_id: str, ref: str):
            return {"clicked": ref}

        async def type(self, session_id: str, ref: str, text: str):
            raise AssertionError("type should not be called")

        async def press(self, session_id: str, key: str):
            raise AssertionError("press should not be called")

        async def navigate(self, session_id: str, url: str):
            raise AssertionError("navigate should not be called")

        async def evaluate(self, session_id: str, expression: str):
            raise AssertionError("evaluate should not be called")

        async def wait_for(self, session_id: str, milliseconds: int):
            return {"waited_ms": milliseconds}

        async def network_summary(self, session_id: str):
            return {}

        async def console_summary(self, session_id: str):
            return {}

    class FakePlanner:
        def __init__(self):
            self.calls = 0

        async def plan(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {"ok": True, "tool": "browser.click", "args": {"ref": "e1"}, "reason": "login"}
            return {"ok": True, "tool": "finish", "args": {}, "reason": "joined"}

    notifier = FakeNotifier()
    engine = RuntimeEngine(
        session_id="session-1",
        user_id=123,
        browser_service=FakeBrowserService(),
        planner=FakePlanner(),
        notifier=notifier,
    )

    await engine.attach(SimpleNamespace())
    result = await engine.run_goal(RuntimeGoal(instruction="join the meeting"))

    assert result["status"] == "completed"
    captions = [item["caption"] for item in notifier.screenshots]
    assert any("Tarayici acildi" in caption for caption in captions)
    assert any("Giris ekrani" in caption for caption in captions)
    assert any("meeting arayuzu" in caption.lower() for caption in captions)
    assert any("baglanti tamamlandi" in caption.lower() for caption in captions)
