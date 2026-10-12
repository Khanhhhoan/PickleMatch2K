# Danh sách tài khoản test

Các tài khoản dưới đây được tạo bởi lệnh `python manage.py seed` (file `backend/scripts/seed.py`).

- Mật khẩu dùng chung cho tất cả tài khoản: **`123456`** (chỉ dành cho phát triển và bảo vệ đồ án)
- Cổng người dùng, chủ sân, nhân viên: `http://localhost:3000`
- Cổng quản trị viên (Admin): `http://localhost:3001`

## Tổng quan

| Nhóm Tài Khoản | Số Lượng | Vai Trò | Cổng Truy Cập |
| :--- | :---: | :---: | :--- |
| Quản Trị Viên (Admin) | 1 | ADMIN | `http://localhost:3001` |
| Chủ Cụm Sân (Owners) | 3 | OWNER | `http://localhost:3000/owner` |
| Nhân Viên Ca Trực (Staff) | 9 | STAFF | `http://localhost:3000/staff` |
| Người Chơi / VĐV (Players) | 20 | PLAYER | `http://localhost:3000` |
| TỔNG CỘNG | 33 | | |

## 1. Tài khoản quản trị viên (Admin)

| Email | Vai Trò | Cổng Truy Cập |
| :--- | :---: | :--- |
| `admin@example.com` | ADMIN | `http://localhost:3001` |

## 2. Danh sách chủ sân (Owners)

| STT | Email | Họ Tên Chủ Sân | Cụm Sân Quản Lý | Số Sân | Địa Chỉ Cụm Sân |
| :---: | :--- | :--- | :--- | :---: | :--- |
| 1 | `owner_rudal@pickleball.vn` | Nguyễn Rudal (Chủ Sân) | RUDAL Pickleball & Academy | 6 | 28 Đường số 12, Khu phố 3, phường An Khánh, TP. Hồ Chí Minh |
| 2 | `owner_djoy_thuthiem@pickleball.vn` | Đặng D-Joy (Chủ Sân) | D-Joy Pickleball Thủ Thiêm | 11 | Công viên bờ sông Sài Gòn (khu vực cầu Ba Son), phường An Khánh, TP. Hồ Chí Minh |
| 3 | `owner_152nguyenoanh@pickleball.vn` | Chị Vân Anh (Chủ Sân) | Pickleball 152 Nguyễn Oanh | 4 | 152 Nguyễn Oanh, Phường 17, Quận Gò Vấp, TP. Hồ Chí Minh |

## 3. Danh sách nhân viên ca trực (Staff)

Nhân viên chỉ thấy và thao tác trên đơn của cụm sân mình được phân công.

| STT | Email | Họ Tên Nhân Viên | Cụm Sân Trực |
| :---: | :--- | :--- | :--- |
| 1 | `staff_rudal_1@pickleball.vn` | Lê Quốc Hưng (NV Rudal) | RUDAL Pickleball & Academy |
| 2 | `staff_rudal_2@pickleball.vn` | Phạm Hoài Nam (NV Rudal) | RUDAL Pickleball & Academy |
| 3 | `staff_rudal_3@pickleball.vn` | Đỗ Minh Tuấn (NV Rudal) | RUDAL Pickleball & Academy |
| 4 | `staff_djoy_1@pickleball.vn` | Trần Bảo Long (NV D-Joy) | D-Joy Pickleball Thủ Thiêm |
| 5 | `staff_djoy_2@pickleball.vn` | Vũ Đình Trọng (NV D-Joy) | D-Joy Pickleball Thủ Thiêm |
| 6 | `staff_djoy_3@pickleball.vn` | Ngô Thế Vinh (NV D-Joy) | D-Joy Pickleball Thủ Thiêm |
| 7 | `staff_152no_1@pickleball.vn` | Nguyễn Thanh Bình (NV 152 NO) | Pickleball 152 Nguyễn Oanh |
| 8 | `staff_152no_2@pickleball.vn` | Hoàng Hải Đăng (NV 152 NO) | Pickleball 152 Nguyễn Oanh |
| 9 | `staff_152no_3@pickleball.vn` | Bùi Quang Khải (NV 152 NO) | Pickleball 152 Nguyễn Oanh |

## 4. Danh sách người chơi / vận động viên (Players)

Mỗi người chơi có sẵn trình độ, lối đánh, mục đích chơi và vị trí, nên dùng được ngay cho
chức năng gợi ý sân và ghép cặp.

| STT | Email | Họ Tên | DUPR | Phong Cách Đánh | Mục Đích Chơi |
| :---: | :--- | :--- | :---: | :--- | :--- |
| 1 | `khanhhoan121209@gmail.com` | Nguyễn Hoàng Khánh | 3.5 | Dinking & Kiểm soát | Giao lưu |
| 2 | `player@example.com` | Trần Minh Nam | 3.5 | Toàn diện (All-Round) | Giao lưu |
| 3 | `player01@gmail.com` | Lê Hoàng Long | 3.0 | Dinking & Kiểm soát | Luyện tập |
| 4 | `player02@gmail.com` | Phạm Minh Tuấn | 4.0 | Tấn công (Offensive) | Thi đấu |
| 5 | `player03@gmail.com` | Vũ Đức Cường | 4.5 | Giao bóng & Bắt lưới | Thi đấu |
| 6 | `player04@gmail.com` | Hoàng Gia Huy | 2.5 | Phòng thủ (Defensive) | Giao lưu |
| 7 | `player05@gmail.com` | Đỗ Bảo Nam | 3.5 | Tấn công (Offensive) | Giao lưu |
| 8 | `player06@gmail.com` | Bùi Phương Thảo | 3.0 | Toàn diện (All-Round) | Giao lưu |
| 9 | `player07@gmail.com` | Ngô Quang Hải | 4.0 | Giao bóng & Bắt lưới | Thi đấu |
| 10 | `player08@gmail.com` | Trịnh Thu Hà | 2.0 | Phòng thủ (Defensive) | Luyện tập |
| 11 | `player09@gmail.com` | Dương Tiến Đạt | 3.5 | Dinking & Kiểm soát | Luyện tập |
| 12 | `player10@gmail.com` | Mai Tuấn Kiên | 5.0 | Tấn công (Offensive) | Thi đấu |
| 13 | `player11@gmail.com` | Đặng Thùy Linh | 3.0 | Toàn diện (All-Round) | Giao lưu |
| 14 | `player12@gmail.com` | Phan Đình Trọng | 3.5 | Tấn công (Offensive) | Giao lưu |
| 15 | `player13@gmail.com` | Lâm Thảo My | 2.5 | Phòng thủ (Defensive) | Luyện tập |
| 16 | `player14@gmail.com` | Huỳnh Tấn Tài | 4.0 | Giao bóng & Bắt lưới | Thi đấu |
| 17 | `player15@gmail.com` | Cao Minh Trí | 3.5 | Dinking & Kiểm soát | Luyện tập |
| 18 | `player16@gmail.com` | Đoàn Ngọc Ánh | 3.0 | Toàn diện (All-Round) | Giao lưu |
| 19 | `player17@gmail.com` | Lương Gia Bảo | 4.5 | Tấn công (Offensive) | Thi đấu |
| 20 | `player18@gmail.com` | Hà Quốc Việt | 3.5 | Toàn diện (All-Round) | Giao lưu |

## 5. Tài khoản mẫu để thử ghép trận (nạp thêm)

Lệnh `python manage.py seed --matches` nạp **thêm** 12 người chơi dưới đây (hồ sơ đầy đủ, cùng mật khẩu `123456`) và
10 phòng đấu của họ trong 6 ngày tới. Lệnh dùng được trên CSDL đang có dữ liệu, không sửa tài khoản có sẵn, và chạy
lại được khi các phòng cũ đã qua ngày.

| STT | Email | Họ Tên | DUPR | Phong Cách Đánh | Mục Đích Chơi |
| :---: | :--- | :--- | :---: | :--- | :--- |
| 1 | `ghep01@example.com` | Trần Quốc Bảo | 3.5 | Toàn diện (All-Round) | Giao lưu |
| 2 | `ghep02@example.com` | Nguyễn Thị Mai Anh | 3.5 | Dinking & Kiểm soát | Giao lưu |
| 3 | `ghep03@example.com` | Lê Minh Khôi | 4.0 | Tấn công (Offensive) | Thi đấu |
| 4 | `ghep04@example.com` | Phạm Gia Hân | 3.0 | Phòng thủ (Defensive) | Luyện tập |
| 5 | `ghep05@example.com` | Võ Thành Đạt | 4.5 | Giao bóng & Bắt lưới | Thi đấu |
| 6 | `ghep06@example.com` | Đinh Ngọc Lan | 2.5 | Phòng thủ (Defensive) | Giao lưu |
| 7 | `ghep07@example.com` | Bùi Anh Tuấn | 3.0 | Toàn diện (All-Round) | Giao lưu |
| 8 | `ghep08@example.com` | Hồ Thanh Tùng | 4.0 | Giao bóng & Bắt lưới | Thi đấu |
| 9 | `ghep09@example.com` | Trương Mỹ Duyên | 3.5 | Tấn công (Offensive) | Luyện tập |
| 10 | `ghep10@example.com` | Lý Hoàng Phúc | 5.0 | Tấn công (Offensive) | Thi đấu |
| 11 | `ghep11@example.com` | Đặng Khánh Vy | 3.0 | Dinking & Kiểm soát | Giao lưu |
| 12 | `ghep12@example.com` | Châu Nhật Minh | 4.5 | Tấn công (Offensive) | Thi đấu |

Các phòng mẫu (ngày tính từ hôm chạy lệnh; giờ có thể lệch 30 phút theo lưới giờ của từng cụm sân):

| Ngày | Giờ | Cụm sân | Chủ phòng | Thành viên | Dùng để thử |
| :---: | :---: | :--- | :--- | :---: | :--- |
| +1 | 18:00 - 20:00 | Cụm sân 1 | `ghep01` (3.5) | 2/4 | Tham gia phòng cùng trình |
| +1 | 19:00 - 20:00 | Cụm sân 2 | `ghep03` (4.0) | 3/4 | Còn 1 chỗ; trùng giờ với phòng trên |
| +2 | 06:00 - 07:00 | Cụm sân 2 | `ghep09` (3.5) | 1/2 | Phòng 2 người: vào là đủ |
| +2 | 20:00 - 22:00 | Cụm sân 1 | `ghep05` (4.5) | 2/4 | Trình cao |
| +2 | 20:00 - 21:00 | Cụm sân 3 | `ghep10` (5.0) | 1/2 | Trình rất cao, đánh đơn |
| +3 | 17:00 - 19:00 | Cụm sân 3 | `ghep04` (3.0) | 3/4 | Còn 1 chỗ |
| +3 | 19:00 - 21:00 | Cụm sân 2 | `ghep02` (3.5) | 3/6 | Phòng xoay vòng 6 người |
| +4 | 07:00 - 08:00 | Cụm sân 1 | `ghep06` (2.5) | 1/4 | Người mới chơi |
| +5 | 08:00 - 10:00 | Cụm sân 2 | `ghep08` (4.0) | 4/4 | Đã đủ người: không hiện với người ngoài |
| +6 | 18:00 - 20:00 | Cụm sân 3 | `ghep09` (3.5) | 1/4 | Phòng mới mở |

Mỗi phòng gắn với một đơn đã cọc của chủ phòng. Khoản cọc ghi vào sổ giao dịch với nhãn "Dữ liệu mẫu" (mã tham
chiếu `DEMO-PK2K…`). Qua giờ chơi mà không ai check-in thì đơn chuyển "Không đến sân" và phòng tự đóng, như mọi đơn khác.

## 6. Tài khoản của cụm sân nhập thêm

Cụm sân thêm vào sau (ví dụ bằng `python manage.py import-excel`) chưa có nhân viên hay đơn đặt nào. Lệnh
`python manage.py seed --activity` (thêm `--venue ID` để chỉ nạp một cụm sân) tạo cho cụm sân đó hai tài khoản nhân
viên và một bộ đơn đặt sân, giao dịch, phòng đấu, đánh giá mẫu của các người chơi ở mục 4. Lệnh không sửa dữ liệu đã
có và bỏ qua cụm sân đã có đơn.

| Tài khoản | Email | Ghi chú |
| :--- | :--- | :--- |
| Chủ sân | `owner_<tên>@pickleball.vn` | Tạo lúc nhập cụm sân; ví dụ `owner_club88@pickleball.vn` |
| Nhân viên 1 | `staff_<tên>_1@pickleball.vn` | Tạo bởi `seed --activity`, mật khẩu `123456`; ví dụ `staff_club88_1@pickleball.vn` |
| Nhân viên 2 | `staff_<tên>_2@pickleball.vn` | Như trên |

Tiền cọc chuyển khoản của các đơn mẫu này mang nhãn "Dữ liệu mẫu" (mã tham chiếu `DEMO-PK2K…`); các dòng thu tại
quầy và hoàn tiền có ghi chú "(dữ liệu mẫu)".

## Ghi chú

- Bộ dữ liệu demo còn có sẵn đơn đặt sân ở nhiều trạng thái, giao dịch, phòng đấu và đánh giá; ngày tháng được tính
  tương đối theo ngày chạy lệnh seed.
- File `DANH_SACH_TAI_KHOAN_TEST.docx` là bản in của danh sách này; khi hai bản khác nhau thì bản `.md` này là bản đúng.
