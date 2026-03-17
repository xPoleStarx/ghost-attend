"""initial

Revision ID: 0001
Revises: 
Create Date: 2024-03-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users tablosu
    op.create_table('users',
        sa.Column('id', sa.BigInteger(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=True),
        sa.Column('first_name', sa.String(length=128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('onboarding_step', sa.String(length=32), nullable=False),
        sa.Column('timezone', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. credentials tablosu
    op.create_table('credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('type', sa.String(length=16), nullable=False),
        sa.Column('dys_url', sa.Text(), nullable=True),
        sa.Column('email_enc', sa.LargeBinary(), nullable=False),
        sa.Column('password_enc', sa.LargeBinary(), nullable=False),
        sa.Column('cookie_enc', sa.LargeBinary(), nullable=True),
        sa.Column('cookie_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_verified', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('uq_user_type', 'credentials', ['user_id', 'type'], unique=True)

    # 3. courses tablosu
    op.create_table('courses',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('name', sa.String(length=256), nullable=False),
        sa.Column('instructor', sa.String(length=256), nullable=True),
        sa.Column('platform', sa.String(length=32), nullable=False),
        sa.Column('day_of_week', sa.SmallInteger(), nullable=False),
        sa.Column('start_time', sa.Time(), nullable=False),
        sa.Column('end_time', sa.Time(), nullable=False),
        sa.Column('direct_url', sa.Text(), nullable=True),
        sa.Column('dys_search_hint', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('semester', sa.String(length=32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_courses_user_active', 'courses', ['user_id', 'is_active'], unique=False)

    # 4. agent_sessions tablosu
    op.create_table('agent_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('course_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.SmallInteger(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['course_id'], ['courses.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_sessions_created', 'agent_sessions', ['created_at'], unique=False)
    op.create_index('idx_sessions_user_status', 'agent_sessions', ['user_id', 'status'], unique=False)

    # 5. session_checkpoints tablosu
    op.create_table('session_checkpoints',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('checkpoint_name', sa.String(length=64), nullable=False),
        sa.Column('screenshot_path', sa.Text(), nullable=True),
        sa.Column('telegram_file_id', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 6. notifications tablosu
    op.create_table('notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(length=32), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['agent_sessions.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('notifications')
    op.drop_table('session_checkpoints')
    op.drop_table('agent_sessions')
    op.drop_table('courses')
    op.drop_table('credentials')
    op.drop_table('users')
