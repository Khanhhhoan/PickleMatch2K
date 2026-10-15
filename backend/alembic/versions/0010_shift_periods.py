"""Kết ca không còn gắn với ngày lịch: mỗi giao dịch thuộc đúng một lần kết ca

- payment_transactions.shift_closing_id: lần kết ca đã tính khoản này (NULL = chưa kết ca).
- shift_closings.period_start: ca kéo dài từ đây (lần kết ca trước của cụm sân) tới closed_at, kể cả qua nửa đêm.

Dữ liệu có sẵn: các lần kết ca cũ được gắn đúng những giao dịch mà cách tính cũ (theo ngày) đã cộng vào chúng - giao
dịch cùng cụm sân, cùng ngày (giờ Việt Nam), ghi trước lúc kết ca và chưa thuộc lần kết ca sớm hơn. Số tiền đã lưu của
từng lần kết ca không đổi. Không xóa hay sửa dòng nào khác.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-15 23:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VN_TZ = "Asia/Ho_Chi_Minh"


def upgrade() -> None:
    op.add_column('shift_closings', sa.Column('period_start', sa.DateTime(timezone=True), nullable=True))
    op.add_column('payment_transactions', sa.Column('shift_closing_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_payment_transactions_shift_closing_id'), 'payment_transactions', ['shift_closing_id'])
    op.create_foreign_key(
        'fk_payment_transactions_shift_closing_id', 'payment_transactions', 'shift_closings',
        ['shift_closing_id'], ['id'], ondelete='SET NULL',
    )

    if op.get_bind().dialect.name != 'postgresql':
        return  # SQLite chỉ dùng thử, không có dữ liệu cũ cần gắn

    # Ca của các lần kết ca cũ: từ lần kết ca trước cùng ngày, hoặc từ 0 giờ của ngày đó
    op.execute(f"""
        UPDATE shift_closings AS c
        SET period_start = COALESCE(
            (SELECT max(p.closed_at) FROM shift_closings p
              WHERE p.venue_id = c.venue_id AND p.business_date = c.business_date AND p.closed_at < c.closed_at),
            (c.business_date::timestamp AT TIME ZONE '{VN_TZ}')
        )
    """)
    # Mỗi giao dịch thành công thuộc lần kết ca sớm nhất cùng cụm sân, cùng ngày, kết sau lúc ghi giao dịch
    op.execute(f"""
        UPDATE payment_transactions AS t
        SET shift_closing_id = pick.closing_id
        FROM (
            SELECT tx.id AS tx_id,
                   (SELECT c.id FROM shift_closings c
                     WHERE c.venue_id = tx.venue_id
                       AND c.business_date = (tx.created_at AT TIME ZONE '{VN_TZ}')::date
                       AND c.closed_at > tx.created_at
                     ORDER BY c.closed_at, c.id
                     LIMIT 1) AS closing_id
            FROM (
                SELECT t2.id, t2.created_at,
                       (SELECT min(ct.venue_id) FROM booking_details d JOIN courts ct ON ct.id = d.court_id
                         WHERE d.booking_id = t2.booking_id) AS venue_id
                FROM payment_transactions t2
                WHERE t2.status = 'SUCCESS' AND t2.created_at IS NOT NULL
            ) AS tx
        ) AS pick
        WHERE t.id = pick.tx_id AND pick.closing_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_constraint('fk_payment_transactions_shift_closing_id', 'payment_transactions', type_='foreignkey')
    op.drop_index(op.f('ix_payment_transactions_shift_closing_id'), table_name='payment_transactions')
    op.drop_column('payment_transactions', 'shift_closing_id')
    op.drop_column('shift_closings', 'period_start')
