# 🏓 PickleMatch2K - Hệ Thống Đặt Sân & AI Ghép Trận Pickleball Thông Minh

> **Đồ Án Khóa Luận Tốt Nghiệp**  
> **Đề tài**: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

---

## 🌟 1. Giới Thiệu Tổng Quan

**PickleMatch2K** là nền tảng thể thao trực tuyến chuyên biệt dành cho cộng đồng Pickleball tại TP. Hồ Chí Minh. Hệ thống giải quyết trọn vẹn bài toán vận hành sân bãi thể thao thực tế:
- **Người chơi (Player)**: Tìm kiếm cụm sân gần nhất theo tọa độ GPS, xem ảnh sân thực tế với hiệu ứng hover trượt ảnh đa góc, xem lịch trống và đặt sân theo thời gian thực, đặt cọc an toàn 50% qua SePay VietQR, tạo kèo & ghép bạn chơi cùng trình độ DUPR sử dụng mô hình học máy **Random Forest**.
- **Chủ cụm sân (Owner)**: Quản lý chi tiết từng sân thi đấu, upload và quản lý bộ sưu tập hình ảnh sân, cấu hình khung giờ mở cửa và bảng giá linh hoạt (Giá cơ bản, Giờ cao điểm, Cuối tuần), phân công nhân viên ca trực, quản lý đơn đặt và đối soát doanh thu tự động.
- **Nhân viên ca trực (Staff)**: Cổng trực sân riêng biệt hỗ trợ quét QR check-in khách đến sân, thu 50% tiền còn lại và theo dõi doanh thu ca trực.
- **Quản trị viên (Admin)**: Cổng riêng trên Port 3001 giám sát toàn bộ hệ thống, quản lý người dùng, phê duyệt cụm sân, theo dõi doanh thu và cấu hình mô hình AI.

---

## 🛠️ 2. Kiến Trúc Công Nghệ (Tech Stack)

| Thành phần | Công nghệ / Thư viện | Vai trò |
| :--- | :--- | :--- |
| **Backend** | **Python 3.11+ / FastAPI** | RESTful API tốc độ cao, xử lý đa luồng bất đồng bộ (Asynchronous) |
| **ORM / Database** | **SQLAlchemy 2.0 / SQLite** | Quản lý mô hình dữ liệu quan hệ, giao dịch ACID an toàn |
| **Realtime Engine** | **FastAPI WebSocket** | Đồng bộ trạng thái khóa slot tức thì giữa nhiều người dùng |
| **AI / Machine Learning** | **Scikit-Learn (Random Forest Classifier)** | Dự đoán mức độ phù hợp và gợi ý ghép cặp người chơi theo DUPR |
| **Bảo mật & Auth** | **JWT (JSON Web Tokens) & SHA256/Bcrypt** | Xác thực người dùng và phân quyền 4 cấp (Player, Owner, Staff, Admin) |
| **Thanh toán trực tuyến** | **SePay VietQR API / Webhook** | Tạo mã QR động thanh toán cọc 50% và đối soát tự động |
| **Frontend Web App** | **Next.js 16 (App Router) + React 19 + TypeScript** | Giao diện người dùng SSR/CSR hiện đại, responsive đa nền tảng |
| **Admin Portal** | **Next.js 16 (Port 3001) + TailwindCSS** | Cổng quản trị điều hành độc lập tối ưu bảo mật |

---

## 📁 3. Cấu Trúc Thư Mục Dự Án (Project Structure)

```
c:/KLTN/
├── README.md                 # Sổ tay hướng dẫn & Tài khoản nghiệm thu KLTN
├── .env                      # Cấu hình biến môi trường hệ thống (Database, Cloudinary, SePay)
├── .gitignore                # Quản lý loại trừ file rác, build cache & credentials
├── docker-compose.yml        # Cấu hình triển khai đa Container (Postgres, Redis, API, 2 Web)
├── start_all.bat             # Khởi động nhanh 3 cổng dịch vụ (Local Dev)
├── start_docker.bat          # Khởi động trọn gói bằng Docker
├── pyproject.toml            # Cấu hình môi trường Python & Pytest
│
├── docs/                     # 📑 Hồ sơ học thuật, giải thuật & dữ liệu KLTN
│   ├── README.md             # Mục lục tra cứu tài liệu
│   ├── HUONG_DAN_KLTN.md     # Đặc tả đề tài, công thức toán học MCDA & Random Forest
│   ├── DATABASE_DESIGN.md    # Thiết kế CSDL, ERD, Schema & chiến lược Indexing
│   ├── Nhom_6_Khanh_va_Khang.docx # Báo cáo Khóa luận tốt nghiệp đầy đủ
│   └── Mau_Nhap_Du_Lieu_Pickleball.xlsx # File Excel mẫu nhập dữ liệu cụm sân
│
├── backend/                  # ⚙️ Dịch vụ Backend API (FastAPI)
│   ├── README.md             # Hướng dẫn chi tiết kỹ thuật Backend
│   ├── app/                  # Mã nguồn chính (api, core, db, ml, models, schemas, services, utils)
│   ├── scripts/              # 🛠️ Toàn bộ công cụ dòng lệnh quản trị CSDL
│   │   ├── README.md         # Sổ tay hướng dẫn từng script
│   │   ├── show_db.py        # In báo cáo trực quan thống kê toàn diện CSDL
│   │   ├── sync_db.py        # Đồng bộ 2 chiều dữ liệu PostgreSQL <-> SQLite
│   │   ├── seed.py           # Nạp dữ liệu mẫu ban đầu
│   │   ├── reset_db.py       # Tái tạo cấu trúc bảng trắng
│   │   ├── import_3_venues.py# Nạp 3 cụm sân thật đồ án KLTN
│   │   └── import_excel.py   # Nạp dữ liệu từ file Excel
│   ├── tests/                # Bộ kiểm thử tự động toàn diện (23 tests PASS)
│   │   ├── integration/      # Pytest đa luồng (chống race-condition, realtime slot lock)
│   │   ├── verification/     # Unittest chuyên sâu (RBAC, SePay, Staff check-in, API)
│   │   ├── run_all_tests.py  # Script chạy tổng hợp 23 bài test tự động
│   │   └── README.md
│   ├── uploads/              # Thư mục lưu trữ hình ảnh sân tải lên vật lý
│   ├── manage.py             # 🎯 Bộ điều khiển CLI trung tâm (show, sync, seed, reset, test...)
│   ├── seed.py               # Entrypoint nạp dữ liệu ban đầu cho Docker Compose
│   ├── requirements.txt      # Danh mục thư viện Python
│   └── pickleball.db         # Cơ sở dữ liệu SQLite đầy đủ dữ liệu mẫu (đã đồng bộ 100%)
│
├── admin-portal/             # 👑 Cổng Quản Trị Hệ Thống Độc Lập (Port 3001)
│   ├── README.md             # Hướng dẫn kỹ thuật Cổng Quản Trị
│   ├── src/app/              # Next.js App Router dành riêng cho Super Admin
│   │   ├── page.tsx          # Bảng điều khiển trung tâm (KPIs, CRM, Sân, Đơn, SePay, AI)
│   │   └── login/            # Trang đăng nhập bảo mật riêng cho Admin
│   ├── src/lib/              # Client API & Auth Context
│   └── package.json          # Cấu hình khởi chạy trên cổng 3001
│
├── frontend/                 # 🏓 Cổng Người Chơi, Chủ Sân & Nhân Viên (Port 3000)
│   ├── README.md             # Hướng dẫn kỹ thuật Cổng Khách Hàng / Sân
│   ├── public/images/        # Tài nguyên ảnh và logo tĩnh
│   ├── src/
│   │   ├── app/              # Next.js App Router
│   │   │   ├── (auth)/       # Gom nhóm xác thực gọn gàng (login, register)
│   │   │   ├── venues/       # Chi tiết sân theo ID
│   │   │   ├── matches/      # Ghép kèo thi đấu DUPR & AI Matchmaker
│   │   │   ├── bookings/     # Lịch sử đơn đặt sân & vé QR
│   │   │   ├── owner/        # Cổng quản lý Chủ Sân (venues, bookings, staff)
│   │   │   ├── staff/        # Cổng nghiệp vụ Nhân Viên (check-in QR, ca trực)
│   │   │   └── profile/      # Hồ sơ cá nhân & chỉnh sửa DUPR
│   │   ├── components/       # UI Components tái sử dụng (VenueImageHoverSlider, SepayModal, PlayerBottomNav...)
│   │   └── lib/              # Client API, Auth Context, WebSocket Hook, Geolocation
│   └── package.json          # Cấu hình khởi chạy trên cổng 3000
```

---

## 🚀 4. Hướng Dẫn Khởi Chạy Hệ Thống

### Cách 1: Triển Khai Trọn Gói Bằng Docker (PostgreSQL 15 + Redis Thật 100%) - Khuyên Dùng
Chạy tệp tin:
```cmd
start_docker.bat
```
Hoặc lệnh Terminal:
```bash
docker compose up --build -d
```
Hệ thống sẽ tự động khởi tạo và chạy các container:
- 🐘 **PostgreSQL Server**: `localhost:5432` (Database: `pickleball_db`)
- ⚡ **Redis Cache**: `localhost:6379`
- ⚙️ **Backend API**: [http://localhost:8000/docs](http://localhost:8000/docs) (Tự động nạp toàn bộ CSDL bảng và dữ liệu mẫu)
- 🏓 **Cổng Người Chơi & Chủ Sân**: [http://localhost:3000](http://localhost:3000)
- 👑 **Cổng Quản Trị Hệ Thống Admin**: [http://localhost:3001](http://localhost:3001)

### Cách 2: Khởi Chạy Nhanh Local Bằng File Batch
Chạy tệp tin:
```cmd
start_all.bat
```

### Cách 3: Khởi chạy thủ công từng dịch vụ
1. **Backend (Port 8000)**:
   ```bash
   cd c:/KLTN
   .\venv\Scripts\Activate.ps1
   python backend/seed.py
   python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
   ```
2. **Frontend Client & Owner (Port 3000)**:
   ```bash
   cd c:/KLTN/frontend
   npm run dev
   ```
3. **Admin Portal (Port 3001)**:
   ```bash
   cd c:/KLTN/admin-portal
   npm run dev
   ```

---

## 🧪 5. Chạy Toàn Bộ Bộ Kiểm Thử Tự Động (Full Test Suite)

Để kiểm tra độ toàn vẹn và tin cậy của hệ thống:
```bash
python backend/tests/run_all_tests.py
```
Bộ kiểm thử bao gồm:
- **8 bài Pytest**: Khóa slot đồng thời (Double Booking Race Condition), Real-time WebSocket Slot Holding, Chuẩn hóa điểm số gợi ý (Distance, Price, Time, Rating, Preference).
- **15 bài Unittest Nghiệp Vụ**: Phân quyền RBAC Chủ sân, Quản lý Nhân viên ca trực, Upload & Xóa ảnh sân, Tích hợp SePay VietQR & Webhook, REST APIs & Tìm kiếm Haversine GPS.

---

## 🔑 6. Danh Sách Tài Khoản Thử Nghiệm

| Vai trò | Email đăng nhập | Mật khẩu | Phạm vi quyền hạn |
| :--- | :--- | :--- | :--- |
| **Quản trị viên (Admin)** | `admin@example.com` | `password` | Toàn quyền quản trị hệ thống tại Cổng [http://localhost:3001](http://localhost:3001) |
| **Chủ Sân RUDAL** | `owner_rudal@pickleball.vn` | `password` | Quản lý độc quyền **RUDAL Pickleball & Academy** (6 sân, nhân viên, doanh thu) |
| **Chủ Sân D-Joy Thủ Thiêm** | `owner_djoy_thuthiem@pickleball.vn` | `password` | Quản lý độc quyền **D-Joy Pickleball Thủ Thiêm** (11 sân) |
| **Chủ Sân 152 Nguyễn Oanh** | `owner_152nguyenoanh@pickleball.vn` | `password` | Quản lý độc quyền **Pickleball 152 Nguyễn Oanh Gò Vấp** (4 sân) |
| **Nhân Viên Ca Trực (RUDAL)** | `staff_owner_rudal@pickleball.vn` | `password` | Check-in khách vào sân, thu 50% tiền cọc còn lại tại `/staff/dashboard` |
| **Nhân Viên Ca Trực (152 Nguyễn Oanh)** | `staff_owner_152nguyenoanh@pickleball.vn` | `password` | Check-in khách vào sân, tạo đơn vãng lai tại quầy |
| **Khách hàng / VĐV (Demo)** | `player@example.com` | `password` | VĐV DUPR 3.5, tìm sân, đặt giữ chỗ realtime, ghép kèo thi đấu AI |
| **Khách hàng / VĐV (Khánh)** | `khanhhoan121209@gmail.com` | `password` | VĐV DUPR 3.5, có sẵn lịch sử 8 đơn đặt và kèo đấu thực tế |
