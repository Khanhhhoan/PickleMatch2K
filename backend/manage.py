"""
Bộ lệnh quản trị PickleMatch2K. Chạy trong thư mục backend/ với môi trường ảo đã kích hoạt:

    python manage.py migrate        Sao lưu rồi đưa schema lên phiên bản mới nhất (--check | --no-backup)
    python manage.py show           Báo cáo tổng quan dữ liệu (chỉ đọc)
    python manage.py seed           Nạp dữ liệu demo vào CSDL trống   (--if-empty | --reset | --preferences | --matches
                                    | --feedback [--regenerate] | --activity [--venue ID])
    python manage.py reset          Xóa sạch, dựng lại CSDL trống + tài khoản Admin (phải xác nhận)
    python manage.py import-excel   Nhập cụm sân từ file Excel        (--file duong_dan.xlsx, --dry-run)
    python manage.py backup         Sao lưu CSDL ra thư mục backups/
    python manage.py train-model    Huấn luyện lại mô hình ghép cặp   (--report | --synthetic)
    python manage.py test           Chạy bộ kiểm thử tự động trên CSDL pickleball_test

Các lệnh xóa dữ liệu (reset, seed --reset) hỏi xác nhận trừ khi thêm --yes.
"""
import argparse
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


# Mã thoát của `migrate --check` khi CSDL còn migration chưa chạy (để file .bat nhận biết)
EXIT_MIGRATION_PENDING = 3


def migrate(backup_first: bool = True, check_only: bool = False) -> None:
    """Nâng cấp schema. CSDL đang có dữ liệu được sao lưu trước; sao lưu thất bại thì dừng, không nâng cấp."""
    from sqlalchemy.exc import OperationalError

    from app.core.config import settings
    from app.db.database import engine
    from app.db.migrations import describe_current, migration_status, run_migrations

    try:
        status = migration_status()
    except OperationalError as exc:
        reason = str(getattr(exc, "orig", exc)).strip().splitlines()[0]
        raise SystemExit(
            f"Không kết nối được CSDL '{engine.url.database}': {reason}\n"
            "Kiểm tra PostgreSQL đang chạy và DATABASE_URL trong file .env."
        )

    if status["unknown"]:
        raise SystemExit(
            f"CSDL đang ở revision {status['current']} mà mã nguồn này không có. "
            "Hãy cập nhật mã nguồn lên bản mới nhất (git pull) rồi chạy lại."
        )
    if not status["pending"]:
        print(f"Schema đã ở phiên bản mới nhất ({status['head']}).")
        return

    print(f"Schema của CSDL '{engine.url.database}': {describe_current(status)} -> cần nâng lên {status['head']}.")
    if check_only:
        print("Chạy `python manage.py migrate` để nâng cấp (CSDL được sao lưu vào backups/ trước khi thay đổi).")
        raise SystemExit(EXIT_MIGRATION_PENDING)

    if backup_first and not status["empty"] and not settings.is_sqlite:
        from scripts.backup_db import backup

        try:
            dump = backup()
        except Exception as exc:
            raise SystemExit(
                f"Không sao lưu được CSDL ({exc}). Chưa thay đổi gì.\n"
                "Hãy cài công cụ pg_dump, hoặc tự sao lưu rồi chạy lại với --no-backup."
            )
        print(f"Nếu cần quay lại: python scripts/backup_db.py --restore-into <ten_csdl_moi> --file \"{dump}\"")

    run_migrations()
    print(f"Schema đã ở phiên bản mới nhất ({migration_status()['current']}).")
    if status["empty"]:
        print("CSDL chưa có dữ liệu. Nạp dữ liệu demo: python manage.py seed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bộ lệnh quản trị PickleMatch2K", epilog=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["migrate", "show", "seed", "reset", "import-excel", "backup", "train-model", "test"])
    parser.add_argument("--yes", action="store_true", help="Không hỏi xác nhận với lệnh xóa dữ liệu")
    parser.add_argument("--no-backup", action="store_true", help="migrate: không sao lưu trước khi nâng cấp schema")
    parser.add_argument("--check", action="store_true", help="migrate: chỉ báo trạng thái (mã thoát 3 nếu cần nâng cấp)")
    parser.add_argument("--if-empty", action="store_true", help="seed: bỏ qua nếu CSDL đã có dữ liệu")
    parser.add_argument("--reset", action="store_true", help="seed: xóa toàn bộ dữ liệu rồi nạp lại")
    parser.add_argument("--preferences", action="store_true", help="seed: chỉ bổ sung mục đích chơi và ngày sinh mẫu cho tài khoản demo")
    parser.add_argument("--feedback", action="store_true", help="seed: chỉ nạp phiếu ghép cặp mô phỏng để huấn luyện mô hình")
    parser.add_argument("--regenerate", action="store_true",
                        help="seed --feedback: thay phiếu mô phỏng cũ bằng bộ sinh theo quy tắc hiện tại (giữ câu trả lời khảo sát thật)")
    parser.add_argument("--matches", action="store_true", help="seed: nạp thêm người chơi và phòng đấu mẫu để thử ghép trận")
    parser.add_argument("--activity", action="store_true", help="seed: nạp thêm hoạt động mẫu cho cụm sân mới chưa có đơn nào")
    parser.add_argument("--venue", type=int, default=None, help="seed --activity: chỉ nạp cho cụm sân mang id này")
    parser.add_argument("--file", "-f", default=None, help="import-excel: đường dẫn file .xlsx")
    parser.add_argument("--dry-run", action="store_true", help="import-excel: chỉ kiểm tra, không ghi")
    parser.add_argument("--report", action="store_true", help="train-model: chỉ in bảng đánh giá")
    parser.add_argument("--synthetic", action="store_true", help="train-model: buộc dùng dữ liệu tổng hợp")
    if len(sys.argv) == 1:
        parser.print_help()
        return
    args, extra = parser.parse_known_args()

    if args.action == "migrate":
        migrate(backup_first=not args.no_backup, check_only=args.check)
    elif args.action == "show":
        from scripts.show_db import show_db_stats

        show_db_stats()
    elif args.action == "seed":
        from scripts import seed

        if args.preferences:
            from app.db.database import SessionLocal
            from scripts._common import ensure_schema

            ensure_schema()
            with SessionLocal() as db:
                print(f"Đã bổ sung mục đích chơi, ngày sinh mẫu cho {seed.apply_demo_preferences(db)} tài khoản demo.")
        elif args.feedback:
            from app.db.database import SessionLocal
            from scripts._common import ensure_schema

            ensure_schema()
            with SessionLocal() as db:
                seed.report_simulated_feedback(seed.seed_simulated_feedback(db, replace=args.regenerate))
        elif args.matches:
            from app.db.database import SessionLocal
            from scripts._common import ensure_schema

            ensure_schema()
            with SessionLocal() as db:
                seed.report_match_demo(seed.seed_match_demo(db))
        elif args.activity:
            from scripts._common import ensure_schema

            ensure_schema()
            seed.report_venue_activity(seed.add_venue_activity(args.venue))
        else:
            seed.seed_database(if_empty=args.if_empty, reset=args.reset, assume_yes=args.yes)
    elif args.action == "reset":
        from scripts.reset_db import reset_database

        reset_database(assume_yes=args.yes)
    elif args.action == "import-excel":
        from scripts.import_excel import DEFAULT_TEMPLATE, import_from_excel

        import_from_excel(args.file or DEFAULT_TEMPLATE, dry_run=args.dry_run)
    elif args.action == "backup":
        from scripts.backup_db import backup

        backup()
    elif args.action == "train-model":
        from app.ml.train_model import train

        train(report_only=args.report, force_synthetic=args.synthetic)
    elif args.action == "test":
        sys.exit(subprocess.call([sys.executable, "-m", "pytest", str(BACKEND_DIR / "tests"), *extra], cwd=BACKEND_DIR.parent))


if __name__ == "__main__":
    main()
