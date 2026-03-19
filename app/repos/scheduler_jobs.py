from sqlalchemy import select

from app.db.models import SchedulerJob
from app.repos.base import BaseRepository


class SchedulerJobRepository(BaseRepository):
    async def get_by_apscheduler_job_id(self, apscheduler_job_id: str) -> SchedulerJob | None:
        result = await self.session.execute(
            select(SchedulerJob).where(SchedulerJob.apscheduler_job_id == apscheduler_job_id)
        )
        return result.scalar_one_or_none()

    async def create_or_reactivate(
        self,
        *,
        user_id: int,
        course_id: int,
        job_type: str,
        apscheduler_job_id: str,
    ) -> SchedulerJob:
        existing = await self.get_by_apscheduler_job_id(apscheduler_job_id)
        if existing is not None:
            existing.is_active = True
            existing.job_type = job_type
            existing.user_id = user_id
            existing.course_id = course_id
            await self.session.flush()
            return existing
        row = SchedulerJob(
            user_id=user_id,
            course_id=course_id,
            job_type=job_type,
            apscheduler_job_id=apscheduler_job_id,
            is_active=True,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def deactivate_by_course(self, course_id: int) -> None:
        result = await self.session.execute(select(SchedulerJob).where(SchedulerJob.course_id == course_id))
        for row in result.scalars().all():
            row.is_active = False
        await self.session.flush()
