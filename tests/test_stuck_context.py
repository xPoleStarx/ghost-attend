"""stuck_subgoal HITL özet metni."""

from types import SimpleNamespace

from app.adapters.browser_use_runner import _hitl_question, _stuck_context_note


def test_stuck_context_note_turkish():
    out = _stuck_context_note(
        SimpleNamespace(
            current_state=SimpleNamespace(
                evaluation_previous_goal="Başarısız",
                memory="Popüler filtresi denendi.",
                next_goal="Tekrar dene",
            )
        ),
        "tr",
    )
    assert "Son değerlendirme" in out
    assert "Hafıza" in out
    assert "Tekrarlanan hedef" in out


def test_hitl_question_stuck_subgoal_turkish():
    q = _hitl_question(
        "https://youtube.com/x",
        "Y",
        "stuck_subgoal",
        agent_context="Özet satırı",
        reply_lang="tr",
    )
    assert "tekrar" in q.lower() or "Tekrar" in q
    assert "Özet" in q
