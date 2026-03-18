"""Shared LLM invocation helpers."""

from __future__ import annotations

from src.core.logging import get_logger

log = get_logger(__name__)


async def call_llm(provider: str, model: str, system_prompt: str, user_text: str) -> str:
    """Call a text LLM and return the raw text response."""
    if provider == "google":
        import google.generativeai as genai

        from src.core.config import settings

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        llm = genai.GenerativeModel(
            model_name=model,
            system_instruction=system_prompt,
        )
        response = await llm.generate_content_async(user_text)
        return getattr(response, "text", "") or ""

    if provider == "openai":
        from openai import AsyncOpenAI

        from src.core.config import settings

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        response = await client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        return response.choices[0].message.content or ""

    if provider == "anthropic":
        import anthropic

        from src.core.config import settings

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        response = await client.messages.create(
            model=model,
            max_tokens=1200,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}],
        )
        text_chunks = [block.text for block in response.content if getattr(block, "type", "") == "text"]
        return "\n".join(text_chunks)

    raise ValueError(f"Unsupported LLM provider: {provider}")
