@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo ================================================================
echo  MỞ ĐƯỜNG HẦM CHO WEBHOOK SEPAY
echo  Dùng khi muốn thử thanh toán cọc bằng chuyển khoản thật.
echo  Cần chạy dự án trước (start_all.bat) và giữ cửa sổ này mở.
echo ================================================================
echo.

if not exist "%ROOT%venv\Scripts\python.exe" (
    echo [LỖI] Chưa có môi trường ảo Python ở thư mục venv. Xem README.md, mục Cài đặt.
    pause
    exit /b 1
)

pushd "%ROOT%backend"
"%ROOT%venv\Scripts\python.exe" scripts\sepay_tunnel.py %*
popd
echo.
pause
