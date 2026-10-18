"""Bảng refund_proofs: nội dung chứng từ chuyển hoàn lưu trong CSDL thay vì thư mục backend/private_uploads

Máy chủ kiểu Render xóa ổ đĩa mỗi lần khởi động lại hay deploy, nên tệp chứng từ trên ổ đĩa sẽ mất. Bảng mới; tệp
chứng từ đang có trong backend/private_uploads/refund_proofs được chép vào bảng (tệp trên ổ đĩa giữ nguyên). Đơn có tên
chứng từ mà tệp không còn trên máy này thì giữ nguyên tên, tải về vẫn báo không tìm thấy như trước. Hạ cấp: ghi nội
dung trở lại thư mục đó rồi xóa bảng.

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-19 09:00:00

"""
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PROOF_DIR = Path(__file__).resolve().parents[2] / "private_uploads" / "refund_proofs"
MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}
PROOF_NAME = re.compile(r"^\d+_[0-9a-f]{32}\.(jpg|png|webp|pdf)$")

refund_proofs = sa.table(
    'refund_proofs',
    sa.column('booking_id', sa.Integer()),
    sa.column('name', sa.String()),
    sa.column('media_type', sa.String()),
    sa.column('size', sa.Integer()),
    sa.column('content', sa.LargeBinary()),
    sa.column('uploaded_at', sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    op.create_table(
        'refund_proofs',
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=50), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('booking_id'),
    )

    conn = op.get_bind()
    named = conn.execute(sa.text("SELECT id, refund_proof_file FROM bookings WHERE refund_proof_file IS NOT NULL")).all()
    for booking_id, name in named:
        path = PROOF_DIR / name
        if not PROOF_NAME.fullmatch(name) or not path.is_file():
            continue
        content = path.read_bytes()
        conn.execute(refund_proofs.insert().values(
            booking_id=booking_id, name=name, media_type=MEDIA_TYPES[path.suffix], size=len(content), content=content,
            uploaded_at=datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc),
        ))


def downgrade() -> None:
    conn = op.get_bind()
    stored = conn.execute(sa.text("SELECT name, content FROM refund_proofs")).all()
    if stored:
        PROOF_DIR.mkdir(parents=True, exist_ok=True)
    for name, content in stored:
        target = PROOF_DIR / name
        if PROOF_NAME.fullmatch(name) and not target.exists():
            target.write_bytes(bytes(content))
    op.drop_table('refund_proofs')
