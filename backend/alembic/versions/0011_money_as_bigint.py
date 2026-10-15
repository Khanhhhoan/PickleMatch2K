"""Tiền VNĐ lưu bằng số nguyên (BIGINT) thay cho số thực (FLOAT)

13 cột tiền: bookings (total_price, deposit_amount, paid_amount, refund_amount), booking_details.price,
payment_transactions.amount_in, shift_closings (opening_float, counted_cash, cash_collected, transfer_collected,
refunded), courts.price, price_rules.price.

Trước khi đổi kiểu, migration kiểm tra từng cột: nếu có giá trị không phải số nguyên đồng, NaN, vô cực hoặc lớn bất
thường (từ 9 triệu tỷ đồng trở lên, vượt mức số thực còn chính xác), nó DỪNG và báo cột nào có bao nhiêu giá trị như
vậy - không làm tròn ngầm, không đổi dòng nào. Mọi giá trị hợp lệ đã là số nguyên nên chuyển sang BIGINT giữ nguyên
từng con số. Quay lại: `alembic downgrade 0010` đổi các cột về số thực, các con số vẫn giữ nguyên.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-15 23:50:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (bảng, cột, cho phép NULL, có giá trị mặc định 0 ở CSDL)
MONEY_COLUMNS = [
    ("bookings", "total_price", False, False),
    ("bookings", "deposit_amount", False, True),
    ("bookings", "paid_amount", False, True),
    ("bookings", "refund_amount", True, False),
    ("booking_details", "price", False, False),
    ("payment_transactions", "amount_in", False, False),
    ("shift_closings", "opening_float", False, False),
    ("shift_closings", "counted_cash", False, False),
    ("shift_closings", "cash_collected", False, False),
    ("shift_closings", "transfer_collected", False, False),
    ("shift_closings", "refunded", False, True),
    ("courts", "price", True, False),
    ("price_rules", "price", False, False),
]
# Từ 2^53 trở lên số thực không còn biểu diễn chính xác mọi số nguyên; số tiền như vậy chắc chắn là dữ liệu hỏng
SUSPICIOUS = 9_000_000_000_000_000


def _problems(bind) -> list:
    found = []
    for table, column, _, _ in MONEY_COLUMNS:
        count = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL AND ("
            f"{column} = 'NaN'::float8 OR abs({column}) >= {SUSPICIOUS} OR {column} <> round({column}))"
        )).scalar()
        if count:
            found.append(f"{table}.{column}: {count} giá trị")
    return found


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return  # SQLite chỉ dùng thử, bảng tạo thẳng từ model
    problems = _problems(bind)
    if problems:
        raise RuntimeError(
            "Dừng nâng cấp: có số tiền không phải số nguyên đồng hoặc bất thường, cần xem và sửa tay trước - "
            + "; ".join(problems)
        )
    for table, column, nullable, has_default in MONEY_COLUMNS:
        if has_default:
            op.alter_column(table, column, server_default=None, existing_type=sa.Float(), existing_nullable=nullable)
        op.alter_column(
            table, column, type_=sa.BigInteger(), existing_type=sa.Float(), existing_nullable=nullable,
            postgresql_using=f"round({column})::bigint",
        )
        if has_default:
            op.alter_column(table, column, server_default=sa.text("0"), existing_type=sa.BigInteger(),
                            existing_nullable=nullable)


def downgrade() -> None:
    if op.get_bind().dialect.name != 'postgresql':
        return
    for table, column, nullable, has_default in MONEY_COLUMNS:
        if has_default:
            op.alter_column(table, column, server_default=None, existing_type=sa.BigInteger(), existing_nullable=nullable)
        op.alter_column(
            table, column, type_=sa.Float(), existing_type=sa.BigInteger(), existing_nullable=nullable,
            postgresql_using=f"{column}::double precision",
        )
        if has_default:
            op.alter_column(table, column, server_default=sa.text("0"), existing_type=sa.Float(),
                            existing_nullable=nullable)
