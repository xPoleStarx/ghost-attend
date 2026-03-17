from __future__ import annotations

from src.bot.utils.safe_text import maybe_unescape_json_string


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

