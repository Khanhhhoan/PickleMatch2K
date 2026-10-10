"""booking core and matching profile

- Đơn đặt sân: trạng thái PENDING/EXPIRED/CHECKED_IN/NO_SHOW, tiền cọc, số tiền đã trả,
  thông tin khách tại quầy (thay cho việc nhét vào refund_reason), người thực hiện check-in/hủy/hoàn.
- Chống đặt trùng ở mức CSDL: unique index một phần + ràng buộc loại trừ khoảng thời gian.
- Giao dịch: phương thức, loại, người ghi nhận; mã tham chiếu ngân hàng là duy nhất.
- Phòng đấu liên kết đơn đặt bằng khóa ngoại (thay cho tìm chuỗi trong notes).
- Hồ sơ người chơi: mục đích chơi, khung giờ rảnh, tiện ích ưa thích, ngân sách.
- Sequence cấp mã đơn / mã giao dịch không trùng khi chạy đồng thời.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REFERENCE_NOT_EMPTY = "reference_number IS NOT NULL AND reference_number <> ''"


def _abort_if_rows(sql: str, message: str) -> None:
    rows = op.get_bind().execute(sa.text(sql)).fetchall()
    if rows:
        raise RuntimeError(f"{message}: {[tuple(r) for r in rows]}")


def upgrade() -> None:
    # ------------------------------------------------------------------ columns
    op.add_column("bookings", sa.Column("source", sa.String(), server_default="ONLINE", nullable=False))
    op.add_column("bookings", sa.Column("guest_name", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("guest_phone", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("deposit_amount", sa.Float(), server_default=sa.text("0"), nullable=False))
    op.add_column("bookings", sa.Column("paid_amount", sa.Float(), server_default=sa.text("0"), nullable=False))
    op.add_column("bookings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("checked_in_by_id", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("cancelled_by_id", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("cancel_reason", sa.String(), nullable=True))
    op.add_column("bookings", sa.Column("refunded_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key("bookings_checked_in_by_id_fkey", "bookings", "users", ["checked_in_by_id"], ["id"])
    op.create_foreign_key("bookings_cancelled_by_id_fkey", "bookings", "users", ["cancelled_by_id"], ["id"])
    op.create_foreign_key("bookings_refunded_by_id_fkey", "bookings", "users", ["refunded_by_id"], ["id"])

    op.add_column("booking_details", sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False))

    op.add_column("payment_transactions", sa.Column("method", sa.String(), server_default="BANK_TRANSFER", nullable=False))
    op.add_column("payment_transactions", sa.Column("kind", sa.String(), server_default="DEPOSIT", nullable=False))
    op.add_column("payment_transactions", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "payment_transactions_created_by_id_fkey", "payment_transactions", "users", ["created_by_id"], ["id"]
    )

    op.add_column("matches", sa.Column("booking_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_matches_booking_id"), "matches", ["booking_id"], unique=False)
    op.create_foreign_key("matches_booking_id_fkey", "matches", "bookings", ["booking_id"], ["id"])

    op.add_column("player_profiles", sa.Column("purpose", sa.String(), nullable=True))
    op.add_column("player_profiles", sa.Column("availability", sa.String(), nullable=True))
    op.add_column("player_profiles", sa.Column("preferred_amenities", sa.String(), nullable=True))
    op.add_column("player_profiles", sa.Column("budget_max", sa.Float(), nullable=True))

    op.create_index(op.f("ix_venues_owner_id"), "venues", ["owner_id"], unique=False)

    # ------------------------------------------------------------------ data backfill
    # Khách tại quầy từng được lưu trong refund_reason dạng "Khách tại quầy: Tên (SĐT)"
    op.execute(r"""
        UPDATE bookings SET
            source = 'DESK',
            guest_name = NULLIF(btrim(regexp_replace(
                substring(refund_reason from 'Khách tại quầy:\s*(.*)$'), '\s*\([^()]*\)\s*$', '')), ''),
            guest_phone = NULLIF(btrim(substring(refund_reason from '\(([^()]*)\)\s*$')), ''),
            refund_reason = NULL
        WHERE refund_reason LIKE 'Khách tại quầy%'
    """)

    op.execute("UPDATE bookings SET payment_status = 'FULLY_PAID' WHERE payment_status = 'PAID'")
    op.execute("UPDATE bookings SET payment_status = 'UNPAID' WHERE payment_status IS NULL OR payment_status = 'REFUNDED'")
    op.execute("""
        UPDATE bookings b SET
            deposit_amount = round(b.total_price * 0.5),
            paid_amount = CASE b.payment_status
                WHEN 'FULLY_PAID' THEN b.total_price
                WHEN 'DEPOSIT_PAID' THEN round(b.total_price * 0.5)
                WHEN 'PARTIALLY_PAID' THEN COALESCE((
                    SELECT SUM(t.amount_in) FROM payment_transactions t
                    WHERE t.booking_id = b.id AND t.status = 'SUCCESS'), 0)
                ELSE 0 END
    """)

    # Trước đây đơn online mới tạo mang trạng thái CONFIRMED dù chưa cọc. Chuyển về đúng nghĩa:
    # còn trong 15 phút -> PENDING (chờ cọc); quá 15 phút -> EXPIRED (kèm yêu cầu hoàn nếu đã chuyển thiếu).
    op.execute("""
        UPDATE bookings SET
            status = 'EXPIRED',
            refund_status = CASE WHEN paid_amount > 0 THEN 'PENDING' ELSE refund_status END,
            refund_amount = CASE WHEN paid_amount > 0 THEN paid_amount ELSE refund_amount END
        WHERE status = 'CONFIRMED' AND source = 'ONLINE'
          AND payment_status IN ('UNPAID', 'PARTIALLY_PAID')
          AND created_at < now() - interval '15 minutes'
    """)
    op.execute("""
        UPDATE bookings SET status = 'PENDING', expires_at = created_at + interval '15 minutes'
        WHERE status = 'CONFIRMED' AND source = 'ONLINE' AND payment_status IN ('UNPAID', 'PARTIALLY_PAID')
    """)

    op.execute("""
        UPDATE booking_details d SET is_active = FALSE
        FROM bookings b WHERE b.id = d.booking_id AND b.status IN ('CANCELLED', 'EXPIRED')
    """)

    # Phòng đấu từng trỏ tới đơn đặt bằng chuỗi "Vé #<id>" trong notes
    op.execute(r"""
        UPDATE matches m SET booking_id = b.id
        FROM bookings b
        WHERE m.notes ~ 'Vé #[0-9]+' AND b.id = substring(m.notes from 'Vé #([0-9]+)')::int
    """)
    op.execute(r"""
        UPDATE matches SET notes = NULLIF(btrim(regexp_replace(notes, '\s*•?\s*Vé #[0-9]+(\s*\([^()]*\))?', '', 'g')), '')
        WHERE notes ~ 'Vé #[0-9]+'
    """)

    # Gỡ dữ liệu trùng trước khi thêm ràng buộc duy nhất (giữ dòng cũ nhất / đánh giá mới nhất)
    op.execute("""
        DELETE FROM match_participants a USING match_participants b
        WHERE a.match_id = b.match_id AND a.user_id = b.user_id AND a.id > b.id
    """)
    op.execute("""
        DELETE FROM operating_hours a USING operating_hours b
        WHERE a.venue_id = b.venue_id AND a.day_of_week = b.day_of_week AND a.id > b.id
    """)
    op.execute("""
        DELETE FROM reviews a USING reviews b
        WHERE a.user_id = b.user_id AND a.venue_id = b.venue_id AND a.id < b.id
    """)
    op.execute("""
        UPDATE payment_transactions a SET reference_number = NULL
        FROM payment_transactions b
        WHERE a.reference_number = b.reference_number AND a.id > b.id
          AND a.reference_number IS NOT NULL AND a.reference_number <> ''
    """)

    # ------------------------------------------------------------------ integrity checks
    _abort_if_rows(
        "SELECT id, booking_id FROM booking_details WHERE end_time <= start_time LIMIT 5",
        "Có khung giờ đặt sân có giờ kết thúc không sau giờ bắt đầu (id, booking_id)",
    )
    _abort_if_rows(
        """
        SELECT a.booking_id, b.booking_id, a.court_id, a.date FROM booking_details a
        JOIN booking_details b ON a.court_id = b.court_id AND a.date = b.date AND a.id < b.id
             AND a.start_time < b.end_time AND b.start_time < a.end_time
        WHERE a.is_active AND b.is_active LIMIT 5
        """,
        "Đang tồn tại các đơn còn hiệu lực bị trùng giờ trên cùng sân, cần xử lý tay trước khi nâng cấp "
        "(booking_a, booking_b, court_id, date)",
    )

    # ------------------------------------------------------------------ constraints
    op.create_check_constraint("ck_booking_details_time_order", "booking_details", "end_time > start_time")
    op.create_index(
        "uq_booking_details_active_slot", "booking_details", ["court_id", "date", "start_time"],
        unique=True, postgresql_where=sa.text("is_active"),
    )
    # Ràng buộc loại trừ: hai dòng còn hiệu lực của cùng một sân không được có khoảng thời gian giao nhau
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.execute("""
        ALTER TABLE booking_details ADD CONSTRAINT ex_booking_details_no_overlap
        EXCLUDE USING gist (
            court_id WITH =,
            tsrange(("date" + start_time), ("date" + end_time)) WITH &&
        ) WHERE (is_active)
    """)

    op.create_unique_constraint("uq_match_participants_match_user", "match_participants", ["match_id", "user_id"])
    op.create_unique_constraint("uq_operating_hours_venue_day", "operating_hours", ["venue_id", "day_of_week"])
    op.create_unique_constraint("uq_reviews_user_venue", "reviews", ["user_id", "venue_id"])
    op.create_index(
        "uq_payment_transactions_reference", "payment_transactions", ["reference_number"],
        unique=True, postgresql_where=sa.text(REFERENCE_NOT_EMPTY),
    )

    # ------------------------------------------------------------------ code sequences
    op.execute("CREATE SEQUENCE IF NOT EXISTS booking_code_seq")
    op.execute("""
        SELECT setval('booking_code_seq', GREATEST(m.n, 1), m.n > 0)
        FROM (SELECT GREATEST(
                COALESCE((SELECT MAX(substring(booking_code from '^PK2K([0-9]+)$')::bigint) FROM bookings), 0),
                COALESCE((SELECT MAX(id) FROM bookings), 0)) AS n) m
    """)
    op.execute("""
        UPDATE bookings SET booking_code = 'PK2K' || lpad(nextval('booking_code_seq')::text, 6, '0')
        WHERE booking_code IS NULL
    """)
    op.execute("CREATE SEQUENCE IF NOT EXISTS transaction_code_seq")
    op.execute("""
        SELECT setval('transaction_code_seq', GREATEST(m.n, 1), m.n > 0)
        FROM (SELECT COALESCE((SELECT MAX(id) FROM payment_transactions), 0) AS n) m
    """)


def downgrade() -> None:
    op.execute("DROP SEQUENCE IF EXISTS transaction_code_seq")
    op.execute("DROP SEQUENCE IF EXISTS booking_code_seq")
    op.drop_index("uq_payment_transactions_reference", table_name="payment_transactions")
    op.drop_constraint("uq_reviews_user_venue", "reviews", type_="unique")
    op.drop_constraint("uq_operating_hours_venue_day", "operating_hours", type_="unique")
    op.drop_constraint("uq_match_participants_match_user", "match_participants", type_="unique")
    op.execute("ALTER TABLE booking_details DROP CONSTRAINT IF EXISTS ex_booking_details_no_overlap")
    op.drop_index("uq_booking_details_active_slot", table_name="booking_details")
    op.drop_constraint("ck_booking_details_time_order", "booking_details", type_="check")

    # Trả trạng thái mới về bộ trạng thái cũ
    op.execute("UPDATE bookings SET status = 'CANCELLED' WHERE status IN ('EXPIRED', 'NO_SHOW')")
    op.execute("UPDATE bookings SET status = 'CONFIRMED' WHERE status IN ('PENDING', 'CHECKED_IN')")

    op.drop_index(op.f("ix_venues_owner_id"), table_name="venues")
    for column in ("budget_max", "preferred_amenities", "availability", "purpose"):
        op.drop_column("player_profiles", column)
    op.drop_constraint("matches_booking_id_fkey", "matches", type_="foreignkey")
    op.drop_index(op.f("ix_matches_booking_id"), table_name="matches")
    op.drop_column("matches", "booking_id")
    op.drop_constraint("payment_transactions_created_by_id_fkey", "payment_transactions", type_="foreignkey")
    for column in ("created_by_id", "kind", "method"):
        op.drop_column("payment_transactions", column)
    op.drop_column("booking_details", "is_active")
    for fk in ("bookings_refunded_by_id_fkey", "bookings_cancelled_by_id_fkey", "bookings_checked_in_by_id_fkey"):
        op.drop_constraint(fk, "bookings", type_="foreignkey")
    for column in (
        "refunded_by_id", "cancel_reason", "cancelled_by_id", "cancelled_at", "checked_in_by_id",
        "checked_in_at", "expires_at", "paid_amount", "deposit_amount", "guest_phone", "guest_name", "source",
    ):
        op.drop_column("bookings", column)
