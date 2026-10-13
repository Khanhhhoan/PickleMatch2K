# PickleMatch2K - Backend API

API FastAPI trên PostgreSQL. Hướng dẫn cài đặt và chạy nằm ở [README gốc](../README.md); tài liệu này mô tả
cấu trúc, cấu hình và các quy tắc nghiệp vụ của backend.

## Cấu trúc

```text
backend/
├── app/
│   ├── main.py             Khởi tạo ứng dụng, CORS, tác vụ nền, phục vụ ảnh /uploads
│   ├── api/v1/endpoints/   auth, users, venues, search, bookings, payments, matches, recommendations, ml, ws
│   ├── core/               config (biến môi trường), security (JWT, bcrypt), booking_policy, matching_policy, recommendation_config,
│   │                       rate_limit, redis_client, websocket_manager
│   ├── db/                 database (engine, phiên làm việc), base (đăng ký model), migrations (trạng thái schema)
│   ├── models/             user, venue, booking, payment (sổ giao dịch, sổ kết ca), match, ml (nhãn khảo sát)
│   ├── schemas/            Kiểu dữ liệu vào/ra của API (Pydantic)
│   ├── services/           Nghiệp vụ: booking, ledger (sổ giao dịch), shift (kết ca), payment, availability, slot_lock, venue,
│   │                       user, search, match, venue_recommendation, ml, maintenance (tác vụ nền), storage
│   ├── ml/                 features (đặc trưng dùng chung), train_model, mô hình .pkl và model_meta.json
│   └── utils/              timeutils (giờ Việt Nam, đồng hồ nghiệp vụ), geo (Haversine)
├── alembic/versions/       0001 schema gốc → 0002 chỉnh lệch CSDL cũ → 0003 lõi đặt sân → 0004 nhãn khảo sát → 0005 bỏ giờ rảnh → 0006 bỏ tiện ích ưa thích, ngân sách → 0007 thêm chênh lệch tuổi → 0008 sổ kết ca
├── scripts/                Script quản trị (seed, reset, import_excel, backup_db, show_db)
├── tests/                  Bộ kiểm thử pytest
├── manage.py               Bộ lệnh quản trị
├── requirements.txt        Thư viện chạy (đã ghim phiên bản)
└── requirements-dev.txt    Thêm pytest và ruff
```

## Cấu hình

Backend đọc biến môi trường, rồi tới file `.env` ở thư mục gốc và `backend/.env`. Mẫu đầy đủ: [`.env.example`](../.env.example).

| Biến | Bắt buộc | Ý nghĩa |
| :--- | :---: | :--- |
| `DATABASE_URL` | Có | `postgresql://user:pass@host:5432/ten_csdl` |
| `SECRET_KEY` | Có | Khóa ký JWT, tối thiểu 16 ký tự; giá trị mẫu bị từ chối khi `ENVIRONMENT=production` |
| `ENVIRONMENT` | | `development` (mặc định) hoặc `production` |
| `REDIS_URL` | | Để trống: giữ chỗ tạm và giới hạn đăng nhập lưu trong bộ nhớ tiến trình |
| `CORS_ORIGINS` | | Danh sách origin của hai ứng dụng web. Ở `development`, origin trong mạng LAN cũng được chấp nhận |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | Thời hạn phiên đăng nhập (mặc định 1440 phút) |
| `STORAGE_BACKEND` | | `local` (thư mục `uploads/`) hoặc `cloudinary` (cần `CLOUDINARY_*`) |
| `SEPAY_WEBHOOK_API_KEY` | | Khóa xác thực webhook SePay |
| `SEPAY_BANK_*`, `SEPAY_ACCOUNT_HOLDER` | | Tài khoản nhận tiền dùng chung khi `SEPAY_UNIFIED_TEST_MODE=true` |
| `SEPAY_SIMULATOR_ENABLED` | | `true`: bật API giả lập thanh toán cho demo và kiểm thử |

## Schema và migration

Schema chỉ được thay đổi qua Alembic. Khi sửa model:

```powershell
cd backend
alembic revision --autogenerate -m "mo ta thay doi"   # sinh file trong alembic/versions, đọc lại trước khi dùng
python manage.py migrate                               # sao lưu rồi áp dụng
python -m pytest tests/test_infrastructure.py          # kiểm tra schema khớp model
```

- `python manage.py migrate --check` chỉ báo trạng thái (mã thoát 3 nếu còn migration chưa chạy).
- CSDL tạo trước khi dự án dùng Alembic (có bảng nhưng không có `alembic_version`) được đánh dấu ở revision `0001`
  rồi nâng cấp, không mất dữ liệu.
- API kiểm tra phiên bản schema lúc khởi động và dừng với thông báo hướng dẫn nếu schema chưa được nâng cấp.

## Nhóm API

87 thao tác dưới tiền tố `/api/v1`; mô tả chi tiết từng tham số ở `http://localhost:8000/docs`.

| Nhóm | Số thao tác | Nội dung |
| :--- | :---: | :--- |
| `auth` | 2 | Đăng ký, đăng nhập (giới hạn số lần sai) |
| `users` | 14 | Hồ sơ cá nhân, đổi mật khẩu, chủ sân quản lý nhân viên, quản trị viên quản lý tài khoản |
| `venues` | 24 | Cụm sân, sân con, bảng giá, giờ mở cửa, ảnh, đánh giá, duyệt cụm sân |
| `search` | 2 | Tìm cụm sân, lịch trống theo ngày |
| `bookings` | 20 | Giữ chỗ tạm, tạo đơn, hủy, đơn tại quầy, check-in, thu tiền, dời lịch, hoàn tiền, thống kê |
| `payments` | 7 | Thông tin chuyển khoản, webhook SePay, giả lập, sổ giao dịch, kết ca tại quầy |
| `matches` | 11 | Phòng đấu: tạo trên đơn đã cọc, tham gia, rời, quản trị; mỗi phòng kèm độ phù hợp và cờ "mô hình đề xuất" cho người xem |
| `recommendations` | 1 | Gợi ý cụm sân, thang 100: gần 40, giá 35, giờ còn trống 25 (trang chủ dùng để xếp danh sách cho người chơi đã đăng nhập) |
| `ml` | 5 | Thông tin mô hình và ngưỡng đề xuất, dự đoán độ phù hợp, xếp hạng người chơi, khảo sát thu nhãn |

WebSocket: `/api/v1/ws/live` (sự kiện công khai toàn hệ thống), `/api/v1/ws/venues/{venue_id}` (lịch của một cụm sân),
`/api/v1/ws/user/{user_id}` (kênh riêng, cần token của chính người đó). Sự kiện công khai không chứa thông tin cá nhân
hay số tiền.

## Quy tắc đặt sân

Tham số nằm ở `app/core/booking_policy.py`; giao diện hiển thị đúng các giá trị này.

| Quy tắc | Giá trị |
| :--- | :--- |
| Độ dài một khung giờ | 60 phút |
| Tiền cọc | 50% tổng tiền |
| Hạn thanh toán cọc của đơn mới | 15 phút, quá hạn đơn chuyển `EXPIRED` và trả lại khung giờ |
| Giữ chỗ tạm khi đang chọn | 5 phút, tối đa 12 khung giờ mỗi người |
| Giới hạn | Tối đa 12 khung giờ mỗi đơn, 3 đơn chờ cọc mỗi người, đặt trước tối đa 60 ngày |
| Hủy trước giờ chơi từ 12 giờ trở lên | Hoàn 100% số tiền đã trả |
| Hủy trước giờ chơi từ 6 đến dưới 12 giờ | Không hoàn cọc, được hỗ trợ dời lịch |
| Hủy dưới 6 giờ hoặc không đến | Không hoàn cọc |

Giá một khung giờ (`availability_service.calculate_slot_price`): giá cơ sở là giá riêng của sân nếu có, ngược lại giá
`BASE` của cụm sân; khung bắt đầu trong giờ cao điểm dùng giá `PEAK`; thứ Bảy và Chủ nhật dùng giá `WEEKEND`
(trong giờ cao điểm lấy mức cao hơn giữa `PEAK` và `WEEKEND`). Đơn nhiều giờ là tổng giá từng khung.

Trạng thái đơn: `PENDING` (chờ cọc) → `CONFIRMED` → `CHECKED_IN` → `COMPLETED`; nhánh kết thúc khác: `NO_SHOW`,
`CANCELLED`, `EXPIRED`.

Mỗi khoản thu hoặc hoàn được ghi thành một dòng trong sổ giao dịch `payment_transactions` (loại `DEPOSIT`, `BALANCE`,
`REFUND`; hình thức `BANK_TRANSFER`, `CASH`) và cộng vào `paid_amount` của đơn trong cùng một giao dịch CSDL. Trạng thái
thanh toán (`UNPAID`, `PARTIALLY_PAID`, `DEPOSIT_PAID`, `FULLY_PAID`) được suy ra từ `paid_amount` so với tiền cọc và
tổng tiền. Doanh thu trên các bảng tổng quan được cộng từ sổ giao dịch.

Chống đặt trùng được bảo đảm ở ba lớp: giữ chỗ tạm (Redis hoặc bộ nhớ), kiểm tra trong giao dịch, và ràng buộc của
PostgreSQL (chỉ mục duy nhất theo khung giờ còn hiệu lực cùng ràng buộc loại trừ khoảng thời gian giao nhau), khai báo
trong `app/models/booking.py` và các migration ở `alembic/versions/`.

Webhook SePay ghi nhận mỗi mã tham chiếu đúng một lần, kể cả khi SePay gửi lặp hoặc gửi đồng thời.

## Tác vụ nền

Mỗi 60 giây (`app/services/maintenance.py`): hết hạn đơn chờ cọc, hoàn tất đơn và đánh dấu vắng mặt cho đơn đã qua
giờ, đóng phòng đấu đã qua giờ. Một tác vụ lỗi không chặn các tác vụ còn lại. Vì vậy API chạy bằng **một tiến trình**.

## Mô hình ghép cặp

```powershell
python manage.py seed --feedback                # nạp 10.000 phiếu ghép cặp mô phỏng vào bảng pair_feedback (bỏ qua nếu đã có)
python manage.py seed --feedback --regenerate   # thay các phiếu mô phỏng bằng bộ sinh theo quy tắc hiện tại
python manage.py train-model                    # huấn luyện từ bảng pair_feedback, ghi app/ml/match_rf_model.pkl + model_meta.json
python manage.py train-model --report           # chỉ in bảng đánh giá, không ghi file
```

File `.pkl` phụ thuộc đúng phiên bản scikit-learn ghim trong `requirements.txt`; đổi phiên bản thì huấn luyện lại.
Khi thiếu hoặc không nạp được mô hình, API ghép cặp trả kết quả rỗng kèm lý do, không tự đặt ra điểm số.
Đặc trưng: `app/ml/features.py`; quy tắc sinh phiếu mô phỏng và cấu hình rừng: `app/ml/train_model.py`; kết quả đánh
giá của mô hình đang dùng: `app/ml/model_meta.json`.

## Kiểm thử và kiểm tra mã

```powershell
python -m pytest                 # từ thư mục gốc dự án
python -m ruff check backend
```

Xem [tests/README.md](tests/README.md) và [scripts/README.md](scripts/README.md).
