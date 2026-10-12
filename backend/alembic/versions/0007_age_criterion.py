"""Thêm chênh lệch tuổi vào mô hình ghép cặp: mô hình có 5 đặc trưng

Phiếu ghép cặp mô phỏng (source = 'simulated') được sinh từ quy tắc cũ chưa tính tuổi nên bị xóa; nạp lại bộ mới
bằng `python manage.py seed --feedback`. Câu trả lời khảo sát thật (source = 'survey') được giữ nguyên; các câu thu
trước thay đổi này không có chênh lệch tuổi (NULL) nên không tham gia huấn luyện.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-12 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DELETE FROM pair_feedback WHERE source = 'simulated'")
    op.add_column('pair_feedback', sa.Column('age_diff', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('pair_feedback', 'age_diff')
