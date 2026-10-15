"""Đối soát hoàn tiền thủ công và hạn tự hủy đơn tại quầy chưa thanh toán

- bookings.refund_reference: mã giao dịch ngân hàng của lần chuyển hoàn (bắt buộc khi xác nhận hoàn tiền từ nay);
  một mã chỉ dùng cho một đơn (unique index một phần, bỏ qua NULL).
- bookings.refund_proof_file: tên tệp chứng từ chuyển khoản (ảnh hoặc PDF) lưu trong thư mục riêng, không công khai.
- venues.unpaid_desk_release_minutes: đơn tại quầy chưa thu đồng nào tự hủy khi còn bấy nhiêu phút tới giờ chơi
  (mặc định 30, 0 = không tự hủy).
- bookings.auto_release_at: hạn tự hủy của từng đơn tại quầy chưa thu, tính khi tạo đơn. Đơn tạo trước bản này giữ
  NULL (không tự hủy), để không đơn cũ nào bị hủy bất ngờ ngay sau khi nâng cấp.

Chỉ thêm cột; dữ liệu đang có không bị thay đổi. Các lần hoàn tiền đã xác nhận trước đây giữ refund_reference = NULL.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-15 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('bookings', sa.Column('auto_release_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('bookings', sa.Column('refund_reference', sa.String(length=64), nullable=True))
    op.add_column('bookings', sa.Column('refund_proof_file', sa.String(length=255), nullable=True))
    op.create_index(
        'uq_bookings_refund_reference', 'bookings', ['refund_reference'], unique=True,
        postgresql_where=sa.text('refund_reference IS NOT NULL'),
        sqlite_where=sa.text('refund_reference IS NOT NULL'),
    )
    op.add_column(
        'venues',
        sa.Column('unpaid_desk_release_minutes', sa.Integer(), server_default=sa.text('30'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('venues', 'unpaid_desk_release_minutes')
    op.drop_index('uq_bookings_refund_reference', table_name='bookings')
    op.drop_column('bookings', 'refund_proof_file')
    op.drop_column('bookings', 'refund_reference')
    op.drop_column('bookings', 'auto_release_at')
