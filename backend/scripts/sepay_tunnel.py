"""
Mở đường hầm Cloudflare tới API đang chạy trên máy để SePay gọi được webhook, và in ra địa chỉ cần dán vào SePay.

    python scripts/sepay_tunnel.py              # API ở cổng 8000
    python scripts/sepay_tunnel.py --port 8010  # API ở cổng khác

Mỗi lần chạy, Cloudflare cấp một địa chỉ https://....trycloudflare.com MỚI, và địa chỉ đó chỉ dùng được khi cửa sổ
này còn mở. Vì vậy sau mỗi lần mở lại phải cập nhật địa chỉ webhook trong trang quản lý SePay; để nguyên địa chỉ cũ
thì SePay báo "Lỗi kết nối" và đơn đặt sân không tự xác nhận.

Cần cài cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
"""
import argparse
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

WEBHOOK_PATH = "/api/v1/payments/sepay-webhook"
HEALTH_PATH = "/api/v1/health"
TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
COMMON_LOCATIONS = (
    r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
    r"C:\Program Files\cloudflared\cloudflared.exe",
)


def find_cloudflared() -> Optional[str]:
    found = shutil.which("cloudflared")
    if found:
        return found
    return next((path for path in COMMON_LOCATIONS if Path(path).exists()), None)


def is_up(url: str, timeout: float = 8.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def copy_to_clipboard(value: str) -> bool:
    if sys.platform != "win32":
        return False
    try:
        subprocess.run("clip", input=value.encode("utf-16-le"), check=True, shell=True)
        return True
    except Exception:
        return False


def webhook_key_configured() -> bool:
    try:
        from app.core.config import settings

        return bool(settings.SEPAY_WEBHOOK_API_KEY)
    except Exception:
        return False


def announce(public_url: str) -> None:
    webhook = public_url + WEBHOOK_PATH
    copied = copy_to_clipboard(webhook)
    line = "=" * 78
    print(f"\n{line}\n ĐỊA CHỈ WEBHOOK CHO SEPAY{' (đã chép sẵn vào bộ nhớ tạm, chỉ cần dán)' if copied else ''}:\n\n   {webhook}\n")
    print(" Việc cần làm trên my.sepay.vn:")
    print("   1. Vào mục Webhooks, sửa webhook của PickleMatch2K, dán địa chỉ trên vào ô \"Gọi đến URL\" rồi lưu.")
    print("   2. Giao dịch nào đang báo lỗi thì mở ra và bấm \"Gửi lại\".")
    if webhook_key_configured():
        print("   3. Phần chứng thực chọn API Key và nhập đúng giá trị SEPAY_WEBHOOK_API_KEY trong file .env.")
    else:
        print("   Lưu ý: chưa đặt SEPAY_WEBHOOK_API_KEY nên ai biết địa chỉ này cũng gọi được webhook.")
        print("          Nên đặt khóa trong .env và chọn chứng thực API Key trên SePay trước khi dùng thật.")
    print(f"\n Giữ cửa sổ này mở trong lúc thử thanh toán. Đóng cửa sổ (hoặc Ctrl+C) là địa chỉ hết dùng được.\n{line}\n")


def verify(public_url: str) -> None:
    """Tên miền mới thường mất dưới một phút mới phân giải được; chờ rồi thử lại trước khi báo kết quả."""
    print(" Đang chờ địa chỉ mới có hiệu lực (thường dưới 1 phút)...")
    time.sleep(10)  # hỏi quá sớm thì máy nhớ luôn câu trả lời "không tồn tại" thêm một lúc
    for _ in range(22):
        if is_up(public_url + HEALTH_PATH):
            print(" Đã kiểm tra: gọi tới API qua địa chỉ này được. Có thể dán vào SePay.")
            return
        time.sleep(5)
    print(" Chưa kiểm tra được địa chỉ từ máy này (tên miền mới đôi khi cần thêm thời gian).\n"
          " Cứ dán địa chỉ vào SePay rồi bấm \"Gửi lại\"; nếu SePay vẫn báo lỗi kết nối thì chạy lại lệnh này.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Mở đường hầm Cloudflare cho webhook SePay")
    parser.add_argument("--port", type=int, default=8000, help="Cổng API đang chạy trên máy (mặc định 8000)")
    args = parser.parse_args()
    local = f"http://localhost:{args.port}"

    cloudflared = find_cloudflared()
    if not cloudflared:
        print("Chưa tìm thấy chương trình cloudflared. Tải và cài tại:\n"
              "  https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/")
        return 1
    if not is_up(local + HEALTH_PATH, timeout=5):
        print(f"API chưa chạy ở {local}. Hãy khởi động dự án (start_all.bat) trước, rồi chạy lại lệnh này.")
        return 1

    print(f"Đang mở đường hầm tới {local} ...")
    process = subprocess.Popen(
        [cloudflared, "tunnel", "--no-autoupdate", "--url", local],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
    )
    announced = False
    assert process.stdout is not None
    try:
        for line in process.stdout:
            if not announced:
                found = TUNNEL_URL.search(line)
                if found:
                    announced = True
                    announce(found.group(0))
                    threading.Thread(target=verify, args=(found.group(0),), daemon=True).start()
            elif " ERR " in line:
                print(" [cloudflared]", line.strip())
    except KeyboardInterrupt:
        pass
    finally:
        process.terminate()
    if not announced:
        print("cloudflared đã dừng mà chưa cấp được địa chỉ. Kiểm tra kết nối mạng rồi thử lại.")
        return 1
    print("Đã đóng đường hầm. Địa chỉ webhook vừa rồi không còn dùng được.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
