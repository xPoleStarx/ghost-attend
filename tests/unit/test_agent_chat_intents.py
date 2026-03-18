from datetime import time

from src.bot.handlers.agent_chat import (
    _compute_next_lesson,
    _detect_intent,
    _extract_manual_join_course_query,
    _is_generic_manual_join_query,
    _pick_manual_join_target,
)


class DummyCourse:
    def __init__(self, name: str, day_of_week: int, start_h: int, start_m: int):
        self.name = name
        self.day_of_week = day_of_week
        self.start_time = time(start_h, start_m)
        self.end_time = time(start_h + 1, start_m)


def test_detect_intent_join_variants():
    assert _detect_intent("derse gir") == "ask_join_or_status"
    assert _detect_intent("Derse girecek misin") == "ask_join_or_status"
    assert _detect_intent("derse katılacak mısın") == "ask_join_or_status"
    assert _detect_intent("şimdi derse gir") == "manual_join_request"


def test_detect_intent_manual_join_request():
    assert _detect_intent("sürdürülebilirlik dersine şimdi gir") == "manual_join_request"
    assert _detect_intent("Kariyer Planlama dersine katıl") == "manual_join_request"
    assert _detect_intent("Kariyer Planlama dersine hemen gir") == "manual_join_request"
    assert _detect_intent("derse şimdi gir") == "manual_join_request"
    assert _detect_intent("derse katılım şimdi") == "manual_join_request"
    assert _detect_intent("hadi derse gir") == "manual_join_request"


def test_detect_intent_ambiguous_schedule_change():
    assert _detect_intent("ders saatini güncelle 23.30 olarak başlangıç") == "ambiguous_schedule_change"


def test_detect_intent_none_for_clear_text():
    assert _detect_intent("Kariyer Planlama dersini salı 23:30 yap") is None


def test_extract_manual_join_course_query():
    assert _extract_manual_join_course_query("kariyer planlama dersine katıl") == "kariyer planlama"
    assert _extract_manual_join_course_query('"Kariyer Planlama" dersine şimdi gir') == "kariyer planlama"


def test_generic_manual_join_query_detection():
    assert _is_generic_manual_join_query(_extract_manual_join_course_query("derse katılım şimdi")) is True
    assert _is_generic_manual_join_query(_extract_manual_join_course_query("Kariyer Planlama dersine katıl")) is False


def test_pick_manual_join_target_prefers_best_match():
    class Course:
        def __init__(self, course_id: str, name: str):
            self.id = course_id
            self.name = name
            self.is_active = True

    exact = Course("1", "Kariyer Planlama")
    weak = Course("2", "Kariyer Gelişimi")

    target, plausible = _pick_manual_join_target("kariyer planlama", [weak, exact])

    assert target is exact
    assert exact in plausible


def test_compute_next_lesson_picks_closest():
    courses = [
        DummyCourse("Ders A", 0, 9, 0),
        DummyCourse("Ders B", 0, 15, 0),
    ]

    next_course = _compute_next_lesson(courses)
    assert next_course in courses


def test_policy_marks_followup_schedule_update_from_memory():
    from src.conversation.policy import decide_policy

    decision = decide_policy(
        message_text="hayır ders saati 18.12",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={"last_schedule_intent": "course_update", "last_referenced_course_name": "Kariyer Planlama"},
    )

    assert decision.tool_name == "courses.update"
    assert decision.tool_args["start_time"] == "18:12"


def test_policy_marks_same_course_day_followup_from_memory():
    from src.conversation.policy import decide_policy

    decision = decide_policy(
        message_text="onu çarşambaya al",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={"last_schedule_intent": "course_update", "last_referenced_course_name": "Kariyer Planlama"},
    )

    assert decision.tool_name == "courses.update"
    assert decision.tool_args["day"] == "Çarşamba"


def test_policy_keeps_batch_schedule_update_for_program_text():
    from src.conversation.policy import decide_policy

    decision = decide_policy(
        message_text="yeni programi guncelle",
        courses=[{"name": "Kariyer Planlama"}],
        attachments=[],
        conversation_state={},
    )

    assert decision.tool_name == "schedule.patch_from_text"
