@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"

echo ================================================================
echo  KHỞI ĐỘNG PICKLEMATCH2K BẰNG DOCKER
echo  PostgreSQL 17, Redis, Backend, cổng người dùng, cổng quản trị
echo ================================================================
echo.

where docker >nul 2>nul
if errorlevel 1 (
    echo [LỖI] Không tìm thấy lệnh docker. Hãy cài và mở Docker Desktop trước.
    pause
    exit /b 1
)
if not exist "%ROOT%.env" (
    echo [LỖI] Chưa có file .env ở thư mục gốc.
    echo       Sao chép .env.example thành .env rồi đặt SECRET_KEY và POSTGRES_PASSWORD.
    pause
    exit /b 1
)

echo [*] Đang build image và khởi động các container. Lần đầu mất vài phút...
pushd "%ROOT%"
docker compose up --build -d
if errorlevel 1 (
    popd
    echo.
    echo [LỖI] Docker Compose báo lỗi. Kiểm tra Docker Desktop đã mở chưa và xem thông báo phía trên.
    pause
    exit /b 1
)
popd

echo.
echo ================================================================
echo  CÁC CONTAINER ĐÃ ĐƯỢC KHỞI ĐỘNG
echo ================================================================
echo  - Tài liệu API (Swagger):  http://localhost:8000/docs
echo  - Cổng người dùng:         http://localhost:3000
echo  - Cổng quản trị:           http://localhost:3001
echo.
echo  CSDL trong Docker là CSDL riêng, không phải PostgreSQL cài trên máy.
echo  Lần chạy đầu backend tự tạo bảng và nạp dữ liệu demo, mất khoảng một phút.
echo ================================================================
echo.
echo  Xem log:        docker compose logs -f backend
echo  Dừng hệ thống:  docker compose down
echo.
pause
