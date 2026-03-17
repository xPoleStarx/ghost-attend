"""
GhostAttend — Runtime Ekran Analizi

Agent çalışırken ekranı analiz etmek için kullanılan Vision LLM servisi.
DYS sayfası tanıma, buton tespiti, MFA algılama gibi görevler.
"""

import base64
import json
import re

from src.core.config import settings
from src.core.logging import get_logger
from src.vision.prompts import MFA_DETECT_PROMPT, SCREEN_ANALYZE_PROMPT

log = get_logger(__name__)


def _extract_json_block(text: str) -> str:
    """LLM yanıtından JSON bloğunu çıkar."""
    pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()

    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1:
        return text[brace_start : brace_end + 1]

    return text


async def _call_vision_llm(image_bytes: bytes, prompt: str, mime_type: str = "image/png") -> str:
    """Vision LLM'i çağır (config'deki provider ile)."""
    provider = settings.AGENT_LLM_PROVIDER

    if provider == "google":
        import google.generativeai as genai

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel(settings.VISION_LLM_MODEL)

        response = await model.generate_content_async(
            [
                {"mime_type": mime_type, "data": base64.standard_b64encode(image_bytes).decode()},
                prompt,
            ],
            generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=1024),
        )
        return response.text

    elif provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        b64 = base64.standard_b64encode(image_bytes).decode()

        response = await client.chat.completions.create(
            model=settings.VISION_LLM_MODEL,
            max_tokens=1024,
            temperature=0.1,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64}"}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.choices[0].message.content or ""

    elif provider == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        response = await client.messages.create(
            model=settings.VISION_LLM_MODEL,
            max_tokens=1024,
            messages=[{
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
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.content[0].text

    else:
        raise ValueError(f"Desteklenmeyen provider: {provider}")


async def analyze_screen(
    screenshot_bytes: bytes,
    mime_type: str = "image/png",
) -> dict:
    """
    Ekran görüntüsünü analiz et.

    Returns:
        {
            "page_type": str,
            "description": str,
            "action_needed": str,
            "elements": list[dict],
            "warnings": list[str]
        }
    """
    log.info("vision.screen_analyze_start", image_size=len(screenshot_bytes))

    try:
        raw = await _call_vision_llm(screenshot_bytes, SCREEN_ANALYZE_PROMPT, mime_type)
        json_str = _extract_json_block(raw)
        result = json.loads(json_str)

        log.info("vision.screen_analyze_complete", page_type=result.get("page_type"))
        return result

    except Exception as e:
        log.error("vision.screen_analyze_failed", error=str(e))
        return {
            "page_type": "unknown",
            "description": f"Analiz başarısız: {e}",
            "action_needed": "",
            "elements": [],
            "warnings": [str(e)],
        }


async def detect_mfa(
    screenshot_bytes: bytes,
    mime_type: str = "image/png",
) -> dict:
    """
    MFA/2FA ekranı tespit et.

    Returns:
        {
            "mfa_detected": bool,
            "mfa_type": str,
            "description": str,
            "input_field_visible": bool,
            "action": str
        }
    """
    log.info("vision.mfa_detect_start")

    try:
        raw = await _call_vision_llm(screenshot_bytes, MFA_DETECT_PROMPT, mime_type)
        json_str = _extract_json_block(raw)
        result = json.loads(json_str)

        log.info(
            "vision.mfa_detect_complete",
            mfa_detected=result.get("mfa_detected"),
            mfa_type=result.get("mfa_type"),
        )
        return result

    except Exception as e:
        log.error("vision.mfa_detect_failed", error=str(e))
        return {
            "mfa_detected": False,
            "mfa_type": "none",
            "description": f"Tespit başarısız: {e}",
            "input_field_visible": False,
            "action": "",
        }
