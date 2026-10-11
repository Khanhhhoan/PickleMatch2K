# Script quản trị backend

Chạy trong thư mục `backend/` với môi trường ảo đã kích hoạt. Mọi script dùng CSDL khai báo ở `DATABASE_URL`
trong file `.env`; schema luôn được tạo/cập nhật bằng migration Alembic.

| Lệnh | Việc làm | Có xóa dữ liệu? |
| :--- | :--- | :---: |
| `python manage.py migrate` | Sao lưu rồi đưa schema lên phiên bản mới nhất (`alembic upgrade head`) | Không |
| `python manage.py migrate --check` | Chỉ báo CSDL đang ở phiên bản nào (mã thoát 3 nếu cần nâng cấp) | Không (chỉ đọc) |
| `python manage.py show` | Báo cáo tổng quan dữ liệu | Không (chỉ đọc) |
| `python manage.py seed` | Nạp bộ dữ liệu demo vào CSDL **trống** | Không |
| `python manage.py seed --if-empty` | Như trên, nhưng bỏ qua nếu đã có dữ liệu (dùng cho Docker) | Không |
| `python manage.py seed --feedback` | Chỉ nạp 3.000 phiếu ghép cặp **mô phỏng** vào bảng `pair_feedback` (nguồn `simulated`) để huấn luyện mô hình từ CSDL; bỏ qua nếu đã có | Không |
| `python manage.py seed --preferences` | Chỉ bổ sung sở thích mẫu (mục đích chơi, khung rảnh…) cho tài khoản demo đang để trống | Không |
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

- 8 tiện ích, 3 cụm sân, 33 tài khoản đúng theo `docs/DANH_SACH_TAI_KHOAN_TEST.md`, mật khẩu chung `123456`
  (chỉ dành cho môi trường phát triển/bảo vệ đồ án).
- Đơn đặt sân, giao dịch, hủy/hoàn tiền, phòng đấu và đánh giá mẫu được tạo bằng chính các hàm nghiệp vụ của
  ứng dụng, nên luôn thỏa các ràng buộc hiện hành (không đặt trùng, tiền đã trả khớp sổ giao dịch, chỉ người
  đã chơi xong mới có đánh giá). Ngày tháng tính tương đối theo ngày chạy script.
- Tài khoản nhận tiền của chủ sân lấy từ biến `SEPAY_BANK_*` trong `.env`; mã nguồn không chứa số tài khoản nào.
- 3.000 phiếu ghép cặp mô phỏng (mỗi người chơi demo 150 phiếu) làm dữ liệu huấn luyện cho mô hình. Các phiếu mang
  nguồn `simulated`, tách biệt với câu trả lời khảo sát thật (nguồn `survey`); cổng quản trị hiển thị riêng hai con số.
  Muốn sinh lại: `DELETE FROM pair_feedback WHERE source = 'simulated';` rồi chạy lại `python manage.py seed --feedback`.

## Sao lưu và khôi phục (`scripts/backup_db.py`)

```bash
python scripts/backup_db.py                                             # tạo backups/<csdl>_<thời gian>.dump
python scripts/backup_db.py --restore-into <csdl_moi> --file <file.dump>  # khôi phục vào một CSDL MỚI
```

Lệnh khôi phục không bao giờ ghi đè CSDL đang cấu hình, và từ chối ghi đè một CSDL đã tồn tại trừ khi thêm
`--overwrite`. Để quay lại dữ liệu cũ: khôi phục vào CSDL mới rồi đổi `DATABASE_URL` trong `.env` sang CSDL đó.

## Nhập Excel (`scripts/import_excel.py`)

Dùng mẫu `docs/Mau_Nhap_Du_Lieu_Pickleball.xlsx`. Dòng thiếu ô bắt buộc (tên, địa chỉ, sân con, email chủ sân,
giá thường, giờ mở/đóng cửa) bị bỏ qua và được báo lại; script không tự điền dữ liệu thay thế. Tài khoản chủ sân
mới nhận mật khẩu ngẫu nhiên, in ra một lần khi chạy xong.
