@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo ================================================================
echo  KHỞI ĐỘNG PICKLEMATCH2K TRÊN MÁY PHÁT TRIỂN
echo  API: 8000  -  Cổng người dùng: 3000  -  Cổng quản trị: 3001
echo ================================================================
echo.

if not exist "%ROOT%venv\Scripts\activate.bat" (
    echo [LỖI] Chưa có môi trường ảo Python ở thư mục venv. Xem README.md, mục Cài đặt.
    pause
    exit /b 1
)
if not exist "%ROOT%frontend\node_modules" (
    echo [LỖI] Chưa cài thư viện cho frontend. Chạy lệnh npm ci trong thư mục frontend.
    pause
    exit /b 1
)
if not exist "%ROOT%admin-portal\node_modules" (
    echo [LỖI] Chưa cài thư viện cho admin-portal. Chạy lệnh npm ci trong thư mục admin-portal.
    pause
    exit /b 1
)

echo [1/4] Kiểm tra phiên bản cơ sở dữ liệu...
call "%ROOT%venv\Scripts\activate.bat"
pushd "%ROOT%backend"
python manage.py migrate --check
set "DB_STATE=%errorlevel%"
popd

if "%DB_STATE%"=="3" (
    echo.
    echo  CSDL cần được nâng cấp thì mới chạy được phiên bản mã nguồn này.
    echo  Lệnh nâng cấp tự sao lưu CSDL vào thư mục backups rồi mới thay đổi, dữ liệu cũ được giữ lại.
    echo.
    choice /C YN /M "Nâng cấp CSDL ngay bây giờ"
    if errorlevel 2 (
        echo Đã dừng. Chưa có gì thay đổi.
        pause
        exit /b 1
    )
    pushd "%ROOT%backend"
    python manage.py migrate
    if errorlevel 1 (
        popd
        echo.
        echo [LỖI] Nâng cấp CSDL không thành công. Xem thông báo phía trên.
        pause
        exit /b 1
    )
    popd
)
if not "%DB_STATE%"=="0" if not "%DB_STATE%"=="3" (
    echo.
    echo [LỖI] Không kiểm tra được CSDL. Xem thông báo phía trên.
    pause
    exit /b 1
)

echo.
echo [2/4] Mở Backend API - cổng 8000...
start "PM2K - Backend API - 8000" /D "%ROOT%backend" cmd /k python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

timeout /t 2 /nobreak >nul

echo [3/4] Mở cổng người chơi, chủ sân, nhân viên - cổng 3000...
start "PM2K - Cong nguoi dung - 3000" /D "%ROOT%frontend" cmd /k npm run dev

timeout /t 2 /nobreak >nul

echo [4/4] Mở cổng quản trị hệ thống - cổng 3001...
start "PM2K - Cong quan tri - 3001" /D "%ROOT%admin-portal" cmd /k npm run dev

echo.
echo ================================================================
echo  Ba cửa sổ vừa mở là ba máy chủ. Đóng cửa sổ nào là dừng máy chủ đó.
echo ================================================================
echo  - Tài liệu API (Swagger):  http://localhost:8000/docs
echo  - Cổng người dùng:         http://localhost:3000
echo  - Cổng quản trị:           http://localhost:3001
echo ================================================================
echo.
pause
