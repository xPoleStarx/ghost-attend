"""GhostAttend - Post-setup conversation handler."""

from __future__ import annotations

from datetime import datetime, time, timezone
import re
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.ext import ContextTypes

from src.agent.llm import call_llm
from src.conversation import ConversationAgent, ConversationService
from src.conversation.tools import ConversationToolRegistry
from src.core.constants import DAYS_TR
from src.core.config import settings
from src.core.logging import get_logger
from src.runtime.ipc import RuntimeIPC

log = get_logger(__name__)


_BROKEN_TURKISH_MAP = {
    "ÅŸ": "ş",
    "Ä±": "ı",
    "Ã¼": "ü",
    "Ã¶": "ö",
    "Ã§": "ç",
    "ÄŸ": "ğ",
    "Åž": "ş",
    "Ä°": "i",
    "Ãœ": "ü",
    "Ã–": "ö",
    "Ã‡": "ç",
    "Äž": "ğ",
}


def _repair_broken_text(text: str) -> str:
    repaired = text
    for broken, fixed in _BROKEN_TURKISH_MAP.items():
        repaired = repaired.replace(broken, fixed)
    return repaired


def _now_in_tz(tz_name: str) -> datetime:
    """Test-friendly timezone-aware now."""
    tz = ZoneInfo(tz_name)
    now = datetime.now(timezone.utc)
    if not hasattr(now, "astimezone"):
        return now  # type: ignore[return-value]
    return now.astimezone(tz)


def _compute_next_lesson(courses) -> object | None:
    """Pick the closest future lesson."""
    if not courses:
        return None

    now = _now_in_tz("Europe/Istanbul")
    now_minutes = now.hour * 60 + now.minute
    today_idx = now.weekday()

    best_course = None
    best_delta = None
    for course in courses:
        course_day = int(getattr(course, "day_of_week", 0))
        start: time = getattr(course, "start_time")
        course_minutes = start.hour * 60 + start.minute
        day_delta = (course_day - today_idx) % 7
        if day_delta == 0 and course_minutes <= now_minutes:
            day_delta = 7
        total_minutes = day_delta * 24 * 60 + (course_minutes - now_minutes)
        if best_delta is None or total_minutes < best_delta:
            best_delta = total_minutes
            best_course = course
    return best_course


def _detect_intent(text: str) -> str | None:
    """Compatibility helper kept for tests."""
    lowered = _repair_broken_text(text).lower().replace("ï¿½", "ş")
    manual_join_patterns = [
        r"\bdersine\s+(şimdi|hemen)\s+gir\b",
        r"\bdersine\s+katıl\b",
        r"\bdersine\s+gir\b",
        r"\bderse\s+(şimdi|hemen)\s+gir\b",
        r"\bderse\s+şimdi\s+katıl\b",
        r"\bderse\s+katılım\s+şimdi\b",
        r"\bhadi\s+derse\s+gir\b",
    ]
    if any(re.search(pattern, lowered) for pattern in manual_join_patterns):
        return "manual_join_request"

    join_patterns = [
        r"\bderse\s+gir\b",
        r"\bderse\s+girecek\s+misin\b",
        r"\bderse\s+katıl\b",
        r"\bderse\s+katılacak\s+mısın\b",
        r"\bderse\s+girmen\s+gerekiyor\b",
    ]
    if any(re.search(pattern, lowered) for pattern in join_patterns):
        return "ask_join_or_status"

    has_time = bool(re.search(r"\b([01]?\d|2[0-3])[:\.][0-5]\d\b", lowered))
    mentions_update = any(
        keyword in lowered
        for keyword in [
            "ders saatini güncelle",
            "başlangıç saatini",
            "saati güncelle",
            "saatini değiştir",
        ]
    )
    mentions_course_name = any(keyword in lowered for keyword in ["kariyer", "veri yapıları", "matematik", "dersi "])
    if has_time and mentions_update and not mentions_course_name:
        return "ambiguous_schedule_change"
    return None


def _normalize_manual_join_text(text: str) -> str:
    normalized = _repair_broken_text(text).casefold().replace("Ã¯Â¿Â½", "ş")
    normalized = (
        normalized.replace("Ã¢â‚¬â„¢", "'")
        .replace("â€™", "'")
        .replace("â€œ", '"')
        .replace("â€", '"')
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _extract_manual_join_course_query(text: str) -> str:
    normalized = _normalize_manual_join_text(text)
    match = re.search(r"(?P<course>.+?)\s+dersine\b", normalized)
    if match:
        candidate = match.group("course")
    else:
        match = re.search(r"(?P<course>.+?)\s+derse\b", normalized)
        if match:
            candidate = match.group("course")
        else:
            candidate = re.sub(
                r"\b(derse|dersine|şimdi|hemen|katıl(?:ım)?|gir|girin|girer misin|girecek misin|hadi)\b",
                " ",
                normalized,
            )

    candidate = re.sub(r"^[\"']+|[\"']+$", "", candidate).strip()
    candidate = re.sub(
        r"\b(şimdi|hemen|katıl(?:ım)?|gir|girin|hadi|beni|bir|de|da|lütfen)\b",
        " ",
        candidate,
    )
    return re.sub(r"\s+", " ", candidate).strip(" ,.:;!?-_'\"")


def _is_generic_manual_join_query(query: str) -> bool:
    normalized = _normalize_manual_join_text(query)
    if not normalized:
        return True
    return normalized in {
        "ders",
        "derse",
        "dersine",
        "canli ders",
        "canlı ders",
        "online ders",
        "toplanti",
        "toplantı",
    }


def _normalize_course_name(name: str) -> str:
    normalized = _normalize_manual_join_text(name)
    normalized = re.sub(r"[^0-9a-zçğıöşü\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _rank_manual_join_matches(query: str, matches: list[object]) -> list[tuple[int, object]]:
    query_norm = _normalize_course_name(query)
    query_tokens = set(query_norm.split())
    ranked: list[tuple[int, object]] = []
    for course in matches:
        name = getattr(course, "name", "")
        name_norm = _normalize_course_name(name)
        name_tokens = set(name_norm.split())
        score = 0
        if query_norm == name_norm:
            score += 200
        if query_norm and query_norm in name_norm:
            score += 120
        if name_norm and name_norm in query_norm:
            score += 80
        overlap = len(query_tokens & name_tokens)
        if overlap:
            score += overlap * 25
        if query_tokens and query_tokens <= name_tokens:
            score += 40
        if getattr(course, "is_active", False):
            score += 5
        ranked.append((score, course))
    ranked.sort(key=lambda item: (item[0], len(getattr(item[1], "name", ""))), reverse=True)
    return ranked


def _pick_manual_join_target(query: str, matches: list[object]) -> tuple[object | None, list[object]]:
    ranked = _rank_manual_join_matches(query, matches)
    if not ranked:
        return None, []
    top_score = ranked[0][0]
    plausible = [course for score, course in ranked if score > 0 and score >= top_score - 20]
    if top_score < 25:
        return None, plausible
    if len(plausible) == 1:
        return plausible[0], plausible
    return None, plausible


async def _collect_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    attachments: list[dict] = []
    if update.message and update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_bytes = await file.download_as_bytearray()
        attachments.append(
            {
                "kind": "image",
                "bytes": bytes(image_bytes),
                "mime_type": "image/jpeg",
                "caption": update.message.caption or "",
            }
        )
    return attachments


async def handle_agent_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle post-setup free-form chat via the conversation service."""
    user = update.effective_user
    if not user or not update.message:
        return

    text = (update.message.text or update.message.caption or "").strip()
    attachments = await _collect_attachments(update, context)
    if not text and not attachments:
        return

    from src.db.connection import get_session
    from src.db.repositories.credential import CredentialRepository
    from src.db.repositories.course import CourseRepository
    from src.db.repositories.session import SessionRepository
    from src.db.repositories.user import UserRepository
    from src.notifications.service import NotificationService
    from src.scheduler.lesson_scheduler import schedule_all_courses_for_user
    from src.scheduler.tasks import attend_lesson_task
    from src.vision.schedule_parser import parse_schedule_images
    import redis.asyncio as aioredis

    history: list[dict] = context.user_data.get("chat_history", [])
    history.append(
        {
            "role": "user",
            "text": (text or "[image]")[:500],
            "ts": datetime.utcnow().isoformat(),
        }
    )
    history = history[-10:]
    context.user_data["chat_history"] = history

    processing = await update.message.reply_text("Bakiyorum...")

    async with get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_by_id(user.id)
        user_tz = getattr(db_user, "timezone", None) or "Europe/Istanbul"

        course_repo = CourseRepository(session)
        credential_repo = CredentialRepository(session)
        session_repo = SessionRepository(session)

        courses = await course_repo.get_user_courses(user.id, active_only=True)
        active_session = await session_repo.get_active_session(user.id)

        notifier = NotificationService(bot_token="", bot=context.bot)
        redis_client = aioredis.from_url(settings.REDIS_URL)
        tool_registry = ConversationToolRegistry(
            user_id=user.id,
            session=session,
            course_repo=course_repo,
            credential_repo=credential_repo,
            session_repo=session_repo,
            notifier=notifier,
            schedule_all_courses=schedule_all_courses_for_user,
            schedule_images_parser=parse_schedule_images,
            attend_task=attend_lesson_task,
            runtime_ipc=RuntimeIPC(redis_client),
        )

        service = ConversationService(agent=ConversationAgent(_call_llm))
        response_text = await service.handle(
            user_id=user.id,
            message_text=text or (update.message.caption or "schedule image"),
            attachments=attachments,
            history=history,
            courses=courses,
            timezone_name=user_tz,
            active_session=active_session,
            tool_registry=tool_registry,
            conversation_state=context.user_data,
        )
        await session.commit()
        await redis_client.aclose()

    try:
        await processing.delete()
    except Exception:
        pass

    if response_text:
        await update.message.reply_text(response_text)


async def _call_llm(provider: str, model: str, system_prompt: str, user_text: str) -> str:
    """Compatibility wrapper for tests and conversation/runtime modules."""
    return await call_llm(provider, model, system_prompt, user_text)
