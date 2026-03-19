from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import Course
from app.repos.base import BaseRepository


class CourseRepository(BaseRepository):
    async def list_all_active(self) -> list[Course]:
        result = await self.session.execute(select(Course).where(Course.is_active.is_(True)))
        return list(result.scalars().all())

    async def list_for_user(self, user_id: int) -> list[Course]:
        result = await self.session.execute(select(Course).where(Course.user_id == user_id))
        return list(result.scalars().all())

    async def list_active_for_user(self, user_id: int) -> list[Course]:
        result = await self.session.execute(
            select(Course).where(Course.user_id == user_id, Course.is_active.is_(True))
        )
        return list(result.scalars().all())

    async def create_many(self, user_id: int, rows: list[dict[str, str | None]]) -> list[Course]:
        courses = [
            Course(
                user_id=user_id,
                name=str(row["name"]),
                start_day_of_week_utc=str(row["start_day_of_week_utc"]),
                end_day_of_week_utc=str(row["end_day_of_week_utc"]),
                start_time_utc=str(row["start_time_utc"]),
                end_time_utc=str(row["end_time_utc"]),
                teams_link=row.get("teams_link"),
                created_at=datetime.now(UTC),
            )
            for row in rows
        ]
        self.session.add_all(courses)
        await self.session.flush()
        return courses
