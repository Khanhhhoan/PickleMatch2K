# PickleMatch2K - Hệ thống đặt sân và ghép trận Pickleball

> **Khóa luận tốt nghiệp** - Đề tài: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

## 1. Tổng quan

PickleMatch2K gồm một API và hai ứng dụng web phục vụ bốn vai trò:

| Vai trò | Cổng | Việc chính |
| :--- | :--- | :--- |
| **Người chơi** | `http://localhost:3000` | Tìm sân theo vị trí, xem lịch trống theo thời gian thực, đặt sân và cọc 50% qua VietQR, nhận vé QR, hủy/hoàn tiền theo chính sách, mở phòng đấu trên đơn đã cọc, tham gia các phòng đấu do mô hình đề xuất |
| **Chủ sân** | `http://localhost:3000/owner` | Thông tin cụm sân, sân con, bảng giá theo khung giờ, giờ mở cửa, nhân viên, quầy đặt sân, doanh thu |
| **Nhân viên** | `http://localhost:3000/staff` | Quầy đặt sân của cụm sân được phân công: tạo đơn tại quầy, tra mã/quét QR, check-in, thu tiền, dời lịch, xác nhận hoàn tiền |
| **Quản trị viên** | `http://localhost:3001` | Duyệt cụm sân, khóa/mở tài khoản, giám sát đơn đặt, giao dịch và phòng đấu |

Hai trọng tâm của hệ thống:

- **Quy trình đặt sân**: giữ chỗ → đặt → cọc 50% qua VietQR → vé QR → check-in → thu phần còn lại, kèm hủy và hoàn tiền
  theo chính sách.
- **Ghép trận bằng Random Forest**: mô hình ước lượng độ phù hợp giữa người chơi và từng phòng đấu đã mở, rồi đề xuất
  những phòng có độ phù hợp cao (từ 70%).

Thuật toán gợi ý cụm sân theo điểm đa tiêu chí vẫn có ở backend (`GET /api/v1/recommendations/venues`) nhưng giao diện
không dùng; trang chủ liệt kê cụm sân từ gần đến xa. Đặc trưng, dữ liệu và kết quả đánh giá của mô hình: xem
[docs/HUONG_DAN_KLTN.md](docs/HUONG_DAN_KLTN.md).

## 2. Công nghệ

| Thành phần | Công nghệ |
| :--- | :--- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Pydantic 2 |
| Cơ sở dữ liệu | PostgreSQL 17, migration bằng Alembic |
| Giữ chỗ tạm, giới hạn đăng nhập | Redis (tùy chọn; không có thì lưu trong bộ nhớ của tiến trình) |
| Thời gian thực | WebSocket của FastAPI |
| Học máy | scikit-learn (Random Forest), pandas, numpy |
| Xác thực | JWT, mật khẩu băm bằng bcrypt |
| Thanh toán | SePay VietQR (webhook) và bộ giả lập dùng khi demo |
| Web | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 |

## 3. Cấu trúc thư mục

```text
KLTN/
├── .env.example            Mẫu cấu hình (sao chép thành .env, không commit .env)
├── docker-compose.yml      Chạy toàn bộ hệ thống bằng Docker
├── start_all.bat           Chạy 3 dịch vụ trên máy phát triển
├── start_docker.bat        Chạy bằng Docker
├── pyproject.toml          Cấu hình pytest và ruff
├── .github/workflows/      Kiểm tra tự động (CI)
├── backend/                API FastAPI
│   ├── app/                api, core, db, ml, models, schemas, services, utils
│   ├── alembic/            Các phiên bản schema (0001 → 0006)
│   ├── scripts/            Script quản trị CSDL (xem backend/scripts/README.md)
│   ├── tests/              Bộ kiểm thử pytest (xem backend/tests/README.md)
│   └── manage.py           Bộ lệnh quản trị
├── frontend/               Cổng người chơi, chủ sân, nhân viên (cổng 3000)
├── admin-portal/           Cổng quản trị (cổng 3001)
├── scripts/e2e_smoke.js    Kiểm thử đầu-cuối qua trình duyệt
├── docs/                   Tài liệu thiết kế, tài khoản demo, mẫu Excel
└── backups/                Bản sao lưu CSDL (không commit)
```

## 4. Cài đặt lần đầu

Cần có: **Python 3.13**, **Node.js 22**, **PostgreSQL 17** (Redis không bắt buộc).

```powershell
# 1) Thư viện Python
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements-dev.txt

# 2) Cấu hình: sao chép rồi sửa DATABASE_URL và SECRET_KEY trong .env
Copy-Item .env.example .env

# 3) Tạo CSDL trống (hoặc tạo bằng pgAdmin), dựng bảng và nạp dữ liệu demo
psql -U postgres -c "CREATE DATABASE pickleball_db"
cd backend
python manage.py migrate
python manage.py seed
cd ..

# 4) Thư viện của hai ứng dụng web
cd frontend;     npm ci; cd ..
cd admin-portal; npm ci; cd ..
```

Đã có CSDL từ phiên bản trước của dự án? Xem [mục 9](#9-nâng-cấp-csdl-của-phiên-bản-cũ) - không cần tạo lại.

## 5. Chạy hệ thống

### Cách 1 - `start_all.bat` (máy phát triển)

Tệp này kiểm tra phiên bản CSDL trước. Nếu CSDL cần nâng cấp, nó hỏi xác nhận rồi mới chạy
`python manage.py migrate` (lệnh này tự sao lưu trước khi thay đổi). Sau đó mở ba cửa sổ: API (8000),
cổng người dùng (3000), cổng quản trị (3001).

### Cách 2 - chạy tay từng dịch vụ

```powershell
# Cửa sổ 1 - API
.\venv\Scripts\Activate.ps1
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Cửa sổ 2 - cổng người dùng          # Cửa sổ 3 - cổng quản trị
cd frontend; npm run dev              cd admin-portal; npm run dev
```

API từ chối khởi động nếu schema CSDL chưa ở phiên bản mới nhất và in ra lệnh cần chạy.

### Cách 3 - Docker

```powershell
# .env cần tối thiểu SECRET_KEY và POSTGRES_PASSWORD
docker compose up --build -d          # hoặc chạy start_docker.bat
docker compose logs -f backend
docker compose down
```

- Docker dùng một **CSDL riêng** trong container (PostgreSQL 17, volume `pgdata17`), không phải PostgreSQL cài trên máy.
  Cổng 5432 và 6379 không mở ra ngoài.
- Lần chạy đầu, backend tự dựng bảng và nạp dữ liệu demo (tắt bằng `SEED_DEMO_DATA=false`).
- Ảnh sân tải lên được giữ trong volume `uploads`.
- Sao lưu CSDL của container (hai bước, chạy được trên mọi loại terminal):

  ```powershell
  docker compose exec -T postgres pg_dump -U postgres -Fc -f /tmp/pm2k.dump pickleball_db
  docker compose cp postgres:/tmp/pm2k.dump backups/docker.dump
  ```

- Volume của cấu hình Docker cũ (`postgres_data`, dữ liệu PostgreSQL 15) không còn được dùng và không bị xóa.

> Cấu hình Docker đã được viết lại và rà soát, nhưng **chưa được chạy thử** trên máy phát triển (máy không cài Docker).
> Hãy chạy thử một lần trước khi dùng cho buổi demo.

Địa chỉ sau khi chạy: API và tài liệu Swagger `http://localhost:8000/docs`, người dùng `http://localhost:3000`,
quản trị `http://localhost:3001`.

## 6. Tài khoản demo

Sau `python manage.py seed`, mọi tài khoản dùng mật khẩu **`123456`** (chỉ dành cho phát triển và bảo vệ đồ án).

| Vai trò | Email | Ghi chú |
| :--- | :--- | :--- |
| Quản trị viên | `admin@example.com` | Đăng nhập ở cổng 3001 |
| Chủ sân | `owner_rudal@pickleball.vn` | RUDAL Pickleball & Academy (6 sân) |
| Chủ sân | `owner_djoy_thuthiem@pickleball.vn` | D-Joy Pickleball Thủ Thiêm (11 sân) |
| Chủ sân | `owner_152nguyenoanh@pickleball.vn` | Pickleball 152 Nguyễn Oanh (4 sân) |
| Nhân viên | `staff_rudal_1@pickleball.vn` | Mỗi cụm sân có 3 nhân viên |
| Người chơi | `player@example.com`, `player01@gmail.com` … `player18@gmail.com` | 20 người chơi với trình độ, phong cách, mục đích chơi khác nhau |

Danh sách đầy đủ 33 tài khoản: [docs/DANH_SACH_TAI_KHOAN_TEST.md](docs/DANH_SACH_TAI_KHOAN_TEST.md).

## 7. Thanh toán khi demo

- Đặt `SEPAY_SIMULATOR_ENABLED=true` trong `.env` rồi khởi động lại API: hộp thoại thanh toán hiện nút
  **giả lập chuyển khoản**, đơn được xác nhận qua đúng luồng xử lý của webhook thật.
- Dùng SePay thật: khai báo `SEPAY_BANK_*`, `SEPAY_WEBHOOK_API_KEY` và trỏ webhook của SePay tới
  `POST /api/v1/payments/sepay-webhook` (header `Authorization: Apikey <khóa>`). Đã đặt khóa thì yêu cầu sai khóa
  bị từ chối; khi `ENVIRONMENT=production` mà chưa đặt khóa, webhook ngừng nhận yêu cầu.
- SePay phải gọi được vào máy đang chạy API. Trên máy cá nhân: chạy `start_all.bat` rồi `start_sepay_tunnel.bat`
  (cần cài `cloudflared`). Lệnh mở một đường hầm Cloudflare và in ra địa chỉ webhook để dán vào SePay. **Mỗi lần mở
  lại, địa chỉ đổi** và địa chỉ cũ ngừng hoạt động: phải dán địa chỉ mới vào SePay, nếu không SePay báo
  "Lỗi kết nối" và đơn không tự xác nhận. Giao dịch bị lỗi có thể bấm "Gửi lại" trên SePay; nếu đơn đã quá 15 phút
  nhưng khung giờ còn trống thì đơn được khôi phục và xác nhận, ngược lại hệ thống tạo yêu cầu hoàn tiền.
- SePay chỉ coi webhook là thành công khi nhận HTTP 200/201 kèm `"success": true` trong 30 giây, nên API trả
  `success: true` cho mọi lần gọi đã tiếp nhận (kết quả xử lý nằm ở `status` và `outcome`).
- `SEPAY_UNIFIED_TEST_MODE=true`: mọi cụm sân nhận tiền vào một tài khoản chung khai báo trong `.env`;
  `false`: mỗi cụm sân dùng tài khoản của chủ sân.

## 8. Lệnh quản trị và kiểm thử

Chạy trong `backend/` với môi trường ảo đã kích hoạt:

| Lệnh | Việc làm |
| :--- | :--- |
| `python manage.py migrate` | Sao lưu rồi nâng schema lên bản mới nhất (`--check` chỉ xem trạng thái, `--no-backup` bỏ sao lưu) |
| `python manage.py show` | Báo cáo tổng quan dữ liệu (chỉ đọc) |
| `python manage.py seed` | Nạp dữ liệu demo vào CSDL trống (`--reset` xóa rồi nạp lại, có hỏi xác nhận; `--feedback` chỉ nạp phiếu ghép cặp mô phỏng cho mô hình; `--matches` nạp thêm người chơi và phòng đấu mẫu để thử ghép trận, dùng được trên CSDL đang có dữ liệu) |
| `python manage.py reset` | Xóa sạch, chỉ giữ danh mục tiện ích và một tài khoản quản trị (có hỏi xác nhận) |
| `python manage.py import-excel --file x.xlsx` | Nhập cụm sân từ Excel theo mẫu trong `docs/` (`--dry-run` để kiểm tra trước) |
| `python manage.py backup` | Sao lưu CSDL vào `backups/` |
| `python manage.py train-model` | Huấn luyện mô hình ghép cặp từ bảng `pair_feedback` (`--report` chỉ in bảng đánh giá) |
| `python manage.py test` | Chạy bộ kiểm thử |

**Kiểm thử backend** - hơn 300 ca kiểm thử chạy trên CSDL riêng `pickleball_test` (tự tạo, không đụng CSDL đang dùng):

```powershell
python -m pytest                                  # từ thư mục gốc, khoảng 2-3 phút
python -m pytest backend/tests/test_payments.py -q
```

**Kiểm thử đầu-cuối qua trình duyệt** - 22 bước cho cả bốn vai trò. Script tạo và hủy đơn nên chỉ chạy trên
CSDL demo, với `SEPAY_SIMULATOR_ENABLED=true` và hai ứng dụng web đã build (`npm run build && npm start`):

```powershell
npm install -g puppeteer        # một lần
node scripts/e2e_smoke.js       # thêm --show để xem trình duyệt
```

**Kiểm tra tự động (CI)** - `.github/workflows/ci.yml` chạy ruff, pytest và build hai ứng dụng web mỗi lần đẩy mã.

## 9. Nâng cấp CSDL của phiên bản cũ

CSDL tạo bởi các phiên bản trước (chưa dùng Alembic) được nâng cấp tại chỗ, **giữ nguyên dữ liệu**:

```powershell
cd backend
python manage.py migrate --check     # chỉ xem: CSDL đang ở đâu, cần lên phiên bản nào
python manage.py migrate             # sao lưu vào backups/ rồi nâng cấp
```

Lệnh in sẵn câu lệnh khôi phục. Muốn quay lại dữ liệu cũ: khôi phục bản sao lưu vào một CSDL **mới** rồi đổi
`DATABASE_URL` sang CSDL đó (lệnh khôi phục không bao giờ ghi đè CSDL đang dùng):

```powershell
python scripts/backup_db.py --restore-into pickleball_khoi_phuc --file ..\backups\<ten_file>.dump
```

Sau khi nâng cấp:

- Các tài khoản demo cũ chưa có mục đích chơi; bổ sung giá trị mẫu bằng `python manage.py seed --preferences` (không đổi
  dữ liệu khác).
- Từ revision 0005, mô hình ghép cặp chỉ còn 4 đặc trưng (đã bỏ giờ rảnh). Bước nâng cấp này xóa các phiếu ghép cặp mô
  phỏng cũ và giữ nguyên câu trả lời khảo sát thật; nạp bộ phiếu mô phỏng mới bằng `python manage.py seed --feedback`.
- Từ revision 0006, hồ sơ người chơi không còn lưu tiện ích ưa thích và ngân sách (hai cột này vốn không còn ô nhập).

## 10. Giới hạn đã biết

- API chạy **một tiến trình**: kênh WebSocket và tác vụ nền (hết hạn đơn chờ cọc, hoàn tất đơn) nằm trong tiến trình đó.
  Không có Redis thì giữ chỗ tạm và giới hạn đăng nhập cũng chỉ nằm trong bộ nhớ tiến trình.
- Số tiền lưu bằng kiểu số thực (`FLOAT`); mọi giá trị trong hệ thống là số nguyên VNĐ.
- Quét QR bằng camera cần trình duyệt hỗ trợ `BarcodeDetector` và trang chạy trên HTTPS hoặc `localhost`;
  các trường hợp khác nhân viên nhập mã đơn bằng tay.
- Mô hình ghép cặp đang được huấn luyện trên **3.000 phiếu ghép cặp mô phỏng** lưu trong bảng `pair_feedback`
  (nạp bằng `python manage.py seed --feedback`), không phải khảo sát người chơi thật. Khi khảo sát trong ứng dụng
  (`/survey`) thu đủ 300 nhãn thật, lệnh `python manage.py train-model` tự chuyển sang huấn luyện bằng nhãn thật.
  Xem phần đánh giá trong `docs/HUONG_DAN_KLTN.md`.
- Tài liệu Swagger (`/docs`) đang mở công khai; nên tắt hoặc chặn khi triển khai thật.

## 11. Tài liệu khác

- [backend/README.md](backend/README.md) - cấu trúc backend, biến cấu hình, nhóm API, quy tắc nghiệp vụ
- [backend/scripts/README.md](backend/scripts/README.md) - script quản trị, sao lưu, nhập Excel
- [backend/tests/README.md](backend/tests/README.md) - cách tổ chức bộ kiểm thử
- [docs/DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) - thiết kế CSDL và các ràng buộc
- [docs/HUONG_DAN_KLTN.md](docs/HUONG_DAN_KLTN.md) - nghiệp vụ đặt sân, mô hình ghép cặp và cách đề xuất phòng đấu
