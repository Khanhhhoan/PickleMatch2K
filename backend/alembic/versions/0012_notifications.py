"""Bảng notifications: thông báo trong ứng dụng (ví dụ phòng đấu bị hủy), lưu lại cho người dùng offline

Bảng mới; dữ liệu đang có không bị thay đổi.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-16 00:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('body', sa.String(length=500), nullable=False),
        sa.Column('link', sa.String(length=255), nullable=True),
        sa.Column('event_key', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'event_key', name='uq_notifications_user_event'),
    )
    op.create_index(op.f('ix_notifications_id'), 'notifications', ['id'], unique=False)
    op.create_index('ix_notifications_user_created', 'notifications', ['user_id', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notifications_user_created', table_name='notifications')
    op.drop_index(op.f('ix_notifications_id'), table_name='notifications')
    op.drop_table('notifications')
