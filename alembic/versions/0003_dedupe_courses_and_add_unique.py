"""Dedupe courses and add uniqueness constraint

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-17 19:35:00.000000
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Mevcut duplicate kayıtları temizle (constraint eklenebilmesi için)
    # Aynı kullanıcı + ders adı + gün + başlangıç + bitiş kombinasyonunda ilk kaydı tut.
    op.execute(
        """
        DELETE FROM courses
        WHERE id IN (
          SELECT id FROM (
            SELECT
              id,
              ROW_NUMBER() OVER (
                PARTITION BY user_id, name, day_of_week, start_time, end_time
                ORDER BY created_at ASC
              ) AS rn
            FROM courses
          ) t
          WHERE t.rn > 1
        );
        """
    )

    # 2) Unique constraint ekle (tekrar insert olmasın)
    op.create_unique_constraint(
        "uq_course_user_time",
        "courses",
        ["user_id", "name", "day_of_week", "start_time", "end_time"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_course_user_time", "courses", type_="unique")

