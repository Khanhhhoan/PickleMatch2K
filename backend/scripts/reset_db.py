"""
Xóa toàn bộ dữ liệu và dựng lại CSDL trống (chỉ có danh mục tiện ích và một tài khoản Admin).

    python scripts/reset_db.py [--yes] [--admin-email EMAIL] [--admin-password MAT_KHAU]

Thao tác KHÔNG hoàn tác được: script bắt gõ lại tên CSDL để xác nhận (bỏ qua bằng --yes).
Nên sao lưu trước: python scripts/backup_db.py backup
Muốn có sẵn dữ liệu demo thay vì CSDL trống: python scripts/seed.py --reset
"""
import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts._common import rebuild_empty_schema  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.services.user_service import create_user  # noqa: E402

DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_PASSWORD = "123456"


def reset_database(admin_email: str = DEFAULT_ADMIN_EMAIL, admin_password: str = DEFAULT_ADMIN_PASSWORD,
                   assume_yes: bool = False) -> None:
    from scripts.seed import seed_amenities

    rebuild_empty_schema("Reset CSDL", assume_yes)
    with SessionLocal() as db:
        seed_amenities(db)
        create_user(db, email=admin_email, password=admin_password, role=UserRole.ADMIN.value, commit=False)
        db.commit()

    print("Đã dựng lại CSDL trống với danh mục tiện ích và tài khoản Admin:")
    print(f"    {admin_email}  /  {admin_password}")
    if admin_password == DEFAULT_ADMIN_PASSWORD:
        print("Đây là mật khẩu mặc định của môi trường demo: hãy đổi ngay nếu CSDL này được dùng thật.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Xóa sạch và dựng lại CSDL trống")
    parser.add_argument("--yes", action="store_true", help="Không hỏi xác nhận")
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()
    reset_database(args.admin_email, args.admin_password, assume_yes=args.yes)


if __name__ == "__main__":
    main()
