"""
GhostAttend — Safe Text Utilities

Kullanıcıya giden metinlerde yanlışlıkla JSON-escape edilmiş string (örn: "\"\\u2705...\\n\"")
görünmesini engellemek için güvenli bir decode katmanı.
"""

from __future__ import annotations

import json
import re
from typing import Any


_UNICODE_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})")


def _decode_backslash_escapes(s: str) -> str:
    # Önce basit kaçışlar
    s = s.replace("\\r", "\r").replace("\\n", "\n").replace("\\t", "\t")

    # Sonra unicode kaçışları: \\u0131 -> ı
    def _repl(match: re.Match[str]) -> str:
        codepoint = int(match.group(1), 16)
        return chr(codepoint)

    return _UNICODE_ESCAPE_RE.sub(_repl, s)


def maybe_unescape_json_string(text: str) -> str:
    """
    Bazı katmanlarda metin yanlışlıkla `json.dumps(...)` ile string'e çevrilip tekrar gönderilebiliyor.
    Bu durumda Telegram'da "\\uXXXX" ve "\\n" gibi kaçışlar ham haliyle görünür.

    Heuristik:
    - Metin başta/sonda çift tırnak içeriyorsa VE
    - İçinde '\\\\u' veya '\\\\n' gibi tipik JSON escape dizileri varsa
    -> `json.loads` ile decode etmeyi dene.

    Başarısız olursa orijinal metni döndürür.
    """
    if not isinstance(text, str) or not text:
        return text

    stripped = text.strip()
    if len(stripped) < 2:
        return text

    looks_quoted = stripped[0] == '"' and stripped[-1] == '"'
    looks_escaped = ("\\u" in stripped) or ("\\n" in stripped) or ("\\t" in stripped) or ("\\r" in stripped)

    if not (looks_quoted and looks_escaped):
        return text

    try:
        decoded = json.loads(stripped)
    except Exception:
        return text

    if not isinstance(decoded, str):
        return text

    # Bazı durumlarda çift-escape olur:
    # json.loads dış tırnakları kaldırır ama içeride hâlâ "\\u2705" gibi diziler kalır.
    if ("\\u" in decoded) or ("\\n" in decoded) or ("\\t" in decoded) or ("\\r" in decoded):
        try:
            return _decode_backslash_escapes(decoded)
        except Exception:
            return decoded

    return decoded


def _parse_mode_str(parse_mode: Any) -> str | None:
    """
    PTB parse_mode bazen string ("Markdown") bazen enum benzeri değerler olabilir.
    Burada sade bir string'e normalize ediyoruz.
    """
    if parse_mode is None:
        return None
    if isinstance(parse_mode, str):
        return parse_mode
    try:
        return str(parse_mode)
    except Exception:
        return None


def escape_md(text: str, *, version: int = 1) -> str:
    """
    Telegram Markdown için güvenli escape.

    Not: Bu fonksiyon dinamik alanlar (ders adı, hoca adı, uyarı metni vb.) için kullanılmalı.
    Sabit UI biçimlendirmeleri (**bold**, _italic_) bu fonksiyonun dışında tutulmalıdır.
    """
    if not isinstance(text, str) or not text:
        return text

    try:
        from telegram.helpers import escape_markdown
    except Exception:
        return text

    try:
        return escape_markdown(text, version=version)
    except Exception:
        return text


def normalize_outgoing_text(text: str, *, parse_mode: Any = None) -> str:
    """
    Outgoing metni normalize et:
    - Yanlışlıkla json.dumps ile escape edilmiş string'i geri al
    """
    if not isinstance(text, str) or not text:
        return text

    # Burada bilinçli Markdown biçimlendirmelerini (örn: **bold**) bozmayacak şekilde
    # SADECE yanlışlıkla JSON-escape edilmiş metni düzeltiyoruz.
    # Markdown escape işlemi, sadece dinamik alanlara, ilgili formatter/template içinde uygulanmalı.
    _ = parse_mode  # gelecekte gerekirse kullanılabilir
    return maybe_unescape_json_string(text)


def escape_dynamic_text(text: str, *, parse_mode: Any = "Markdown") -> str:
    """
    Dinamik (kullanıcı/LLM/DB kaynaklı) metni Telegram parse_mode'a göre escape et.
    """
    pm = _parse_mode_str(parse_mode) or "Markdown"
    if pm in ("MarkdownV2", "MARKDOWN_V2", "MARKDOWNV2"):
        return escape_md(text, version=2)
    return escape_md(text, version=1)

