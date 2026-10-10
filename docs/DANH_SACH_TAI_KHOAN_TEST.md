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

Mỗi người chơi có sẵn vị trí, khung rảnh trong tuần, tiện ích ưa thích và ngân sách, nên dùng được ngay cho
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

## Ghi chú

- Bộ dữ liệu demo còn có sẵn đơn đặt sân ở nhiều trạng thái, giao dịch, phòng đấu và đánh giá; ngày tháng được tính
  tương đối theo ngày chạy lệnh seed.
- File `DANH_SACH_TAI_KHOAN_TEST.docx` là bản in của danh sách này; khi hai bản khác nhau thì bản `.md` này là bản đúng.
