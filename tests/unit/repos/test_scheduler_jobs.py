from dataclasses import dataclass

import pytest

from app.repos.scheduler_jobs import SchedulerJobRepository


@dataclass
class FakeRow:
    user_id: int
    course_id: int
    job_type: str
    apscheduler_job_id: str
    is_active: bool = True


class FakeScalarResult:
    def __init__(self, row: FakeRow | None) -> None:
        self.row = row

    def scalar_one_or_none(self) -> FakeRow | None:
        return self.row

    def all(self) -> list[FakeRow]:
        return [] if self.row is None else [self.row]


class FakeSession:
    def __init__(self) -> None:
        self.row: FakeRow | None = None
        self.added: list[object] = []
        self.flush_calls = 0

    async def execute(self, _query: object) -> FakeScalarResult:
        return FakeScalarResult(self.row)

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        self.flush_calls += 1


@pytest.mark.asyncio
async def test_scheduler_job_repository_reactivates_existing_job() -> None:
    session = FakeSession()
    session.row = FakeRow(user_id=1, course_id=10, job_type="T_MINUS_1", apscheduler_job_id="job-1", is_active=False)
    repo = SchedulerJobRepository(session)  # type: ignore[arg-type]

    row = await repo.create_or_reactivate(
        user_id=1,
        course_id=10,
        job_type="T_MINUS_3",
        apscheduler_job_id="job-1",
    )

    assert row.is_active is True
    assert row.job_type == "T_MINUS_3"
    assert session.flush_calls == 1
