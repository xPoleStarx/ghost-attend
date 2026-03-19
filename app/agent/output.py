from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage


def _content_to_str(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                elif "text" in block:
                    parts.append(str(block["text"]))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return str(content).strip() if content is not None else ""


def last_assistant_text_for_telegram(messages: list[Any] | None) -> str:
    """Son araç çağrısı olmayan AI mesajını metin olarak döndür."""
    if not messages:
        return ""
    for m in reversed(messages):
        if not isinstance(m, AIMessage):
            continue
        if getattr(m, "tool_calls", None):
            continue
        t = _content_to_str(m.content)
        if t:
            return t[:4096]
    return ""
