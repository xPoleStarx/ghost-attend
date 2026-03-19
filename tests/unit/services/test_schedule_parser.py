from app.services.schedule_parser import ScheduleParser


def test_schedule_parser_parses_pipe_delimited_text(schedule_parser: ScheduleParser) -> None:
    raw = "Kariyer Planlama | monday | 14:00 | 15:00 | https://example.com"

    parsed = schedule_parser.parse_text(raw)

    assert len(parsed.courses) == 1
    assert parsed.courses[0].day_of_week == "MONDAY"
    assert parsed.needs_confirmation is True
    assert parsed.confidence > 0.8


def test_schedule_parser_collects_warnings(schedule_parser: ScheduleParser) -> None:
    parsed = schedule_parser.parse_text("bad line")

    assert parsed.courses == []
    assert parsed.warnings == ["Could not parse line: bad line"]


def test_schedule_parser_parses_natural_turkish_sentence(schedule_parser: ScheduleParser) -> None:
    parsed = schedule_parser.parse_text(
        "kariyer planlama, her çarşamba, 19.30da başlıyor 20.00da bitiyor"
    )

    assert len(parsed.courses) == 1
    assert parsed.courses[0].name == "kariyer planlama"
    assert parsed.courses[0].day_of_week == "WEDNESDAY"
    assert parsed.courses[0].start_local == "19:30"
    assert parsed.courses[0].end_local == "20:00"
