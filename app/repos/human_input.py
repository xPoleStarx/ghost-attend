from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.models import HumanInputRequest
from app.domain.enums import HumanInputStatus
from app.repos.base import BaseRepository


class HumanInputRepository(BaseRepository):
    async def create(
        self,
        *,
        session_id: UUID,
        user_id: int,
        tool_name: str,
        reason: str,
        prompt: str,
        timeout_seconds: int,
        screenshot_path: str | None = None,
    ) -> HumanInputRequest:
        request = HumanInputRequest(
            session_id=session_id,
            user_id=user_id,
            tool_name=tool_name,
            reason=reason,
            prompt=prompt,
            screenshot_path=screenshot_path,
            status=HumanInputStatus.PENDING.value,
            expires_at=datetime.now(UTC) + timedelta(seconds=timeout_seconds),
            created_at=datetime.now(UTC),
        )
        self.session.add(request)
        await self.session.flush()
        return request

    async def get_pending_for_session(self, session_id: UUID) -> HumanInputRequest | None:
        result = await self.session.execute(
            select(HumanInputRequest).where(
                HumanInputRequest.session_id == session_id,
                HumanInputRequest.status == HumanInputStatus.PENDING.value,
            )
        )
        return result.scalar_one_or_none()

    async def resolve(self, request: HumanInputRequest) -> HumanInputRequest:
        request.status = HumanInputStatus.RESOLVED.value
        await self.session.flush()
        return request
