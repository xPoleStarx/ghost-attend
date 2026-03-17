"""
GhostAttend — Ders Programı Parser

Vision LLM ile ders programı fotoğrafını analiz eder ve yapılandırılmış JSON döndürür.
Multi-provider desteği: Google (Gemini), OpenAI (GPT-4o-mini), Anthropic (Claude Haiku).
architecture.md Section 8.1
"""

import base64
import json
import re

from src.core.config import settings
from src.core.exceptions import ScheduleParseError
from src.core.logging import get_logger
from src.core.models import ParsedCourse, ScheduleParseResult
from src.vision.prompts import SCHEDULE_PARSE_PROMPT

log = get_logger(__name__)


def _extract_json_block(text: str) -> str:
    """
    LLM yanıtından JSON bloğunu çıkar.
    ```json ... ``` veya { ... } formatını destekler.
    """
    # Markdown code block içindeki JSON'ı bul
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    # Direkt JSON obje bul
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        return text[brace_start : brace_end + 1]

    raise ScheduleParseError(f"JSON bloğu bulunamadı. LLM yanıtı: {text[:200]}")


async def _parse_with_google(image_bytes: bytes, mime_type: str) -> str:
    """Google Gemini ile ders programı parse et."""
    import google.generativeai as genai

    genai.configure(api_key=settings.GOOGLE_API_KEY)

    model = genai.GenerativeModel(settings.VISION_LLM_MODEL)

    response = await model.generate_content_async(
        [
            {
                "mime_type": mime_type,
                "data": base64.standard_b64encode(image_bytes).decode(),
            },
            SCHEDULE_PARSE_PROMPT,
        ],
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    return response.text


async def _parse_with_openai(image_bytes: bytes, mime_type: str) -> str:
    """OpenAI GPT-4o-mini ile ders programı parse et."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    b64_image = base64.standard_b64encode(image_bytes).decode()

    response = await client.chat.completions.create(
        model=settings.VISION_LLM_MODEL,
        max_tokens=2048,
        temperature=0.1,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{b64_image}",
                        },
                    },
                    {
                        "type": "text",
                        "text": SCHEDULE_PARSE_PROMPT,
                    },
                ],
            }
        ],
    )

    return response.choices[0].message.content or ""


async def _parse_with_anthropic(image_bytes: bytes, mime_type: str) -> str:
    """Anthropic Claude ile ders programı parse et."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    response = await client.messages.create(
        model=settings.VISION_LLM_MODEL,
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": base64.standard_b64encode(image_bytes).decode(),
                        },
                    },
                    {
                        "type": "text",
                        "text": SCHEDULE_PARSE_PROMPT,
                    },
                ],
            }
        ],
    )

    return response.content[0].text


# Provider fonksiyon haritası
_PROVIDER_MAP = {
    "google": _parse_with_google,
    "openai": _parse_with_openai,
    "anthropic": _parse_with_anthropic,
}


async def parse_schedule_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
    provider: str | None = None,
) -> ScheduleParseResult:
    """
    Ders programı görselini Vision LLM ile parse et.

    Args:
        image_bytes: Görselin binary verisi
        mime_type: MIME tipi (image/jpeg, image/png)
        provider: LLM sağlayıcı (google, openai, anthropic). None ise config'den alınır.

    Returns:
        ScheduleParseResult: Parse edilmiş ders listesi

    Raises:
        ScheduleParseError: Parse başarısız olduğunda
    """
    provider = provider or settings.AGENT_LLM_PROVIDER

    parse_fn = _PROVIDER_MAP.get(provider)
    if not parse_fn:
        raise ScheduleParseError(f"Desteklenmeyen LLM provider: {provider}")

    log.info(
        "vision.parse_start",
        provider=provider,
        model=settings.VISION_LLM_MODEL,
        image_size=len(image_bytes),
        mime_type=mime_type,
    )

    try:
        # LLM'den yanıt al
        raw_response = await parse_fn(image_bytes, mime_type)

        log.info("vision.llm_response_received", response_length=len(raw_response))

        # JSON bloğunu çıkar ve parse et
        json_str = _extract_json_block(raw_response)
        data = json.loads(json_str)

        # Pydantic ile validate et
        result = ScheduleParseResult(
            courses=[ParsedCourse(**c) for c in data.get("courses", [])],
            raw_text=data.get("raw_text", ""),
            parse_warnings=data.get("parse_warnings", []),
        )

        log.info(
            "vision.parse_complete",
            course_count=len(result.courses),
            warning_count=len(result.parse_warnings),
        )

        return result

    except json.JSONDecodeError as e:
        raise ScheduleParseError(f"JSON parse hatası: {e}") from e
    except Exception as e:
        raise ScheduleParseError(f"Ders programı parse edilemedi: {e}") from e


# ── Multi-Image Provider Fonksiyonları ──

async def _parse_multi_with_google(
    images: list[tuple[bytes, str]], extra_text: str | None
) -> str:
    """Google Gemini — birden fazla görsel + opsiyonel metin."""
    import google.generativeai as genai

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel(settings.VISION_LLM_MODEL)

    content_parts: list = []
    for img_bytes, mime in images:
        content_parts.append({
            "mime_type": mime,
            "data": base64.standard_b64encode(img_bytes).decode(),
        })

    prompt_text = SCHEDULE_PARSE_PROMPT
    if extra_text:
        prompt_text += f"\n\nKullanıcının ek bilgisi:\n{extra_text}"
    content_parts.append(prompt_text)

    response = await model.generate_content_async(
        content_parts,
        generation_config=genai.GenerationConfig(
            temperature=0.1, max_output_tokens=4096,
        ),
    )
    return response.text


async def _parse_multi_with_openai(
    images: list[tuple[bytes, str]], extra_text: str | None
) -> str:
    """OpenAI GPT — birden fazla görsel + opsiyonel metin."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    content_parts = []
    for img_bytes, mime in images:
        b64 = base64.standard_b64encode(img_bytes).decode()
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })

    prompt_text = SCHEDULE_PARSE_PROMPT
    if extra_text:
        prompt_text += f"\n\nKullanıcının ek bilgisi:\n{extra_text}"
    content_parts.append({"type": "text", "text": prompt_text})

    response = await client.chat.completions.create(
        model=settings.VISION_LLM_MODEL,
        max_tokens=4096,
        temperature=0.1,
        messages=[{"role": "user", "content": content_parts}],
    )
    return response.choices[0].message.content or ""


async def _parse_multi_with_anthropic(
    images: list[tuple[bytes, str]], extra_text: str | None
) -> str:
    """Anthropic Claude — birden fazla görsel + opsiyonel metin."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    content_parts = []
    for img_bytes, mime in images:
        content_parts.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime,
                "data": base64.standard_b64encode(img_bytes).decode(),
            },
        })

    prompt_text = SCHEDULE_PARSE_PROMPT
    if extra_text:
        prompt_text += f"\n\nKullanıcının ek bilgisi:\n{extra_text}"
    content_parts.append({"type": "text", "text": prompt_text})

    response = await client.messages.create(
        model=settings.VISION_LLM_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": content_parts}],
    )
    return response.content[0].text


_MULTI_PROVIDER_MAP = {
    "google": _parse_multi_with_google,
    "openai": _parse_multi_with_openai,
    "anthropic": _parse_multi_with_anthropic,
}


async def parse_schedule_images(
    images: list[tuple[bytes, str]],
    extra_text: str | None = None,
    provider: str | None = None,
) -> ScheduleParseResult:
    """
    Birden fazla ders programı görselini ve/veya ek metni Vision LLM ile parse et.

    Args:
        images: (image_bytes, mime_type) listesi
        extra_text: Kullanıcının ek metin girdisi
        provider: LLM sağlayıcı. None ise config'den alınır.

    Returns:
        ScheduleParseResult
    """
    # Tek görsel → orijinal fonksiyonu kullan
    if len(images) == 1 and not extra_text:
        return await parse_schedule_image(images[0][0], images[0][1], provider)

    provider = provider or settings.AGENT_LLM_PROVIDER
    parse_fn = _MULTI_PROVIDER_MAP.get(provider)
    if not parse_fn:
        raise ScheduleParseError(f"Desteklenmeyen LLM provider: {provider}")

    log.info(
        "vision.multi_parse_start",
        provider=provider,
        image_count=len(images),
        has_text=bool(extra_text),
    )

    try:
        raw_response = await parse_fn(images, extra_text)
        log.info("vision.multi_llm_response", response_length=len(raw_response))

        json_str = _extract_json_block(raw_response)
        data = json.loads(json_str)

        result = ScheduleParseResult(
            courses=[ParsedCourse(**c) for c in data.get("courses", [])],
            raw_text=data.get("raw_text", ""),
            parse_warnings=data.get("parse_warnings", []),
        )

        log.info(
            "vision.multi_parse_complete",
            course_count=len(result.courses),
        )
        return result

    except json.JSONDecodeError as e:
        raise ScheduleParseError(f"JSON parse hatası: {e}") from e
    except Exception as e:
        raise ScheduleParseError(f"Ders programı parse edilemedi: {e}") from e


def format_courses_for_telegram(result: ScheduleParseResult) -> str:
    """
    Parse sonuçlarını Telegram mesajı formatına çevir.
    Inline keyboard ile birlikte kullanılır.
    """
    if not result.courses:
        return "❌ Ders programından hiç ders tespit edilemedi. Lütfen tekrar dene."

    lines = ["📚 Ders programından şunları tespit ettim:\n"]

    gun_emoji = {
        "Pazartesi": "🔵",
        "Salı": "🟢",
        "Çarşamba": "🟡",
        "Perşembe": "🟠",
        "Cuma": "🔴",
        "Cumartesi": "🟣",
        "Pazar": "⚪",
    }

    for i, course in enumerate(result.courses, 1):
        confidence = "✅" if course.guvven_skoru >= 0.8 else "❓"
        platform_text = course.platform.upper() if course.platform != "unknown" else "Belirsiz"
        emoji = gun_emoji.get(course.gun, "⚪")

        lines.append(
            f"{i}. {confidence} **{course.ders_adi}**\n"
            f"   {emoji} {course.gun} {course.baslangic_saati}–{course.bitis_saati}\n"
            f"   👨‍🏫 {course.ogretim_uyesi or 'Belirtilmemiş'}\n"
            f"   🖥️ {platform_text}"
        )

        if course.online_mi is True:
            lines.append(f"   🟢 **Online**")
        elif course.online_mi is False:
            lines.append(f"   🔴 **Yüz yüze**")
        else:
            lines.append(f"   ❓ _Online/yüz yüze belirsiz_")

        lines.append("")  # Boş satır

    if result.parse_warnings:
        lines.append("⚠️ **Uyarılar:**")
        for warning in result.parse_warnings:
            lines.append(f"  • {warning}")

    return "\n".join(lines)
