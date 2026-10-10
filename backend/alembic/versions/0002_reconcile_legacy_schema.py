"""reconcile legacy schema

CSDL cũ được tạo bằng create_all + các lệnh ALTER thủ công nên lệch so với model
(thiếu index, ràng buộc unique trùng lặp, users.is_active cho phép NULL).
Migration này đưa CSDL cũ về đúng trạng thái baseline; trên CSDL mới nó không làm gì.

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # booking_code / transaction_code: thay ràng buộc unique + index thường bằng một unique index
    op.execute("ALTER TABLE bookings DROP CONSTRAINT IF EXISTS bookings_booking_code_key")
    op.execute("DROP INDEX IF EXISTS ix_bookings_booking_code")
    op.execute("CREATE UNIQUE INDEX ix_bookings_booking_code ON bookings (booking_code)")
    op.execute(
        "ALTER TABLE payment_transactions DROP CONSTRAINT IF EXISTS payment_transactions_transaction_code_key"
    )
    op.execute("DROP INDEX IF EXISTS ix_payment_transactions_transaction_code")
    op.execute(
        "CREATE UNIQUE INDEX ix_payment_transactions_transaction_code ON payment_transactions (transaction_code)"
    )

    # Các index model đã khai báo nhưng CSDL cũ chưa có
    op.execute("CREATE INDEX IF NOT EXISTS ix_bookings_refund_status ON bookings (refund_status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_matches_court_id ON matches (court_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_matches_creator_id ON matches (creator_id)")

    # users.is_active bắt buộc có giá trị
    op.execute("UPDATE users SET is_active = TRUE WHERE is_active IS NULL")
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET NOT NULL")
    op.execute("ALTER TABLE users ALTER COLUMN is_active DROP DEFAULT")


def downgrade() -> None:
    # Không khôi phục lại các sai lệch của CSDL cũ.
    pass
