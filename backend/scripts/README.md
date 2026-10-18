# Script quản trị backend

Chạy trong thư mục `backend/` với môi trường ảo đã kích hoạt. Mọi script dùng CSDL khai báo ở `DATABASE_URL`
trong file `.env`; schema luôn được tạo/cập nhật bằng migration Alembic.

| Lệnh | Việc làm | Có xóa dữ liệu? |
| :--- | :--- | :---: |
| `python manage.py migrate` | Sao lưu rồi đưa schema lên phiên bản mới nhất (`alembic upgrade head`) | Không |
| `python manage.py migrate --check` | Chỉ báo CSDL đang ở phiên bản nào (mã thoát 3 nếu cần nâng cấp) | Không (chỉ đọc) |
| `python manage.py show` | Báo cáo tổng quan dữ liệu | Không (chỉ đọc) |
| `python manage.py seed` | Nạp bộ dữ liệu demo vào CSDL **trống** | Không |
| `python manage.py seed --if-empty` | Như trên, nhưng bỏ qua nếu đã có dữ liệu (dùng trong script tự động) | Không |
| `python manage.py seed --feedback` | Chỉ nạp 10.000 phiếu ghép cặp **mô phỏng** vào bảng `pair_feedback` (nguồn `simulated`) để huấn luyện mô hình từ CSDL; bỏ qua nếu đã có | Không |
| `python manage.py seed --feedback --regenerate` | Thay các phiếu mô phỏng bằng bộ sinh theo quy tắc hiện tại (dùng sau khi đổi quy tắc sinh nhãn); câu trả lời khảo sát thật được giữ nguyên | Chỉ phiếu mô phỏng |
| `python manage.py seed --preferences` | Chỉ bổ sung mục đích chơi và ngày sinh mẫu cho tài khoản demo đang để trống (kể cả các tài khoản `ghepNN`) | Không |
| `python manage.py seed --matches` | Nạp **thêm** 12 người chơi mẫu và 10 phòng đấu cho 6 ngày tới để thử chức năng ghép trận; chạy lại được, không sửa dữ liệu đã có | Không |
| `python manage.py seed --activity` | Nạp **thêm** hoạt động mẫu (nhân viên, đơn đặt, giao dịch, phòng đấu, đánh giá) cho cụm sân mới chưa có đơn nào; `--venue ID` để chỉ nạp một cụm sân; không sửa dữ liệu đã có | Không |
| `python manage.py seed --reset` | Xóa toàn bộ rồi nạp lại dữ liệu demo | **Có** |
| `python manage.py reset` | Xóa toàn bộ, chỉ giữ danh mục tiện ích và một tài khoản Admin | **Có** |
| `python manage.py import-excel --file x.xlsx` | Nhập thêm cụm sân từ Excel (thêm `--dry-run` để kiểm tra trước) | Không |
| `python manage.py backup` | Sao lưu CSDL vào `backups/` (pg_dump) | Không |
| `python manage.py train-model` | Huấn luyện mô hình ghép cặp từ bảng `pair_feedback`, ghi `match_rf_model.pkl` + `model_meta.json` | Không |
| `python manage.py test` | Chạy bộ kiểm thử trên CSDL riêng `pickleball_test` | Không (CSDL test) |

Các lệnh có xóa dữ liệu bắt gõ lại tên CSDL để xác nhận; thêm `--yes` để bỏ qua bước hỏi (ví dụ trong CI).
Trước khi chạy chúng trên CSDL đang dùng, hãy sao lưu: `python manage.py backup`.

## Nâng cấp schema (`manage.py migrate`)

- CSDL đang có dữ liệu được sao lưu vào `backups/` trước khi thay đổi. Sao lưu thất bại (ví dụ máy không có
  `pg_dump`) thì lệnh dừng và chưa thay đổi gì; thêm `--no-backup` nếu bạn đã tự sao lưu.
- CSDL tạo từ trước khi dự án dùng Alembic (có bảng, chưa có `alembic_version`) được đánh dấu ở revision `0001`
  rồi mới nâng cấp, nên dữ liệu cũ được giữ.
- CSDL ở revision mà mã nguồn không có (mã nguồn cũ hơn CSDL) không bị đụng tới: lệnh báo cần cập nhật mã nguồn.

## Dữ liệu demo (`scripts/seed.py`)

- 8 tiện ích, 3 cụm sân, 33 tài khoản (khai báo trong `VENUES` và `PLAYERS` của `scripts/seed.py`), mật khẩu chung `123456`
  (chỉ dành cho môi trường phát triển/bảo vệ đồ án).
- Đơn đặt sân, giao dịch, hủy/hoàn tiền, phòng đấu và đánh giá mẫu được tạo bằng chính các hàm nghiệp vụ của
  ứng dụng, nên luôn thỏa các ràng buộc hiện hành (không đặt trùng, tiền đã trả khớp sổ giao dịch, chỉ người
  đã chơi xong mới có đánh giá). Ngày tháng tính tương đối theo ngày chạy script.
- Tài khoản nhận tiền của chủ sân lấy từ biến `SEPAY_BANK_*` trong `.env`; mã nguồn không chứa số tài khoản nào.
- 10.000 phiếu ghép cặp mô phỏng (mỗi người chơi demo 500 phiếu) làm dữ liệu huấn luyện cho mô hình. Các phiếu mang
  nguồn `simulated`, tách biệt với câu trả lời khảo sát thật (nguồn `survey`); cổng quản trị hiển thị riêng hai con số.
  Muốn sinh lại (ví dụ sau khi đổi quy tắc sinh nhãn): `python manage.py seed --feedback --regenerate`, rồi
  `python manage.py train-model`. Lệnh huấn luyện chỉ dùng phiếu mô phỏng cho tới khi có đủ 300 câu trả lời khảo sát thật.
- `seed --matches` dùng được trên CSDL đang có dữ liệu: tạo các tài khoản `ghep01@example.com` … `ghep12@example.com`
  (hồ sơ đầy đủ, trình độ 2.5 - 5.0) và 10 phòng đấu trong 6 ngày tới ở nhiều trạng thái (mới mở, còn 1 chỗ, đã đủ
  người, phòng 2 người, phòng 6 người, hai phòng trùng giờ). Mỗi phòng gắn với một đơn đã cọc của chủ phòng; khoản
  cọc ghi sổ với nhãn "Dữ liệu mẫu" và mã tham chiếu `DEMO-PK2K…` để phân biệt với tiền thật. Lệnh không đụng tới
  tài khoản hay đơn có sẵn. Phòng nào đã nạp thì bỏ qua, nên có thể chạy lại khi các phòng cũ đã qua ngày.
- `seed --activity` dành cho cụm sân vừa thêm vào CSDL đang dùng (ví dụ bằng `import-excel`), khi cụm sân đó chưa có
  đơn nào: tạo hai tài khoản nhân viên `staff_<tên>_1@pickleball.vn`, `staff_<tên>_2@pickleball.vn` (`<tên>` lấy từ
  email chủ sân `owner_<tên>@…`, mật khẩu `123456`) nếu cụm sân chưa có nhân viên, rồi dựng 14 đơn của các tài khoản
  người chơi demo có sẵn: 6 đơn đã chơi xong trong tuần qua (5 đơn kèm đánh giá, 1 khách vãng lai trả tiền mặt), 1 đơn
  không đến, 1 đơn hủy đã hoàn cọc, 1 đơn tối nay để thử nhận sân, 2 đơn có mở phòng đấu, 1 đơn giữ sân qua điện
  thoại, 1 đơn hủy đang chờ hoàn cọc và 1 đơn đã cọc. Tiền cọc chuyển khoản ghi sổ với nhãn "Dữ liệu mẫu" và mã
  `DEMO-PK2K…`; các dòng thu tại quầy và hoàn tiền có ghi chú "(dữ liệu mẫu)". Cả lượt nạp nằm trong một giao dịch
  CSDL: có lỗi giữa chừng thì không ghi gì. Cụm sân đã có đơn thì bỏ qua, nên chạy lại không nạp trùng.

## Sao lưu và khôi phục (`scripts/backup_db.py`)

```bash
python scripts/backup_db.py                                             # tạo backups/<csdl>_<thời gian>.dump
python scripts/backup_db.py --restore-into <csdl_moi> --file <file.dump>  # khôi phục vào một CSDL MỚI
```

Lệnh khôi phục không bao giờ ghi đè CSDL đang cấu hình, và từ chối ghi đè một CSDL đã tồn tại trừ khi thêm
`--overwrite`. Để quay lại dữ liệu cũ: khôi phục vào CSDL mới rồi đổi `DATABASE_URL` trong `.env` sang CSDL đó.

## Nhập Excel (`scripts/import_excel.py`)

`python manage.py import-excel --file duong_dan.xlsx`. File Excel có mỗi dòng một cụm sân; cột được nhận theo từ khóa
trong tên cột, không phân biệt hoa thường:

| Tên cột chứa | Nội dung | Bắt buộc |
| :--- | :--- | :---: |
| `Tên cụm` | Tên cụm sân | Có |
| `Địa chỉ` | Địa chỉ chi tiết | Có |
| `Sân con` | Tên các sân, cách nhau bằng dấu phẩy | Có |
| `Giá thường` | Giá mỗi giờ (VNĐ) | Có |
| `Cao điểm`, `Cuối tuần` | Giá giờ cao điểm, giá cuối tuần; để trống thì dùng giá thường | |
| `Mở cửa`, `Đóng cửa` | Giờ hoạt động, dạng `06:00` hoặc `5h30` | Có |
| `Email` | Email đăng nhập của chủ sân | Có |
| `Họ tên chủ`, `Điện thoại`, `Ngân hàng` | Thông tin chủ sân | |
| `Tiện ích`, `Mô tả`, `Ảnh` | Tiện ích có sẵn (cách nhau bằng dấu phẩy), mô tả, link ảnh | |
| `Maps` | Link Google Maps; toạ độ chỉ lấy được khi link có dạng `...?q=<vĩ độ>,<kinh độ>` | |

Dòng thiếu ô bắt buộc bị bỏ qua và được báo lại; script không tự điền dữ liệu thay thế. Tài khoản chủ sân mới nhận
mật khẩu ngẫu nhiên, in ra một lần khi chạy xong.

## Webhook SePay trên máy cá nhân (`scripts/sepay_tunnel.py`)

SePay chỉ báo giao dịch về được khi gọi tới được API. Trên máy cá nhân, chạy `start_sepay_tunnel.bat` ở thư mục gốc
(hoặc `python scripts/sepay_tunnel.py` trong `backend/`) sau khi API đã chạy: lệnh mở một đường hầm Cloudflare tới
cổng 8000, in ra và chép sẵn địa chỉ webhook, rồi tự kiểm tra địa chỉ đó. Cần cài `cloudflared`.

- Địa chỉ `https://….trycloudflare.com` **đổi sau mỗi lần chạy** và chỉ sống khi cửa sổ lệnh còn mở. Mỗi lần mở lại
  phải dán địa chỉ mới vào webhook trên SePay; để địa chỉ cũ thì SePay báo "Lỗi kết nối".
- Giao dịch SePay báo lỗi có thể bấm "Gửi lại" sau khi đã cập nhật địa chỉ.
- Nên đặt `SEPAY_WEBHOOK_API_KEY` trong `.env` và chọn chứng thực API Key trên SePay, vì địa chỉ đường hầm là công khai.
