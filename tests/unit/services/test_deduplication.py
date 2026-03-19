from datetime import UTC, datetime, timedelta

from app.services.deduplication import CommandDeduplicator


def test_deduplicator_detects_recent_duplicate() -> None:
    current = datetime(2026, 3, 19, 12, 0, tzinfo=UTC)
    deduplicator = CommandDeduplicator(window=timedelta(seconds=30), now=lambda: current)

    assert deduplicator.seen_recently(1, "/start") is False
    assert deduplicator.seen_recently(1, "/start") is True
