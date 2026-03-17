"""
GhostAttend — Course Repository

Ders CRUD işlemleri.
"""

import uuid
from datetime import time

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.db.models import Course


class CourseRepository:
    """Course tablosu üzerinde CRUD operasyonları."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, course_id: uuid.UUID) -> Course | None:
        """ID ile ders bul."""
        result = await self.session.execute(
            select(Course).where(Course.id == course_id)
        )
        return result.scalar_one_or_none()

    async def get_user_courses(self, user_id: int, active_only: bool = True) -> list[Course]:
        """Kullanıcının derslerini listele."""
        query = select(Course).where(Course.user_id == user_id)
        if active_only:
            query = query.where(Course.is_active.is_(True))
        query = query.order_by(Course.day_of_week, Course.start_time)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        name: str,
        day_of_week: int,
        start_time: time,
        end_time: time,
        instructor: str | None = None,
        platform: str = "teams",
        direct_url: str | None = None,
        dys_search_hint: str | None = None,
        semester: str | None = None,
    ) -> Course:
        """Yeni ders oluştur."""
        course = Course(
            user_id=user_id,
            name=name,
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            instructor=instructor,
            platform=platform,
            direct_url=direct_url,
            dys_search_hint=dys_search_hint,
            semester=semester,
        )
        self.session.add(course)
        await self.session.flush()
        return course

    async def bulk_create_from_parsed(
        self,
        user_id: int,
        parsed_courses: list[dict],
    ) -> list[Course]:
        """Vision LLM'den parse edilen dersleri topluca kaydet."""
        from src.core.constants import DAYS_TR

        rows: list[dict] = []
        keys: list[tuple] = []

        for pc in parsed_courses:
            name = pc["ders_adi"]
            day_of_week = DAYS_TR.get(pc["gun"], 0)
            start_time = time.fromisoformat(pc["baslangic_saati"])
            end_time = time.fromisoformat(pc["bitis_saati"])

            rows.append(
                {
                    "user_id": user_id,
                    "name": name,
                    "day_of_week": day_of_week,
                    "start_time": start_time,
                    "end_time": end_time,
                    "instructor": pc.get("ogretim_uyesi"),
                    "platform": pc.get("platform", "unknown"),
                    "is_online": pc.get("online_mi"),
                    "is_active": True,
                }
            )
            keys.append((name, day_of_week, start_time, end_time))

        if not rows:
            return []

        # Aynı ders tekrar kaydolmasın: unique constraint üstünden upsert.
        stmt = insert(Course).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_course_user_time",
            set_={
                "instructor": stmt.excluded.instructor,
                "platform": stmt.excluded.platform,
                "is_online": stmt.excluded.is_online,
                "is_active": True,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()

        # Geri dönüş (mevcut kod uyumluluğu): ilgili dersleri DB'den çek.
        result = await self.session.execute(
            select(Course).where(
                Course.user_id == user_id,
                tuple_(Course.name, Course.day_of_week, Course.start_time, Course.end_time).in_(keys),
            )
        )
        return list(result.scalars().all())

    async def set_active(self, course_id: uuid.UUID, is_active: bool) -> None:
        """Dersi aktif/pasif yap."""
        await self.session.execute(
            update(Course)
            .where(Course.id == course_id)
            .values(is_active=is_active)
        )

    async def update_direct_url(self, course_id: uuid.UUID, url: str) -> None:
        """Derse direkt Teams/Zoom linki ekle."""
        await self.session.execute(
            update(Course)
            .where(Course.id == course_id)
            .values(direct_url=url)
        )

    async def get_courses_for_day(self, user_id: int, day_of_week: int) -> list[Course]:
        """Belirli bir gün için aktif dersleri getir."""
        result = await self.session.execute(
            select(Course)
            .where(
                Course.user_id == user_id,
                Course.day_of_week == day_of_week,
                Course.is_active.is_(True),
            )
            .order_by(Course.start_time)
        )
        return list(result.scalars().all())

    async def delete(self, course_id: uuid.UUID) -> None:
        """Dersi sil."""
        course = await self.get_by_id(course_id)
        if course:
            await self.session.delete(course)
