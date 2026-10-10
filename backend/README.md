# ⚙️ PickleMatch2K - Backend API Service

Dịch vụ Backend API hiệu năng cao được xây dựng trên nền tảng **FastAPI**, kết nối CSDL quan hệ **PostgreSQL 15** (hoặc **SQLite** cục bộ), hỗ trợ giao tiếp Realtime qua **WebSocket** và tích hợp mô hình học máy **Random Forest** (Scikit-Learn) gợi ý bạn chơi Pickleball theo trình độ DUPR.

---

## 📁 Cấu Trúc Thư Mục (Directory Structure)

```
backend/
├── app/                  # Mã nguồn chính của dịch vụ FastAPI
│   ├── api/              # API Route Handlers (Auth, Venues, Bookings, Matches, AI, Admin, WS)
│   ├── core/             # Cấu hình bảo mật, Settings, JWT tokens
│   ├── db/               # Database session và Base model
│   ├── ml/               # Module AI Random Forest (Dataset, Train, Benchmark, Model .pkl)
│   ├── models/           # SQLAlchemy Models (User, Venue, Court, Booking, Match, Payment...)
│   ├── schemas/          # Pydantic validation schemas
│   ├── services/         # Business logic (Slot Locking, SePay, DUPR, AI Matching)
│   ├── utils/            # Tiện ích tính khoảng cách GPS Haversine
│   └── main.py           # Điểm khởi chạy FastAPI & Static file mounting
│
├── scripts/              # Các công cụ dòng lệnh (CLI tools) quản trị CSDL
│   ├── show_db.py        # Báo cáo thống kê toàn diện CSDL
│   ├── sync_db.py        # Đồng bộ 2 chiều PostgreSQL <-> SQLite
│   ├── seed.py           # Nạp dữ liệu mẫu ban đầu
│   ├── reset_db.py       # Tái tạo cấu trúc bảng trắng
│   ├── import_3_venues.py# Nạp 3 cụm sân thật đồ án KLTN
│   ├── import_excel.py   # Nhập dữ liệu từ file Excel
│   └── README.md         # Sổ tay hướng dẫn chi tiết từng script
│
├── tests/                # Bộ kiểm thử tự động toàn diện (23 tests PASS)
│   ├── integration/      # Pytest đa luồng & thuật toán (test_concurrency, realtime, recommendation)
│   ├── verification/     # Unittest nghiệp vụ (verify_api, owner, sepay, services, staff, images)
│   ├── conftest.py       # Cấu hình Pytest Fixtures
│   ├── run_all_tests.py  # Script chạy tổng hợp 23 bài test tự động
│   └── README.md         # Hướng dẫn chi tiết kiểm thử
│
├── alembic/              # Cấu hình Database Migrations
├── uploads/              # Thư mục lưu trữ hình ảnh sân tải lên vật lý
├── Dockerfile            # Container image build manifest
├── requirements.txt      # Danh sách thư viện Python
├── pickleball.db         # Cơ sở dữ liệu SQLite cục bộ (đã đồng bộ 100%)
├── manage.py             # Bộ điều khiển dòng lệnh quản trị tập trung
└── seed.py               # Entrypoint nạp dữ liệu ban đầu cho Docker Compose
```

---

## 🚀 Khởi Chạy Dịch Vụ Cục Bộ (Local Development)

```bash
# 1. Kích hoạt môi trường ảo Python
..\venv\Scripts\activate

# 2. Khởi chạy Uvicorn Server (Port 8000, Hot-Reload)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🛠️ Công Cụ Quản Trị Trung Tâm (`manage.py`)

Hệ thống tích hợp sẵn bộ CLI điều khiển trực quan:

```bash
# In báo cáo thống kê dữ liệu
python manage.py show

# Đồng bộ PostgreSQL sang SQLite
python manage.py sync

# Nạp dữ liệu mẫu ban đầu
python manage.py seed

# Khởi tạo lại CSDL trắng
python manage.py reset

# Nạp 3 cụm sân đồ án KLTN
python manage.py import-venues

# Nhập dữ liệu từ file Excel
python manage.py import-excel --file ../docs/Mau_Nhap_Du_Lieu_Pickleball.xlsx

# Chạy toàn bộ 23 bài kiểm thử tự động
python manage.py test
```
