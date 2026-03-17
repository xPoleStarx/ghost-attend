from __future__ import annotations

from src.bot.utils.safe_text import escape_md, escape_dynamic_text, maybe_unescape_json_string


def test_maybe_unescape_json_string_decodes_json_dumped_string() -> None:
    # json.dumps("✅ ...\n\n...") benzeri tek katmanlı escape
    raw = "\"\\u2705 Bilgiler kaydedildi!\\n\\nTamamlanınca *bitti* yaz.\""
    out = maybe_unescape_json_string(raw)
    assert out == "✅ Bilgiler kaydedildi!\n\nTamamlanınca *bitti* yaz."


def test_maybe_unescape_json_string_decodes_double_escaped_json_string() -> None:
    # Çift katmanlı escape: json.dumps("\\u2705 ...\\n") çıktısı
    raw = "\"\\\\u2705 Bilgiler kaydedildi!\\\\n\\\\nTamamlanınca *bitti* yaz.\""
    out = maybe_unescape_json_string(raw)
    assert out == "✅ Bilgiler kaydedildi!\n\nTamamlanınca *bitti* yaz."


def test_maybe_unescape_json_string_leaves_normal_text_untouched() -> None:
    raw = "✅ Bilgiler kaydedildi!\n\nTamamlanınca *bitti* yaz."
    out = maybe_unescape_json_string(raw)
    assert out == raw


def test_escape_md_escapes_markdown_v1_special_chars() -> None:
    raw = "A_B [link](x) `code` *star* _it_"
    out = escape_md(raw, version=1)
    # PTB escape_markdown v1: _ * ` [ karakterlerini kaçışlar
    assert "A\\_B" in out
    assert "\\[" in out
    assert "\\`" in out
    assert "\\*" in out


def test_escape_dynamic_text_defaults_to_markdown_v1() -> None:
    raw = "A_B"
    out = escape_dynamic_text(raw)
    assert out == "A\\_B"

