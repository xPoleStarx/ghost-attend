"""Add is_online column to courses table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('courses', sa.Column('is_online', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('courses', 'is_online')
