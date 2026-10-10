"""
===============================================================================
BACKUP / RESTORE DATABASE - PICKLEMATCH2K
===============================================================================
Sao lưu và khôi phục CSDL PostgreSQL bằng pg_dump / pg_restore.

    python scripts/backup_db.py                     # tạo backups/<db>_<thời gian>.dump
    python scripts/backup_db.py --restore-into pickleball_copy --file backups/x.dump

Thông tin kết nối lấy từ DATABASE_URL trong cấu hình ứng dụng, mật khẩu được
truyền cho pg_dump qua biến môi trường của tiến trình con (không in ra màn hình).
Lệnh khôi phục luôn tạo MỘT CSDL MỚI: không ghi đè CSDL đang cấu hình, và cũng từ chối
ghi đè một CSDL đã tồn tại trừ khi thêm --overwrite.
===============================================================================
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import URL, make_url  # noqa: E402

from app.core.config import settings  # noqa: E402

BACKUP_DIR = BACKEND_DIR.parent / "backups"


def find_pg_tool(name: str) -> str:
    """Tìm pg_dump / pg_restore trong PATH hoặc thư mục cài đặt PostgreSQL trên Windows."""
    found = shutil.which(name)
    if found:
        return found
    candidates = sorted(glob.glob(rf"C:\Program Files\PostgreSQL\*\bin\{name}.exe"), reverse=True)
    if candidates:
        return candidates[0]
    raise FileNotFoundError(f"Không tìm thấy {name}. Hãy cài PostgreSQL client hoặc thêm thư mục bin vào PATH.")


def _postgres_url() -> URL:
    url = make_url(settings.DATABASE_URL)
    if not url.drivername.startswith("postgresql"):
        raise SystemExit("DATABASE_URL không phải PostgreSQL nên không dùng được pg_dump.")
    return url


def _tool_args(url: URL) -> list[str]:
    args = ["--host", url.host or "localhost", "--port", str(url.port or 5432)]
    if url.username:
        args += ["--username", url.username]
    return args


def _tool_env(url: URL) -> dict:
    env = dict(os.environ)
    if url.password:
        env["PGPASSWORD"] = str(url.password)
    return env


def backup(output_dir: Path = BACKUP_DIR) -> Path:
    url = _postgres_url()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{url.database}_{datetime.now():%Y%m%d_%H%M%S}.dump"
    cmd = [find_pg_tool("pg_dump"), *_tool_args(url), "--format=custom", "--no-owner",
           "--file", str(target), url.database]
    subprocess.run(cmd, env=_tool_env(url), check=True)
    print(f"✓ Đã sao lưu CSDL '{url.database}' -> {target} ({target.stat().st_size:,} bytes)")
    return target


def restore_into(dump_file: Path, target_db: str, overwrite: bool = False) -> None:
    url = _postgres_url()
    if target_db == url.database:
        raise SystemExit("Từ chối khôi phục đè lên CSDL đang cấu hình. Hãy chọn tên CSDL khác.")
    if not target_db.replace("_", "").isalnum():
        raise SystemExit("Tên CSDL đích chỉ được chứa chữ, số và dấu gạch dưới.")
    if not Path(dump_file).exists():
        raise SystemExit(f"Không tìm thấy file sao lưu: {dump_file}")

    admin_engine = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target_db}).scalar()
        if exists and not overwrite:
            raise SystemExit(f"CSDL '{target_db}' đã tồn tại. Chọn tên khác, hoặc thêm --overwrite nếu chắc chắn muốn thay nó.")
        conn.execute(text(f'DROP DATABASE IF EXISTS "{target_db}"'))
        conn.execute(text(f'CREATE DATABASE "{target_db}"'))
    admin_engine.dispose()

    cmd = [find_pg_tool("pg_restore"), *_tool_args(url), "--no-owner", "--dbname", target_db, str(dump_file)]
    subprocess.run(cmd, env=_tool_env(url), check=True)
    print(f"✓ Đã khôi phục {dump_file.name} vào CSDL '{target_db}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sao lưu / khôi phục CSDL PickleMatch2K")
    parser.add_argument("--restore-into", help="Tên CSDL mới sẽ được tạo để khôi phục bản sao lưu")
    parser.add_argument("--file", help="File .dump dùng để khôi phục (mặc định: bản sao lưu mới nhất)")
    parser.add_argument("--overwrite", action="store_true", help="Cho phép thay CSDL đích nếu nó đã tồn tại")
    args = parser.parse_args()

    if args.restore_into:
        dumps = sorted(BACKUP_DIR.glob("*.dump"), key=lambda p: p.stat().st_mtime)
        if not args.file and not dumps:
            raise SystemExit(f"Chưa có bản sao lưu nào trong {BACKUP_DIR}.")
        restore_into(Path(args.file) if args.file else dumps[-1], args.restore_into, overwrite=args.overwrite)
    else:
        backup()


if __name__ == "__main__":
    main()
