"""Bỏ tiện ích ưa thích và ngân sách khỏi hồ sơ người chơi

Hai cột này chỉ là giá trị mặc định cho thuật toán gợi ý sân ở backend và giao diện không còn nhập chúng.
Thuật toán vẫn nhận ngân sách và tiện ích qua tham số của yêu cầu.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12 10:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('player_profiles', 'budget_max')
    op.drop_column('player_profiles', 'preferred_amenities')


def downgrade() -> None:
    op.add_column('player_profiles', sa.Column('preferred_amenities', sa.String(), nullable=True))
    op.add_column('player_profiles', sa.Column('budget_max', sa.Float(), nullable=True))
