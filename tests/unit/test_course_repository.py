from datetime import time

from src.db.repositories.course import _coerce_end_time


def test_coerce_end_time_parses_explicit_value():
    assert _coerce_end_time("20:15", time(18, 50)) == time(20, 15)


def test_coerce_end_time_defaults_missing_value_to_one_hour_after_start():
    assert _coerce_end_time(None, time(18, 50)) == time(19, 50)


def test_coerce_end_time_clamps_missing_value_before_midnight():
    assert _coerce_end_time(None, time(23, 30)) == time(23, 59)
