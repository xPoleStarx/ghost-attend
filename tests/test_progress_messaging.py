"""Kullanıcıya giden progress metni yardımcıları (browser_use_runner)."""

from types import SimpleNamespace

from app.adapters.browser_use_runner import (
    _compose_agent_progress_message,
    _sanitize_agent_progress_field,
    _sanitize_next_goal_line,
    _user_task_preview_from_instruction,
)


def test_preview_strips_reply_lang():
    raw = "[reply-lang:tr]\n\nhttps://example.com aç ve başlığı söyle"
    p = _user_task_preview_from_instruction(raw)
    assert "[reply-lang" not in p.lower()
    assert "example.com" in p


def test_preview_collapses_whitespace():
    assert _user_task_preview_from_instruction("  a  \n  b  ") == "a b"


def test_sanitize_strips_verdict_prefixes():
    s = "Verdict: Success. Memory: foo Next goal: Click the button"
    out = _sanitize_next_goal_line(s)
    assert "Verdict" not in out[:20]
    assert len(out) <= 131


def test_sanitize_truncates_long():
    long = "x" * 200
    out = _sanitize_next_goal_line(long)
    assert out.endswith("…")
    assert len(out) <= 131


def test_sanitize_agent_progress_field_truncates():
    s = "a" * 400
    out = _sanitize_agent_progress_field(s, 50)
    assert out.endswith("…")
    assert len(out) == 50


def test_compose_progress_memory_and_goal():
    st = SimpleNamespace(
        current_state=SimpleNamespace(
            memory="Hepsiburada ana sayfadayım.",
            next_goal="GTA 5 için arama kutusunu kullanacağım.",
        )
    )
    msg = _compose_agent_progress_message(st)
    assert "Hepsiburada" in msg
    assert "GTA 5" in msg
    assert " — " in msg


def test_compose_progress_dedupes_redundant_goal():
    st = SimpleNamespace(
        current_state=SimpleNamespace(
            memory="Arama yaptım ve sonuçlar yüklendi.",
            next_goal="Arama yaptım ve sonuçlar yüklendi.",
        )
    )
    msg = _compose_agent_progress_message(st)
    assert msg == "Arama yaptım ve sonuçlar yüklendi."


def test_compose_progress_none_when_empty():
    assert _compose_agent_progress_message(None) is None
    assert _compose_agent_progress_message(SimpleNamespace(current_state=None)) is None
    assert (
        _compose_agent_progress_message(
            SimpleNamespace(current_state=SimpleNamespace(memory="", next_goal=""))
        )
        is None
    )
