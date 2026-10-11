"""Bỏ giờ rảnh khỏi hồ sơ và khỏi mô hình ghép cặp: mô hình còn 4 đặc trưng

Phiếu ghép cặp mô phỏng (source = 'simulated') được sinh từ quy tắc cũ có tính giờ rảnh nên bị xóa; nạp lại bộ mới
bằng `python manage.py seed --feedback`. Câu trả lời khảo sát thật (source = 'survey') được giữ nguyên, chỉ mất cột
không còn dùng.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12 10:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM pair_feedback WHERE source = 'simulated'")
    op.drop_column('pair_feedback', 'availability_overlap')
    op.drop_column('player_profiles', 'availability')


def downgrade() -> None:
    # Giá trị cũ không khôi phục được: cột được tạo lại, các dòng đang có nhận độ trùng lịch 0 / chưa khai khung rảnh.
    op.add_column('player_profiles', sa.Column('availability', sa.String(), nullable=True))
    op.add_column('pair_feedback', sa.Column('availability_overlap', sa.Float(), server_default='0', nullable=False))
    op.alter_column('pair_feedback', 'availability_overlap', server_default=None)
