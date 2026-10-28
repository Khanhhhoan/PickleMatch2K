# PickleMatch2K - Hệ thống đặt sân và ghép trận Pickleball

> **Khóa luận tốt nghiệp** - Đề tài: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

## 1. Tổng quan

PickleMatch2K gồm một API và hai ứng dụng web phục vụ bốn vai trò:

| Vai trò | Cổng | Việc chính |
| :--- | :--- | :--- |
| **Người chơi** | `http://localhost:3000` | Tìm sân theo vị trí, xem lịch trống theo thời gian thực, đặt sân và cọc 50% qua VietQR, nhận vé QR, hủy/hoàn tiền theo chính sách, mở phòng đấu trên đơn đã cọc, tham gia các phòng đấu do mô hình đề xuất |
| **Chủ sân** | `http://localhost:3000/owner` | Thông tin cụm sân, sân con, bảng giá theo khung giờ, giờ mở cửa, nhân viên, quầy đặt sân, doanh thu, kết ca |
| **Nhân viên** | `http://localhost:3000/staff` | Quầy đặt sân của cụm sân được phân công: tạo đơn tại quầy, tra mã/quét QR, check-in, thu tiền, dời lịch, xác nhận hoàn tiền, kết ca và đối chiếu tiền mặt |
| **Quản trị viên** | `http://localhost:3001` | Duyệt cụm sân, quản lý tài khoản, giám sát đơn đặt, giao dịch và phòng đấu, xem thống kê doanh thu và đơn đặt theo ngày/tháng/năm |

Hai trọng tâm của hệ thống:

- **Quy trình đặt sân**: giữ chỗ → đặt → cọc 50% qua VietQR → vé QR → check-in → thu phần còn lại, kèm hủy và hoàn tiền
  theo chính sách.
- **Ghép trận bằng Random Forest**: mô hình ước lượng độ phù hợp giữa người chơi và từng phòng đấu đã mở, rồi đề xuất
  những phòng có độ phù hợp cao (từ 70%).

Gợi ý cụm sân chấm thang 100 điểm (`GET /api/v1/recommendations/venues`: gần 40, giá thuê 35, giờ còn trống 25) và
được dùng để xếp sẵn danh sách cụm sân trên trang chủ khi người chơi đã đăng nhập (kèm nhãn Top 1, Top 2…); khách
chưa đăng nhập thấy danh sách xếp từ gần đến xa.

Mô hình ghép trận dùng 5 đặc trưng của một cặp người chơi: chênh lệch trình độ, khoảng cách tới sân, cùng mục đích
chơi, hợp phong cách và chênh lệch tuổi. Đặc trưng nằm ở `backend/app/ml/features.py`, quy tắc sinh phiếu mô phỏng và
cấu hình rừng ở `backend/app/ml/train_model.py`, kết quả đánh giá ở `backend/app/ml/model_meta.json` (in lại bằng
`python manage.py train-model --report`).

## 2. Công nghệ

| Thành phần | Công nghệ |
| :--- | :--- |
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Pydantic 2 |
| Cơ sở dữ liệu | PostgreSQL 17, migration bằng Alembic |
| Giữ chỗ tạm, giới hạn đăng nhập | Redis (tùy chọn; không có thì lưu trong bộ nhớ của tiến trình) |
| Thời gian thực | WebSocket của FastAPI |
| Học máy | scikit-learn (Random Forest), pandas, numpy |
| Xác thực | JWT, mật khẩu băm bằng bcrypt |
| Thanh toán | SePay VietQR (webhook); bộ giả lập chỉ bật khi chạy trên máy |
| Web | Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4 |

## 3. Cấu trúc thư mục

```text
KLTN/
├── .env.example            Mẫu cấu hình (sao chép thành .env, không commit .env)
├── render.yaml             Triển khai toàn bộ hệ thống lên Render (mục 5, Cách 3)
├── start_all.bat           Chạy 3 dịch vụ trên máy phát triển
├── pyproject.toml          Cấu hình pytest và ruff
├── .github/workflows/      Kiểm tra tự động (CI)
├── backend/                API FastAPI
│   ├── app/                api, core, db, ml, models, schemas, services, utils
│   ├── alembic/            Các phiên bản schema (0001 → 0013)
│   ├── scripts/            Script quản trị CSDL (xem backend/scripts/README.md)
│   ├── tests/              Bộ kiểm thử pytest (xem backend/tests/README.md)
│   └── manage.py           Bộ lệnh quản trị
├── frontend/               Cổng người chơi, chủ sân, nhân viên (cổng 3000)
├── admin-portal/           Cổng quản trị (cổng 3001)
├── scripts/e2e_smoke.js    Kiểm thử đầu-cuối qua trình duyệt
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

Địa chỉ sau khi chạy: API và tài liệu Swagger `http://localhost:8000/docs`, người dùng `http://localhost:3000`,
quản trị `http://localhost:3001`.

### Cách 3 - Đưa lên Internet bằng Render

`render.yaml` mô tả toàn bộ hệ thống trên Render: API `picklematch2k-api`, cổng người dùng `picklematch2k-web`, cổng
quản trị `picklematch2k-admin` và CSDL PostgreSQL 17 `picklematch2k-db`. Không cần máy chủ riêng, có sẵn HTTPS, và mỗi
lần push lên nhánh `main` Render tự deploy lại.

1. Render → New → Blueprint → chọn repo này, điền các biến được hỏi (khóa Cloudinary, tài khoản nhận tiền SePay) →
   Deploy Blueprint.
2. Nạp dữ liệu từ một bản sao lưu (tùy chọn): lấy External Database URL của `picklematch2k-db` rồi chạy trên máy
   (`--clean` vì API đã dựng sẵn bảng trống lúc khởi động):

   ```powershell
   pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction --exit-on-error -d "<External Database URL>" backups\<bản sao lưu>.dump
   ```

3. Mở `https://picklematch2k-web.onrender.com` (người dùng) và `https://picklematch2k-admin.onrender.com` (quản trị).

- Ba địa chỉ đi theo tên dịch vụ. Render cấp tên khác thì sửa `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_ADMIN_URL` của hai
  cổng web (rồi deploy lại) và `CORS_ORIGINS` của API.
- Gói miễn phí (theo chính sách của Render lúc viết): mỗi dịch vụ ngủ sau khoảng 15 phút không có truy cập, lần mở
  đầu tiên chờ khoảng 1 phút, tác vụ nền tạm dừng khi API ngủ (chạy bù khi thức dậy); CSDL miễn phí hết hạn sau
  30 ngày, muốn giữ lâu hơn thì nâng lên gói trả phí.
- Ổ đĩa trên Render bị xóa mỗi lần khởi động lại: ảnh dùng Cloudinary (đặt sẵn trong `render.yaml`), chứng từ hoàn
  tiền nằm trong CSDL.
- Mỗi lần khởi động, API tự nâng schema của CSDL lên bản mới nhất (`manage.py migrate --no-backup`).
- Bản trên Render nhận thanh toán thật: không có nút giả lập (`SEPAY_SIMULATOR_ENABLED=false`), đơn chỉ được xác
  nhận khi SePay báo tiền về. Cần hai việc làm tay:
  1. Render → `picklematch2k-api` → Environment: thêm `SEPAY_WEBHOOK_API_KEY` (một chuỗi ngẫu nhiên dài). Blueprint
     đã tạo rồi thì Render không tự hỏi biến bí mật mới khai trong `render.yaml`.
  2. SePay → Tích hợp WebHooks: thêm webhook "Có tiền vào" cho tài khoản nhận tiền, URL
     `https://picklematch2k-api.onrender.com/api/v1/payments/sepay-webhook`, chứng thực API Key với đúng chuỗi trên.

  Thiếu khóa thì webhook bị từ chối (503) vì API chạy ở chế độ production.

## 6. Tài khoản demo

Sau `python manage.py seed`, mọi tài khoản dùng mật khẩu **`123456`** (chỉ dành cho phát triển và bảo vệ đồ án).
Bản chạy thật trên Render không dùng mật khẩu này cho tài khoản quản trị viên, chủ sân và nhân viên.

| Vai trò | Email | Ghi chú |
| :--- | :--- | :--- |
| Quản trị viên | `admin@example.com` | Đăng nhập ở cổng 3001 |
| Chủ sân | `owner_rudal@pickleball.vn` | RUDAL Pickleball & Academy (6 sân) |
| Chủ sân | `owner_djoy_thuthiem@pickleball.vn` | D-Joy Pickleball Thủ Thiêm (11 sân) |
| Chủ sân | `owner_152nguyenoanh@pickleball.vn` | Pickleball 152 Nguyễn Oanh (4 sân) |
| Nhân viên | `staff_rudal_1@pickleball.vn` | Mỗi cụm sân có 3 nhân viên |
| Người chơi | `player@example.com`, `player01@gmail.com` … `player18@gmail.com` | 20 người chơi với trình độ, phong cách, mục đích chơi khác nhau |

Danh sách đầy đủ 33 tài khoản nằm trong `backend/scripts/seed.py` (các bảng `VENUES` và `PLAYERS`).

## 7. Thanh toán

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
| `python manage.py seed` | Nạp dữ liệu demo vào CSDL trống (`--reset` xóa rồi nạp lại, có hỏi xác nhận; `--feedback` chỉ nạp phiếu ghép cặp mô phỏng cho mô hình, thêm `--regenerate` để thay các phiếu đó bằng bộ sinh theo quy tắc hiện tại; `--matches` nạp thêm người chơi và phòng đấu mẫu để thử ghép trận, dùng được trên CSDL đang có dữ liệu; `--activity` nạp thêm nhân viên, đơn đặt, giao dịch, phòng đấu và đánh giá mẫu cho cụm sân mới chưa có đơn nào) |
| `python manage.py reset` | Xóa sạch, chỉ giữ danh mục tiện ích và một tài khoản quản trị (có hỏi xác nhận) |
| `python manage.py import-excel --file x.xlsx` | Nhập cụm sân từ file Excel; các cột cần có ghi trong `backend/scripts/README.md` (`--dry-run` để kiểm tra trước) |
| `python manage.py backup` | Sao lưu CSDL vào `backups/` |
| `python manage.py train-model` | Huấn luyện mô hình ghép cặp từ bảng `pair_feedback` (`--report` chỉ in bảng đánh giá) |
| `python manage.py test` | Chạy bộ kiểm thử |

**Kiểm thử backend** - hơn 300 ca kiểm thử chạy trên CSDL riêng `pickleball_test` (tự tạo, không đụng CSDL đang dùng):

```powershell
python -m pytest                                  # từ thư mục gốc, khoảng 2-3 phút
python -m pytest backend/tests/test_payments.py -q
```

**Kiểm thử đầu-cuối qua trình duyệt** - 27 bước cho cả bốn vai trò. Script tạo và hủy đơn nên chỉ chạy trên
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
- Từ revision 0007, mô hình ghép cặp có thêm tiêu chí thứ năm là chênh lệch tuổi. Bước nâng cấp này xóa các phiếu ghép
  cặp mô phỏng cũ và giữ nguyên câu trả lời khảo sát thật (các câu cũ không có chênh lệch tuổi nên không được tính).
  Sau khi nâng cấp: nạp bộ 10.000 phiếu mô phỏng mới bằng `python manage.py seed --feedback`, và bổ sung ngày sinh mẫu
  cho các tài khoản demo đang để trống bằng `python manage.py seed --preferences`.
- Từ revision 0008 có thêm bảng `shift_closings` (sổ kết ca tại quầy). Bước nâng cấp này chỉ thêm bảng mới, không
  đổi dữ liệu đang có.
- Từ revision 0009: xác nhận hoàn tiền bắt buộc có mã giao dịch ngân hàng (kèm chứng từ tùy chọn, lưu riêng; từ 0013
  nằm trong CSDL), đơn tại quầy chưa thu tiền tự hủy trước giờ chơi (mặc định 30 phút, chủ sân chỉnh trong
  "Giờ hoạt động"). Bước nâng cấp chỉ thêm cột; đơn tạo trước đó không bị tự hủy. Quay lại bản trước:
  `alembic downgrade 0008` (bỏ các cột mới) hoặc khôi phục bản sao lưu mà `manage.py migrate` tạo trước khi nâng cấp.
- Từ revision 0010, một ca kết ca không còn gắn với ngày lịch: mỗi giao dịch được gắn vào đúng lần kết ca đã tính nó
  (ca 20:00 - 00:15 hôm sau là một ca, khoản ghi sổ muộn thuộc lần kết ca sau). Các lần kết ca cũ được gắn đúng
  những giao dịch chúng đã cộng; số tiền đã lưu không đổi.
- Từ revision 0011, 13 cột tiền lưu bằng số nguyên `BIGINT` thay cho số thực. Migration kiểm tra trước và dừng hẳn
  nếu có số tiền lẻ hoặc bất thường (không làm tròn ngầm); tổng từng cột giữ nguyên. Quay lại: `alembic downgrade 0010`.
- Từ revision 0012 có bảng `notifications` (thông báo trong ứng dụng, ví dụ phòng đấu bị hủy). Chỉ thêm bảng mới.
- Từ revision 0013, nội dung chứng từ hoàn tiền nằm trong bảng `refund_proofs` thay vì thư mục
  `backend/private_uploads/` (máy chủ kiểu Render xóa ổ đĩa khi khởi động lại). Tệp đang có trên ổ đĩa được chép vào
  bảng, tệp gốc giữ nguyên. Quay lại: `alembic downgrade 0012` (nội dung được ghi lại ra thư mục cũ).
- Phiếu ghép cặp mô phỏng nạp từ bản cũ được sinh với nhiễu 0,08, khiến độ phù hợp của phòng thường hiện 100%. Mô hình
  đi kèm mã nguồn đã được huấn luyện lại với nhiễu 0,15; để bảng `pair_feedback` khớp với mô hình, sinh lại các phiếu
  mô phỏng bằng `python manage.py seed --feedback --regenerate` (câu trả lời khảo sát thật được giữ nguyên).

## 10. Giới hạn đã biết

- Tác vụ nền (hết hạn đơn chờ cọc, tự hủy đơn tại quầy chưa thu, hoàn tất đơn và phòng đấu) chạy được khi API có
  nhiều tiến trình: mỗi lượt giữ một khóa tư vấn của PostgreSQL nên chỉ một tiến trình chạy, và mỗi dòng được khóa
  SKIP LOCKED nên không xử lý trùng. Kênh WebSocket thì vẫn theo từng tiến trình: chạy nhiều tiến trình cần đặt
  `REDIS_URL` để giữ chỗ tạm và giới hạn đăng nhập dùng chung (không có Redis thì chúng chỉ nằm trong bộ nhớ tiến trình).
- Thông báo chỉ có trong ứng dụng (chuông); chưa gửi email vì hệ thống chưa cấu hình dịch vụ gửi thư.
- Quét QR bằng camera cần trình duyệt hỗ trợ `BarcodeDetector` và trang chạy trên HTTPS hoặc `localhost`;
  các trường hợp khác nhân viên nhập mã đơn bằng tay.
- Mô hình ghép cặp được huấn luyện trên **10.000 phiếu ghép cặp mô phỏng** lưu trong bảng `pair_feedback`
  (nạp bằng `python manage.py seed --feedback`), không phải khảo sát người chơi thật. Thu thập câu trả lời thật qua
  trang khảo sát (`/survey`) là hướng phát triển: các câu trả lời được lưu riêng, và khi đủ 300 nhãn thật thì lệnh
  `python manage.py train-model` tự chuyển sang huấn luyện bằng nhãn thật.
- Tài liệu Swagger (`/docs`, `/redoc`, `/openapi.json`) chỉ mở khi chạy trên máy; bản `ENVIRONMENT=production` đóng lại.

## 11. Tài liệu khác

- [backend/README.md](backend/README.md) - cấu trúc backend, biến cấu hình, nhóm API, quy tắc nghiệp vụ
- [backend/scripts/README.md](backend/scripts/README.md) - script quản trị, sao lưu, nhập Excel
- [backend/tests/README.md](backend/tests/README.md) - cách tổ chức bộ kiểm thử
