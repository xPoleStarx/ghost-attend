"""Runtime engine built around snapshots, refs, validated planner output, and IPC."""

from __future__ import annotations

from typing import Any

from src.core.exceptions import AgentJoinFailed
from src.runtime.browser import BrowserControlService
from src.runtime.guardrails import RuntimeGuardrails
from src.runtime.ipc import RuntimeIPC
from src.runtime.models import RuntimeGoal, RuntimeQuestionResult, RuntimeStateStore, RuntimeStep
from src.runtime.observer import RuntimeObserver


class RuntimeEngine:
    """Coordinates browser snapshots, planning, execution, and live IPC commands."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: int,
        browser_service: BrowserControlService,
        planner,
        notifier=None,
        session_repo=None,
        runtime_ipc: RuntimeIPC | None = None,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.browser_service = browser_service
        self.planner = planner
        self.guardrails = RuntimeGuardrails()
        self.state_store = RuntimeStateStore(session_id=session_id, user_id=user_id)
        self.observer = RuntimeObserver(
            notifier=notifier,
            session_repo=session_repo,
            state_store=self.state_store,
        )
        self.runtime_ipc = runtime_ipc

    async def attach(self, browser_session) -> None:
        self.browser_service.attach_session(browser_session)
        await self._heartbeat(status="SESSION_STARTING")
        try:
            image = await self.browser_service.screenshot(self.session_id)
        except Exception:
            image = None
        await self.observer.emit_progress(
            event_key="runtime_starting",
            user_id=self.user_id,
            session_id=self.session_id,
            caption="Tarayici acildi. Derse giris surecini baslatiyorum.",
            screenshot_bytes=image,
        )

    async def detach(self) -> None:
        self.browser_service.detach_session(self.session_id)
        if self.runtime_ipc:
            await self.runtime_ipc.clear_session(self.session_id)

    async def answer_user_request(self, request_text: str) -> RuntimeQuestionResult:
        snapshot = await self.browser_service.snapshot(self.session_id)
        self.state_store.latest_snapshot = snapshot
        lower = request_text.casefold()
        if "screenshot" in lower or "ekran" in lower:
            image = await self.browser_service.screenshot(self.session_id)
            return RuntimeQuestionResult(
                answer="Guncel ekran goruntusunu gonderiyorum.",
                screenshot_bytes=image,
                details={"snapshot_id": snapshot.snapshot_id},
            )

        signals = snapshot.page_signals
        activity_bits = []
        if signals.get("joined_confirmed"):
            activity_bits.append("derse bagli gorunuyorum")
        elif signals.get("meeting_ui_detected"):
            activity_bits.append("meeting arayuzu gorunuyor")
        if signals.get("modal_present"):
            activity_bits.append("acik bir modal veya dialog olabilir")
        if signals.get("mfa_prompt_detected"):
            activity_bits.append("dogrulama ekrani olabilir")

        if "konus" in lower or "speaking" in lower or "chat" in lower or "aktivite" in lower:
            answer = "Son snapshot'a gore " + (", ".join(activity_bits) if activity_bits else "belirgin bir aktivite sinyali gormuyorum.")
            return RuntimeQuestionResult(answer=answer, details={"snapshot_id": snapshot.snapshot_id, "signals": signals})

        return RuntimeQuestionResult(
            answer="Aktif oturuma baktim. Su anda sayfa durumu hazir gorunuyor.",
            details={"snapshot_id": snapshot.snapshot_id, "signals": signals},
        )

    async def run_goal(self, goal: RuntimeGoal, *, max_steps: int = 12) -> dict[str, Any]:
        self.state_store.goal = goal
        self.state_store.fsm_state = "SESSION_STARTING"

        for index in range(1, max_steps + 1):
            await self._drain_runtime_commands()
            snapshot = await self.browser_service.snapshot(self.session_id)
            self.state_store.latest_snapshot = snapshot
            await self._heartbeat(status=self.state_store.fsm_state)
            await self._emit_runtime_progress(snapshot)

            planner_payload = await self.planner.plan(
                goal=goal,
                snapshot=snapshot,
                recent_steps=[step.model_dump(mode="json") for step in self.state_store.steps],
            )
            if not planner_payload.get("ok"):
                self.state_store.last_error = str(planner_payload.get("error"))
                await self.observer.record_decision(
                    self.session_id,
                    {"kind": "planner_error", "error": self.state_store.last_error},
                )
                raise AgentJoinFailed(self.state_store.last_error or "Runtime planner failed to produce valid JSON.")

            tool_name = planner_payload["tool"]
            args = planner_payload.get("args") or {}
            await self.observer.record_decision(
                self.session_id,
                {
                    "kind": "planner",
                    "tool_name": tool_name,
                    "args": args,
                    "reason": planner_payload.get("reason", ""),
                },
            )
            if tool_name == "finish":
                if not self._has_completion_proof(snapshot):
                    raise AgentJoinFailed("Runtime attempted to finish without join proof.")
                self.state_store.fsm_state = "SESSION_ACTIVE"
                await self._heartbeat(status="SESSION_ACTIVE")
                await self._emit_joined_progress()
                return {"status": "completed", "raw": planner_payload.get("reason") or "completed"}
            if tool_name == "fail":
                raise AgentJoinFailed(planner_payload.get("reason") or "runtime planner failed")

            result = await self._execute(tool_name, args)
            after = await self.browser_service.snapshot(self.session_id)
            step = RuntimeStep(
                index=index,
                tool_name=tool_name,
                args=args,
                result=result,
                snapshot_id_before=snapshot.snapshot_id,
                snapshot_id_after=after.snapshot_id,
            )
            self.state_store.steps.append(step)
            self.state_store.latest_snapshot = after
            if self._has_completion_proof(after):
                self.state_store.joined_confirmed = True
                self.state_store.fsm_state = "SESSION_ACTIVE"
                await self._emit_joined_progress()
            else:
                await self._emit_runtime_progress(after)
            await self._heartbeat(status=self.state_store.fsm_state)

        raise AgentJoinFailed("Runtime exceeded the maximum number of planner steps.")

    async def _execute(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "browser.click":
            element = self.state_store.latest_snapshot and next(
                (item for item in self.state_store.latest_snapshot.elements if item.ref == args.get("ref")),
                None,
            )
            self.guardrails.assert_action_allowed(tool_name, element=element)
            return await self.browser_service.click(self.session_id, args["ref"])
        if tool_name == "browser.type":
            element = self.state_store.latest_snapshot and next(
                (item for item in self.state_store.latest_snapshot.elements if item.ref == args.get("ref")),
                None,
            )
            self.guardrails.assert_action_allowed(tool_name, element=element, value=args.get("text"))
            return await self.browser_service.type(self.session_id, args["ref"], args.get("text", ""))
        if tool_name == "browser.press":
            return await self.browser_service.press(self.session_id, args.get("key", "Enter"))
        if tool_name == "browser.navigate":
            return await self.browser_service.navigate(self.session_id, args["url"])
        if tool_name == "browser.evaluate":
            return await self.browser_service.evaluate(self.session_id, args["expression"])
        if tool_name == "browser.wait_for":
            return await self.browser_service.wait_for(self.session_id, int(args.get("milliseconds", 1000)))
        if tool_name == "browser.screenshot":
            image = await self.browser_service.screenshot(self.session_id)
            await self.observer.send_runtime_screenshot(
                user_id=self.user_id,
                session_id=self.session_id,
                screenshot_bytes=image,
                caption="Runtime screenshot",
            )
            return {"sent": True}
        if tool_name == "browser.snapshot":
            snapshot = await self.browser_service.snapshot(self.session_id)
            return {"snapshot_id": snapshot.snapshot_id, "element_count": len(snapshot.elements)}
        if tool_name == "browser.network_summary":
            return await self.browser_service.network_summary(self.session_id)
        if tool_name == "browser.console_summary":
            return await self.browser_service.console_summary(self.session_id)
        raise ValueError(f"Unsupported runtime tool: {tool_name}")

    def _has_completion_proof(self, snapshot) -> bool:
        if snapshot is None:
            return False
        page_signals = snapshot.page_signals or {}
        if page_signals.get("joined_confirmed"):
            return True
        if not self.state_store.steps:
            return False
        return bool(page_signals.get("meeting_ui_detected"))

    async def _heartbeat(self, *, status: str) -> None:
        snapshot = self.state_store.latest_snapshot
        summary = {
            "fsm_state": self.state_store.fsm_state,
            "last_error": self.state_store.last_error,
            "latest_snapshot": (
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "url": snapshot.url,
                    "title": snapshot.title,
                    "page_signals": snapshot.page_signals,
                }
                if snapshot
                else {}
            ),
            "last_tool": self.state_store.steps[-1].tool_name if self.state_store.steps else None,
        }
        if self.session_repo:
            await self.session_repo.update_metadata(
                self.session_id,
                {
                    "runtime_session": {
                        "status": status,
                        "runtime_mode": self.state_store.mode,
                        **summary,
                    }
                },
            )
        if self.runtime_ipc is None:
            return
        await self.runtime_ipc.heartbeat(
            session_id=self.session_id,
            user_id=self.user_id,
            status=status,
            runtime_mode=self.state_store.mode,
            snapshot_summary=summary,
            capabilities=["take_screenshot", "inspect_activity", "summarize_chat", "cancel"],
        )

    async def _drain_runtime_commands(self) -> None:
        if self.runtime_ipc is None:
            return
        while True:
            command = await self.runtime_ipc.consume_command(self.session_id, timeout=0)
            if command is None:
                break
            try:
                if command.command_type == "take_screenshot":
                    answer = await self.answer_user_request(command.payload.get("question") or "take a screenshot")
                    payload = {
                        "answer": answer.answer,
                        "details": answer.details,
                        "screenshot_b64": self.runtime_ipc.encode_bytes(answer.screenshot_bytes) if answer.screenshot_bytes else None,
                    }
                    await self.runtime_ipc.publish_result(
                        command_id=command.command_id,
                        session_id=self.session_id,
                        ok=True,
                        payload=payload,
                    )
                elif command.command_type in {"inspect_activity", "summarize_chat"}:
                    answer = await self.answer_user_request(command.payload.get("question") or "")
                    await self.runtime_ipc.publish_result(
                        command_id=command.command_id,
                        session_id=self.session_id,
                        ok=True,
                        payload={"answer": answer.answer, "details": answer.details},
                    )
                elif command.command_type == "cancel":
                    self.state_store.last_error = "cancelled_by_user"
                    await self.runtime_ipc.publish_result(
                        command_id=command.command_id,
                        session_id=self.session_id,
                        ok=True,
                        payload={"answer": "Runtime oturumu iptal ediliyor."},
                    )
                    raise AgentJoinFailed("Runtime cancelled by user.")
                else:
                    await self.runtime_ipc.publish_result(
                        command_id=command.command_id,
                        session_id=self.session_id,
                        ok=False,
                        error=f"Unsupported runtime command: {command.command_type}",
                    )
            except Exception as exc:
                await self.runtime_ipc.publish_result(
                    command_id=command.command_id,
                    session_id=self.session_id,
                    ok=False,
                    error=str(exc),
                )
                if command.command_type == "cancel":
                    raise

    async def _emit_runtime_progress(self, snapshot) -> None:
        if snapshot is None:
            return

        signals = snapshot.page_signals or {}
        try:
            screenshot_bytes = await self.browser_service.screenshot(self.session_id)
        except Exception:
            screenshot_bytes = None

        if signals.get("login_form_detected"):
            await self.observer.emit_progress(
                event_key="runtime_login_form",
                user_id=self.user_id,
                session_id=self.session_id,
                caption="Giris ekrani gorunuyor. Oturum acmayi deniyorum.",
                screenshot_bytes=screenshot_bytes,
            )

        if signals.get("mfa_prompt_detected"):
            await self.observer.emit_progress(
                event_key="runtime_mfa_prompt",
                user_id=self.user_id,
                session_id=self.session_id,
                caption="Dogrulama ekrani gorunuyor. Gerekirse senden MFA onayi isteyecegim.",
                screenshot_bytes=screenshot_bytes,
            )

        if signals.get("meeting_ui_detected"):
            await self.observer.emit_progress(
                event_key="runtime_meeting_ui",
                user_id=self.user_id,
                session_id=self.session_id,
                caption="Ders veya meeting arayuzu bulundu. Join adimina geciyorum.",
                screenshot_bytes=screenshot_bytes,
            )

    async def _emit_joined_progress(self) -> None:
        try:
            screenshot_bytes = await self.browser_service.screenshot(self.session_id)
        except Exception:
            screenshot_bytes = None
        await self.observer.emit_progress(
            event_key="runtime_joined",
            user_id=self.user_id,
            session_id=self.session_id,
            caption="Derse baglanti tamamlandi. Oturum aktif gorunuyor.",
            screenshot_bytes=screenshot_bytes,
        )
