"""Bảng shift_closings: sổ kết ca tại quầy của từng cụm sân

Mỗi dòng là một lần kết ca: tiền vốn đầu ca, tiền mặt đếm được và các khoản thu, hoàn mà sổ giao dịch đã ghi
trong ca. Đây là bảng mới; dữ liệu đang có không bị thay đổi.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-13 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'shift_closings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venue_id', sa.Integer(), nullable=False),
        sa.Column('business_date', sa.Date(), nullable=False),
        sa.Column('closed_by_id', sa.Integer(), nullable=False),
        sa.Column('closed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('opening_float', sa.Float(), nullable=False),
        sa.Column('counted_cash', sa.Float(), nullable=False),
        sa.Column('cash_collected', sa.Float(), nullable=False),
        sa.Column('transfer_collected', sa.Float(), nullable=False),
        sa.Column('refunded', sa.Float(), server_default='0', nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['closed_by_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['venue_id'], ['venues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_shift_closings_id'), 'shift_closings', ['id'], unique=False)
    op.create_index('ix_shift_closings_venue_date', 'shift_closings', ['venue_id', 'business_date'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_shift_closings_venue_date', table_name='shift_closings')
    op.drop_index(op.f('ix_shift_closings_id'), table_name='shift_closings')
    op.drop_table('shift_closings')
