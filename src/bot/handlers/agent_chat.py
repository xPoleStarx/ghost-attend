"""
GhostAttend — Agentic Chat Handler

Kurulumdan sonra kullanıcıların doğal dil ile sistemle konuşmasını sağlar.
LLM, tool-call benzeri JSON çıktısı üretir; bot bu tool'ları çalıştırır.
"""

from __future__ import annotations

import json
from datetime import time

from telegram import Update
from telegram.ext import ContextTypes

from src.bot.utils.safe_text import escape_dynamic_text
from src.core.constants import DAYS_TR
from src.core.logging import get_logger

log = get_logger(__name__)


def _parse_time_hhmm(value: str) -> time:
    return time.fromisoformat(value.strip())


def _day_to_int(day_tr: str) -> int:
    day_tr = day_tr.strip()
    if day_tr not in DAYS_TR:
        raise ValueError(f"Geçersiz gün: {day_tr}")
    return DAYS_TR[day_tr]


async def handle_agent_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Normal metin mesajlarını agent chat olarak ele al.
    / komutları ve ConversationHandler içi mesajlar bu handler'a düşmez.
    """
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    if not text:
        return

    # Kullanıcıya hızlı geri bildirim
    processing = await update.message.reply_text("💭 Anlıyorum, hemen bakıyorum...")

    from src.core.config import settings
    from src.db.connection import get_session
    from src.db.repositories.credential import CredentialRepository
    from src.db.repositories.course import CourseRepository
    from src.scheduler.lesson_scheduler import schedule_all_courses_for_user
    from src.vision.schedule_parser import _extract_json_block

    async with get_session() as session:
        cred_repo = CredentialRepository(session)
        dys_url = await cred_repo.get_dys_url_for_user(user.id)

        course_repo = CourseRepository(session)
        courses = await course_repo.get_user_courses(user.id, active_only=True)

        courses_payload = [
            {
                "id": str(c.id),
                "name": c.name,
                "day_of_week": c.day_of_week,
                "start_time": c.start_time.strftime("%H:%M"),
                "end_time": c.end_time.strftime("%H:%M"),
                "platform": c.platform,
                "direct_url": c.direct_url,
                "is_online": c.is_online,
                "is_active": c.is_active,
            }
            for c in courses
        ]

        tool_spec = {
            "tools": [
                {
                    "name": "list_courses",
                    "description": "Kayıtlı dersleri listeler.",
                    "args": {},
                },
                {
                    "name": "update_course_time",
                    "description": "Bir dersin gün/saatini değiştirir ve yeniden zamanlar.",
                    "args": {
                        "course_name_query": "string (örn: 'Kariyer')",
                        "day": "string (örn: 'Salı') opsiyonel",
                        "start_time": "string HH:MM opsiyonel",
                        "end_time": "string HH:MM opsiyonel",
                    },
                },
                {
                    "name": "add_course",
                    "description": "Yeni ders ekler ve yeniden zamanlar.",
                    "args": {
                        "name": "string",
                        "day": "string (Pazartesi..Pazar)",
                        "start_time": "string HH:MM",
                        "end_time": "string HH:MM",
                        "platform": "string opsiyonel (teams/zoom/meet/unknown)",
                        "direct_url": "string opsiyonel",
                    },
                },
                {
                    "name": "deactivate_course",
                    "description": "Bir dersi pasifleştirir (zamanlamadan çıkar) ve yeniden zamanlar.",
                    "args": {"course_name_query": "string"},
                },
                {
                    "name": "help",
                    "description": "Kısa örneklerle yardım mesajı üretir.",
                    "args": {},
                },
            ]
        }

        system_prompt = f"""
Sen GhostAttend'in otonom asistanısın. Kullanıcı Telegram üzerinden doğal dilde istek yazar.

ELİNDEKİ DURUM:
- user_id: {user.id}
- dys_url_var_mi: {"evet" if dys_url else "hayır"}
- kayıtlı_dersler (JSON): {json.dumps(courses_payload, ensure_ascii=False)}
- tool'lar (JSON): {json.dumps(tool_spec, ensure_ascii=False)}

GÖREV:
- Kullanıcı isteğini en uygun tool ile gerçekleştir.
- Eğer tool gerekmiyorsa kısa cevap ver.

ÇIKTI FORMATI (SADECE JSON):
```json
{{
  "action": "tool" | "reply",
  "tool": "tool_adı (action=tool ise zorunlu)",
  "args": {{ ... }},
  "message": "kullanıcıya gönderilecek kısa mesaj"
}}
```

KURALLAR:
- Sadece JSON döndür, başka metin ekleme.
- Ders seçerken course_name_query ile en iyi eşleşeni seç. Birden fazla güçlü aday varsa en olası olanı seç ve message içinde ne yaptığını belirt.
- Eksik bilgi varsa action=reply ile net bir soru sor (ama mümkünse mevcut veriden çıkarım yap).
"""

        raw = await _call_llm(settings.AGENT_LLM_PROVIDER, settings.AGENT_LLM_MODEL, system_prompt, text)
        try:
            payload = json.loads(_extract_json_block(raw))
        except Exception:
            payload = {"action": "reply", "message": raw[:500]}

        action = payload.get("action", "reply")
        message = payload.get("message", "Tamam.")

        if action != "tool":
            await _safe_delete(processing)
            await update.message.reply_text(message)
            return

        tool = payload.get("tool")
        args = payload.get("args") or {}

        try:
            if tool == "help":
                await _safe_delete(processing)
                await update.message.reply_text(
                    "Şunları yazabilirsin:\n"
                    "- \"Kariyer Planlama dersini Salı 14:00-15:30 yap\"\n"
                    "- \"Veri Yapıları dersini pasifleştir\"\n"
                    "- \"Yeni ders ekle: Yapay Zeka, Perşembe 10:00-11:30\"\n"
                    "- \"Derslerimi listele\""
                )
                return

            if tool == "list_courses":
                if not courses:
                    await _safe_delete(processing)
                    await update.message.reply_text("Henüz ders kaydın yok. /upload_schedule ile ekleyebilirsin.")
                    return
                lines = ["📚 Kayıtlı dersler:\n"]
                inv_days = {v: k for k, v in DAYS_TR.items()}
                for c in courses:
                    lines.append(
                        f"- **{escape_dynamic_text(c.name, parse_mode='Markdown')}**: "
                        f"{inv_days.get(c.day_of_week,'?')} {c.start_time.strftime('%H:%M')}-{c.end_time.strftime('%H:%M')}"
                    )
                await _safe_delete(processing)
                await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
                return

            if tool == "update_course_time":
                name_q = str(args.get("course_name_query", "")).strip()
                if not name_q:
                    raise ValueError("course_name_query gerekli")

                matches = await course_repo.find_by_name(user.id, name_q, active_only=True, limit=5)
                if not matches:
                    await _safe_delete(processing)
                    await update.message.reply_text(
                        f"❌ \"{escape_dynamic_text(name_q, parse_mode='Markdown')}\" ile eşleşen ders bulamadım. /courses ile kontrol edebilirsin.",
                        parse_mode="Markdown",
                    )
                    return

                target = matches[0]
                day = args.get("day")
                start_s = args.get("start_time")
                end_s = args.get("end_time")

                day_int = _day_to_int(day) if day else None
                start_t = _parse_time_hhmm(start_s) if start_s else None
                end_t = _parse_time_hhmm(end_s) if end_s else None

                await course_repo.update_schedule(
                    target.id,
                    day_of_week=day_int,
                    start_time=start_t,
                    end_time=end_t,
                )
                await session.commit()

                # Zamanlamayı yenile
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Güncellendi ve yeniden zamanlandı.")
                return

            if tool == "add_course":
                name = str(args.get("name", "")).strip()
                day = str(args.get("day", "")).strip()
                start_s = str(args.get("start_time", "")).strip()
                end_s = str(args.get("end_time", "")).strip()
                platform = str(args.get("platform", "teams")).strip() or "teams"
                direct_url = args.get("direct_url")

                if not (name and day and start_s and end_s):
                    raise ValueError("name, day, start_time, end_time gerekli")

                await course_repo.create(
                    user_id=user.id,
                    name=name,
                    day_of_week=_day_to_int(day),
                    start_time=_parse_time_hhmm(start_s),
                    end_time=_parse_time_hhmm(end_s),
                    platform=platform,
                    direct_url=str(direct_url).strip() if direct_url else None,
                )
                await session.commit()
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Ders eklendi ve zamanlandı.")
                return

            if tool == "deactivate_course":
                name_q = str(args.get("course_name_query", "")).strip()
                if not name_q:
                    raise ValueError("course_name_query gerekli")

                matches = await course_repo.find_by_name(user.id, name_q, active_only=True, limit=5)
                if not matches:
                    await _safe_delete(processing)
                    await update.message.reply_text("❌ Eşleşen ders bulamadım.")
                    return

                target = matches[0]
                await course_repo.set_active(target.id, False)
                await session.commit()
                await schedule_all_courses_for_user(user.id)

                await _safe_delete(processing)
                await update.message.reply_text(message or "✅ Ders pasifleştirildi ve zamanlama güncellendi.")
                return

            await _safe_delete(processing)
            await update.message.reply_text("⚠️ Bu isteği şu an otomatik yapamıyorum. /help yazabilirsin.")

        except Exception as e:
            log.error("agent_chat.tool_failed", user_id=user.id, tool=str(tool), error=str(e), exc_info=True)
            await _safe_delete(processing)
            await update.message.reply_text(
                f"❌ İşlem başarısız: {escape_dynamic_text(str(e)[:200], parse_mode='Markdown')}",
                parse_mode="Markdown",
            )


async def _safe_delete(message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _call_llm(provider: str, model: str, system_prompt: str, user_text: str) -> str:
    """
    Basit LLM çağrısı: tool-call yerine JSON üretmesini ister.
    """
    if provider == "google":
        import google.generativeai as genai

        from src.core.config import settings

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        m = genai.GenerativeModel(model)
        combined = system_prompt + "\n\nKullanıcı: " + user_text
        resp = await m.generate_content_async(
            combined,
            generation_config=genai.GenerationConfig(temperature=0.2, max_output_tokens=2048),
        )
        return resp.text or ""

    if provider == "openai":
        from openai import AsyncOpenAI

        from src.core.config import settings

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.2,
            max_tokens=2048,
        )
        return resp.choices[0].message.content or ""

    if provider == "anthropic":
        import anthropic

        from src.core.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        resp = await client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
        return resp.content[0].text

    raise ValueError(f"Desteklenmeyen LLM provider: {provider}")

