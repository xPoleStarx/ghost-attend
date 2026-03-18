"""Typed tool registry for the conversation agent."""

from __future__ import annotations

from datetime import date, datetime, timedelta, time
from typing import Any
from uuid import UUID

from src.conversation.models import ToolResult
from src.core.constants import DAYS_TR
from src.runtime.ipc import RuntimeIPC


def _normalize_course_name(name: str) -> str:
    return " ".join(name.casefold().split())


def _pick_best_course(courses: list[object], query: str) -> object | None:
    query_norm = _normalize_course_name(query)
    best = None
    best_score = -1
    for course in courses:
        name = _normalize_course_name(getattr(course, "name", ""))
        score = 0
        if query_norm == name:
            score += 100
        if query_norm and query_norm in name:
            score += 50
        score += len(set(query_norm.split()) & set(name.split())) * 10
        if score > best_score:
            best = course
            best_score = score
    return best if best_score > 0 else None


def _extract_time_value(text: str) -> str | None:
    import re

    normalized = (text or "").casefold().replace(" ", "")
    match = re.search(r"\b(?P<hour>[01]?\d|2[0-3])[:\.](?P<minute>[0-5]\d)\b", normalized)
    if match:
        return f"{int(match.group('hour')):02d}:{match.group('minute')}"

    match = re.search(r"\b(?P<hour>[01]\d|2[0-3])(?P<minute>[0-5]\d)\b", normalized)
    if match:
        return f"{int(match.group('hour')):02d}:{match.group('minute')}"
    return None


def _extract_direct_url(text: str) -> str | None:
    import re

    match = re.search(r"(https?://\S+)", text or "")
    if not match:
        return None
    return match.group(1).rstrip(".,)")


def _extract_day_value(text: str) -> str | None:
    normalized = _normalize_course_name(text)
    for day_name in DAYS_TR:
        if _normalize_course_name(day_name) in normalized:
            return day_name
    return None


def _shift_time_preserving_duration(start: time, duration_minutes: int) -> time:
    shifted = datetime.combine(date.today(), start) + timedelta(minutes=duration_minutes)
    return shifted.time().replace(second=0, microsecond=0)


class ConversationToolRegistry:
    """Executes conversation tools against repositories and runtime state."""

    def __init__(
        self,
        *,
        user_id: int,
        session,
        course_repo,
        credential_repo,
        session_repo,
        notifier=None,
        schedule_all_courses=None,
        schedule_images_parser=None,
        attend_task=None,
        runtime_ipc: RuntimeIPC | None = None,
    ):
        self.user_id = user_id
        self.session = session
        self.course_repo = course_repo
        self.credential_repo = credential_repo
        self.session_repo = session_repo
        self.notifier = notifier
        self.schedule_all_courses = schedule_all_courses
        self.schedule_images_parser = schedule_images_parser
        self.attend_task = attend_task
        self.runtime_ipc = runtime_ipc

    async def execute(self, tool_name: str, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        method_name = f"_tool_{tool_name.replace('.', '_')}"
        method = getattr(self, method_name, None)
        if method is None:
            return ToolResult(ok=False, message=f"Desteklenmeyen tool: {tool_name}")
        return await method(args, context)

    def _conversation_state(self, context: dict[str, Any]) -> dict[str, Any]:
        return context.setdefault("conversation_state", {})

    def _remember_course(self, context: dict[str, Any], course: object, *, intent: str | None = None) -> None:
        state = self._conversation_state(context)
        state["last_referenced_course_id"] = str(getattr(course, "id"))
        state["last_referenced_course_name"] = getattr(course, "name", "")
        if intent:
            state["last_schedule_intent"] = intent

    async def _resolve_course_target(self, query: str, context: dict[str, Any]) -> object | None:
        courses = list(context.get("courses") or [])
        state = self._conversation_state(context)

        if query:
            matches = await self.course_repo.find_by_name(self.user_id, query, active_only=True, limit=5)
            target = _pick_best_course(matches, query)
            if target is not None:
                return target

        remembered_id = str(state.get("last_referenced_course_id") or "").strip()
        if remembered_id:
            try:
                target = await self.course_repo.get_by_id(UUID(remembered_id))
            except (ValueError, TypeError):
                target = None
            if target is not None and getattr(target, "is_active", True):
                return target

        remembered_name = str(state.get("last_referenced_course_name") or "").strip()
        if remembered_name:
            matches = await self.course_repo.find_by_name(self.user_id, remembered_name, active_only=True, limit=5)
            target = _pick_best_course(matches, remembered_name)
            if target is not None:
                return target

        if len(courses) == 1:
            return courses[0]

        message_text = str(context.get("message_text") or "").strip()
        if message_text and courses:
            target = _pick_best_course(courses, message_text)
            if target is not None:
                return target

        return None

    async def _tool_courses_list(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        courses = context["courses"]
        if not courses:
            return ToolResult(message="Henuz kayitli dersin yok.")
        lines = ["Kayitli derslerin:"]
        inv_days = {v: k for k, v in DAYS_TR.items()}
        for course in courses:
            lines.append(
                f"- {course.name}: {inv_days.get(course.day_of_week, '?')} {course.start_time.strftime('%H:%M')}-{course.end_time.strftime('%H:%M')}"
            )
        return ToolResult(message="\n".join(lines))

    async def _tool_courses_update(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        raw_text = str(args.get("raw_text") or context.get("message_text") or "").strip()
        query = str(args.get("course_name_query", "")).strip()
        target = await self._resolve_course_target(query, context)
        if target is None:
            return ToolResult(ok=False, message="Hangi dersi guncellememi istedigini anlayamadim.")

        start_time_value = str(args.get("start_time") or "").strip() or (_extract_time_value(raw_text) or "")
        end_time_value = str(args.get("end_time") or "").strip() or ""
        day_value = str(args.get("day") or "").strip() or (_extract_day_value(raw_text) or "")
        direct_url = str(args.get("direct_url") or "").strip() or (_extract_direct_url(raw_text) or "")

        values: dict[str, Any] = {}
        if day_value:
            values["day_of_week"] = DAYS_TR[day_value]

        if start_time_value:
            new_start = time.fromisoformat(start_time_value)
            values["start_time"] = new_start
            if not end_time_value:
                duration_minutes = int(
                    (
                        datetime.combine(date.today(), target.end_time)
                        - datetime.combine(date.today(), target.start_time)
                    ).total_seconds()
                    // 60
                )
                values["end_time"] = _shift_time_preserving_duration(new_start, duration_minutes)

        if end_time_value:
            values["end_time"] = time.fromisoformat(end_time_value)

        if not values and not direct_url:
            self._remember_course(context, target, intent="course_update")
            return ToolResult(ok=False, message=f"{target.name} icin neyi degistirmemi istedigini biraz daha acik yaz.")

        await self.course_repo.update_schedule(target.id, **values)
        if direct_url:
            await self.course_repo.update_direct_url(target.id, direct_url)
        await self.session.commit()
        if self.schedule_all_courses:
            await self.schedule_all_courses(self.user_id)

        self._remember_course(context, target, intent="course_update")
        current_day = {v: k for k, v in DAYS_TR.items()}.get(values.get("day_of_week", target.day_of_week), "?")
        current_start = values.get("start_time", target.start_time).strftime("%H:%M")
        current_end = values.get("end_time", target.end_time).strftime("%H:%M")
        return ToolResult(message=f"{target.name} dersini {current_day} {current_start}-{current_end} olarak guncelledim.")

    async def _tool_courses_add(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        required = ["name", "day", "start_time", "end_time"]
        if any(not args.get(field) for field in required):
            return ToolResult(ok=False, message="Yeni ders eklemek icin ad, gun, baslangic ve bitis saatleri gerekli.")
        course = await self.course_repo.create(
            user_id=self.user_id,
            name=str(args["name"]).strip(),
            day_of_week=DAYS_TR[str(args["day"]).strip()],
            start_time=time.fromisoformat(str(args["start_time"]).strip()),
            end_time=time.fromisoformat(str(args["end_time"]).strip()),
            platform=str(args.get("platform") or "teams"),
            direct_url=str(args.get("direct_url")).strip() if args.get("direct_url") else None,
        )
        await self.session.commit()
        if self.schedule_all_courses:
            await self.schedule_all_courses(self.user_id)
        self._remember_course(context, course, intent="course_update")
        return ToolResult(message=f"{args['name']} dersini ekledim.")

    async def _tool_courses_deactivate(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = str(args.get("course_name_query", "")).strip()
        matches = await self.course_repo.find_by_name(self.user_id, query, active_only=True, limit=5)
        target = _pick_best_course(matches, query)
        if target is None:
            return ToolResult(ok=False, message="Pasiflestirecek bir ders bulamadim.")
        await self.course_repo.set_active(target.id, False)
        await self.session.commit()
        if self.schedule_all_courses:
            await self.schedule_all_courses(self.user_id)
        self._remember_course(context, target, intent="course_update")
        return ToolResult(message=f"{target.name} dersini pasiflestirdim.")

    async def _apply_schedule_parse(self, *, images, extra_text: str | None, replace: bool) -> ToolResult:
        if self.schedule_images_parser is None:
            return ToolResult(ok=False, message="Program guncelleme servisi hazir degil.")
        result = await self.schedule_images_parser(images=images, extra_text=extra_text)
        parsed_courses = [item.model_dump() for item in result.courses]
        if replace:
            await self.course_repo.deactivate_all_for_user(self.user_id)
        await self.course_repo.bulk_create_from_parsed(self.user_id, parsed_courses)
        await self.session.commit()
        if self.schedule_all_courses:
            await self.schedule_all_courses(self.user_id)
        prefix = "Programi bastan guncelledim." if replace else "Programdaki degisiklikleri isledim."
        return ToolResult(message=f"{prefix}\n{len(parsed_courses)} ders aktif durumda.", data={"warnings": result.parse_warnings})

    async def _tool_schedule_replace_from_images(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return await self._apply_schedule_parse(images=context.get("images", []), extra_text=context.get("text_hint"), replace=True)

    async def _tool_schedule_patch_from_images(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return await self._apply_schedule_parse(images=context.get("images", []), extra_text=context.get("text_hint"), replace=False)

    async def _tool_schedule_patch_from_text(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        return await self._apply_schedule_parse(images=[], extra_text=str(args.get("text") or context.get("text_hint") or ""), replace=False)

    async def _tool_session_start(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        query = str(args.get("course_name_query", "")).strip() or context["message_text"]
        lowered = query.casefold()
        if any(
            phrase in lowered
            for phrase in ["katilacak misin", "katÄ±lacak mÄ±sÄ±n", "girecek misin", "derste misin", "hangi ders"]
        ):
            return ToolResult(ok=False, message="Bu bir durum sorusu gibi gorunuyor. Istersen aktif durumu kontrol edebilirim.")
        matches = await self.course_repo.find_by_name(self.user_id, query, active_only=True, limit=5)
        target = _pick_best_course(matches, query)
        if target is None:
            return ToolResult(ok=False, message="Baslatmam icin ders adini biraz daha net yazman gerekiyor.")
        dys_url = await self.credential_repo.get_dys_url_for_user(self.user_id)
        if not dys_url and not target.direct_url:
            return ToolResult(ok=False, message="Bu ders icin kullanabilecegim bir DYS veya direkt link yok.")
        self._remember_course(context, target)
        self.attend_task.delay(
            user_id=self.user_id,
            course_id=str(target.id),
            course_name=target.name,
            dys_url=dys_url or "",
            start_time=target.start_time.strftime("%H:%M"),
            end_time=target.end_time.strftime("%H:%M"),
            direct_url=target.direct_url,
            dys_search_hint=getattr(target, "dys_search_hint", None),
        )
        return ToolResult(message=f"{target.name} icin katilim oturumunu baslattim.")

    async def _tool_session_cancel(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        active = await self.session_repo.get_active_session(self.user_id)
        if active is None:
            return ToolResult(message="Su anda iptal edilecek aktif bir oturum yok.")
        if self.notifier and hasattr(self.notifier, "send_message"):
            await self.notifier.send_message(self.user_id, "Aktif oturumu iptal etme istegini aldim.")
        return ToolResult(message="Aktif oturumu iptal etme istegini ilettim.")

    async def _tool_session_status(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        active = await self.session_repo.get_active_session(self.user_id)
        if active is None:
            courses = list(context.get("courses") or [])
            if courses:
                courses.sort(key=lambda course: (course.day_of_week, course.start_time))
                next_course = courses[0]
                self._remember_course(context, next_course)
                return ToolResult(
                    message=(
                        "Su anda aktif bir ders oturumu yok. "
                        f"Siradaki ders: {next_course.name} "
                        f"{next_course.start_time.strftime('%H:%M')}-{next_course.end_time.strftime('%H:%M')}."
                    )
                )
            return ToolResult(message="Su anda aktif bir ders oturumu yok.")
        return ToolResult(
            message=f"Su anda aktif oturum durumu: {active.status}.",
            data={"session_id": str(active.id), "status": active.status},
        )

    async def _tool_session_ask_runtime(self, args: dict[str, Any], context: dict[str, Any]) -> ToolResult:
        active = await self.session_repo.get_active_session(self.user_id)
        if active is None:
            return ToolResult(message="Su anda aktif bir oturum yok, bu yuzden canli tarayici incelemesi yapamiyorum.")
        if self.runtime_ipc is None:
            return ToolResult(message="Canli tarayici inceleme ozelligi gecici olarak kullanilamiyor.")

        record = await self.runtime_ipc.get_session(str(active.id))
        if record is None:
            return ToolResult(message="Aktif tarayici runtime'i su anda erisilebilir degil.")

        question = str(args.get("question") or context["message_text"]).strip()
        lowered = question.casefold()
        if "ekran" in lowered or "screenshot" in lowered or "goruntu" in lowered or "gÃ¶rÃ¼ntÃ¼" in lowered:
            command_type = "take_screenshot"
        elif "chat" in lowered:
            command_type = "summarize_chat"
        else:
            command_type = "inspect_activity"

        command = await self.runtime_ipc.send_command(
            session_id=str(active.id),
            command_type=command_type,
            payload={"question": question},
        )
        result = await self.runtime_ipc.await_result(command.command_id)
        if result is None:
            return ToolResult(message="Canli runtime'dan zamaninda yanit alamadim.")
        if not result.ok:
            return ToolResult(ok=False, message=result.error or "Canli runtime istegi basarisiz oldu.")

        payload = result.payload or {}
        screenshot_b64 = payload.get("screenshot_b64")
        if screenshot_b64 and self.notifier:
            screenshot_bytes = self.runtime_ipc.decode_bytes(screenshot_b64)
            await self.notifier.send_screenshot(
                user_id=self.user_id,
                screenshot_bytes=screenshot_bytes,
                caption=str(payload.get("answer") or "Guncel ekran goruntusu"),
                checkpoint_name="manual_runtime",
                session_id=str(active.id),
            )
        return ToolResult(message=str(payload.get("answer") or "Canli runtime yaniti alindi."), data=payload.get("details") or {})
