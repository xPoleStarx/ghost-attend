"""Deterministic intent policy for high-risk post-setup conversation flows."""

from __future__ import annotations

import re
from typing import Any

from src.conversation.models import ConversationPolicyDecision
from src.core.constants import DAYS_TR


def _normalize(text: str) -> str:
    text = (text or "").casefold()
    text = text.replace("â€™", "'").replace("'", " ")
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, phrases: list[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _extract_time_value(text: str) -> str | None:
    match = re.search(r"\b(?P<hour>[01]?\d|2[0-3])[:\.](?P<minute>[0-5]\d)\b", text)
    if match:
        return f"{int(match.group('hour')):02d}:{match.group('minute')}"

    match = re.search(r"\b(?P<hour>[01]\d|2[0-3])(?P<minute>[0-5]\d)\b", text)
    if match:
        return f"{int(match.group('hour')):02d}:{match.group('minute')}"
    return None


def _extract_day_value(text: str) -> str | None:
    for day_name in DAYS_TR:
        if _normalize(day_name) in text:
            return day_name
    return None


def _extract_direct_url(text: str) -> str | None:
    match = re.search(r"(https?://\S+)", text)
    if not match:
        return None
    return match.group(1).rstrip(".,)")


def _extract_course_query(text: str) -> str:
    normalized = _normalize(text)
    for pattern in (
        r"(?P<course>.+?)\s+dersine\b",
        r"(?P<course>.+?)\s+derse\b",
        r"(?P<course>.+?)\s+dersinin\b",
        r"(?P<course>.+?)\s+dersi\b",
        r"(?P<course>.+?)\s+i[Ã§c]in\b",
    ):
        match = re.search(pattern, normalized)
        if match:
            candidate = match.group("course")
            candidate = re.sub(
                r"\b(lutfen|lütfen|simdi|şimdi|hemen|katil|katıl|gir|baslat|başlat|hadi|saatini|saatini|tarihi|yanlis|yanlış)\b",
                " ",
                candidate,
            )
            return re.sub(r"\s+", " ", candidate).strip(" ,.:;!?-_")
    return ""


def _looks_like_join_request(text: str) -> bool:
    return _contains_any(
        text,
        [
            "katil simdi",
            "katıl şimdi",
            "hemen katil",
            "hemen katıl",
            "dersine katil",
            "dersine katıl",
            "derse katil",
            "derse katıl",
            "dersine gir",
            "derse gir",
            "baslat",
            "başlat",
        ],
    )


def _looks_like_status_question(text: str) -> bool:
    if "?" in text:
        return True
    return _contains_any(
        text,
        [
            "katilacak misin",
            "katılacak mısın",
            "girecek misin",
            "derste misin",
            "hangi ders",
            "ne zaman ders",
            "siradaki ders",
            "sıradaki ders",
            "aktif oturum",
            "durum ne",
        ],
    )


def _looks_like_runtime_request(text: str) -> bool:
    return _contains_any(
        text,
        [
            "ekran",
            "screenshot",
            "goruntu",
            "görüntü",
            "chat",
            "konusan",
            "konuşan",
            "aktivite",
            "kim konusuyor",
            "kim konuşuyor",
        ],
    )


def _looks_like_batch_schedule_update(text: str) -> bool:
    return _contains_any(
        text,
        [
            "program",
            "schedule",
            "yeni program",
            "tum program",
            "tüm program",
        ],
    )


def _looks_like_followup_schedule_update(text: str, state: dict[str, Any] | None) -> bool:
    if not state or not state.get("last_schedule_intent"):
        return False
    if _extract_time_value(text) or _extract_day_value(text) or _extract_direct_url(text):
        return True
    return _contains_any(
        text,
        [
            "hayir",
            "hayır",
            "degil",
            "değil",
            "yanlis",
            "yanlış",
            "onu",
            "bunu",
            "bu dersi",
            "ayni ders",
            "aynı ders",
        ],
    )


def _looks_like_course_update(text: str, state: dict[str, Any] | None) -> bool:
    if _looks_like_followup_schedule_update(text, state):
        return True
    if _extract_time_value(text) or _extract_day_value(text) or _extract_direct_url(text):
        return True
    return _contains_any(
        text,
        [
            "ders saat",
            "ders saati",
            "tarihi yanlis",
            "tarihi yanlış",
            "saatini degistir",
            "saatini değiştir",
            "saati degisti",
            "saati değişti",
            "guncelle",
            "güncelle",
            "degisti",
            "değişti",
            "yanlis",
            "yanlış",
        ],
    )


def decide_policy(
    *,
    message_text: str,
    courses: list[dict[str, Any]],
    attachments: list[dict[str, Any]],
    conversation_state: dict[str, Any] | None = None,
) -> ConversationPolicyDecision:
    normalized = _normalize(message_text)
    state = conversation_state or {}
    pending_join = state.get("pending_manual_join")
    course_query = _extract_course_query(message_text)
    parsed_start_time = _extract_time_value(normalized)
    parsed_day = _extract_day_value(normalized)
    parsed_direct_url = _extract_direct_url(message_text)

    if pending_join and normalized:
        state.pop("pending_manual_join", None)
        return ConversationPolicyDecision(
            intent_family="manual_join_followup",
            tool_name="session.start",
            tool_args={"course_name_query": message_text.strip()},
            allowed_tools=["session.start"],
        )

    if attachments or _looks_like_batch_schedule_update(normalized):
        if attachments:
            return ConversationPolicyDecision(
                intent_family="schedule_update",
                tool_name="schedule.replace_from_images",
                allowed_tools=["schedule.replace_from_images", "schedule.patch_from_images"],
            )
        return ConversationPolicyDecision(
            intent_family="schedule_update",
            tool_name="schedule.patch_from_text",
            tool_args={"text": message_text.strip()},
            allowed_tools=["schedule.patch_from_text"],
        )

    if _looks_like_course_update(normalized, state):
        tool_args: dict[str, Any] = {"raw_text": message_text.strip()}
        if course_query:
            tool_args["course_name_query"] = course_query
        if parsed_start_time:
            tool_args["start_time"] = parsed_start_time
        if parsed_day:
            tool_args["day"] = parsed_day
        if parsed_direct_url:
            tool_args["direct_url"] = parsed_direct_url

        if any(tool_args.get(key) for key in ("start_time", "day", "direct_url")):
            return ConversationPolicyDecision(
                intent_family="course_update",
                tool_name="courses.update",
                tool_args=tool_args,
                allowed_tools=["courses.update"],
            )

        return ConversationPolicyDecision(
            intent_family="course_update",
            tool_args=tool_args,
            requires_clarification=True,
            clarification_message="Bu ders icin neyi degistirmemi istersin?",
            allowed_tools=["courses.update"],
        )

    if _looks_like_runtime_request(normalized):
        return ConversationPolicyDecision(
            intent_family="runtime_question",
            tool_name="session.ask_runtime",
            tool_args={"question": message_text.strip()},
            allowed_tools=["session.ask_runtime"],
        )

    if _looks_like_status_question(normalized) and not _looks_like_join_request(normalized):
        return ConversationPolicyDecision(
            intent_family="session_status",
            tool_name="session.status",
            allowed_tools=["session.status"],
        )

    if _looks_like_join_request(normalized):
        if course_query:
            return ConversationPolicyDecision(
                intent_family="manual_join",
                tool_name="session.start",
                tool_args={"course_name_query": course_query},
                allowed_tools=["session.start"],
            )
        if len(courses) == 1:
            return ConversationPolicyDecision(
                intent_family="manual_join",
                tool_name="session.start",
                tool_args={"course_name_query": courses[0]["name"]},
                allowed_tools=["session.start"],
            )
        if conversation_state is not None:
            conversation_state["pending_manual_join"] = True
        return ConversationPolicyDecision(
            intent_family="manual_join",
            requires_clarification=True,
            clarification_message="Hangi derse katilmami istedigini yazar misin?",
            allowed_tools=["session.start"],
        )

    return ConversationPolicyDecision(intent_family="general")
