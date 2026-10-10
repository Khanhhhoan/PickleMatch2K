# 🏓 PickleMatch2K - Cổng Người Chơi & Chủ Sân (Port 3000)

Ứng dụng web front-end hiện đại phục vụ 3 nhóm đối tượng: **Người chơi (Player)**, **Chủ sân (Owner)** và **Nhân viên sân (Staff)**. Xây dựng trên nền tảng **Next.js 16 (App Router)**, **React 19**, **TypeScript** và **TailwindCSS**.

---

## 🌟 Chức Năng Cốt Lõi

- **Khách hàng / Người chơi**:
  - Tìm kiếm sân thể thao theo khoảng cách GPS thực tế (Haversine).
  - Trình duyệt ảnh sân đa góc độ mượt mà với hiệu ứng hover slideshow.
  - Đặt sân theo thời gian thực (Realtime WebSocket Slot Locking chống trùng).
  - Thanh toán cọc 50% qua cổng **SePay VietQR** tự động hiển thị mã QR động.
  - Tạo kèo giao lưu và nhận gợi ý người chơi phù hợp theo DUPR qua mô hình **Random Forest AI**.
- **Chủ sân (Owner)**:
  - Cổng `/owner`: Quản lý danh sách sân, upload ảnh trực tiếp (Cloudinary / Local), cấu hình bảng giá và phân công nhân viên.
- **Nhân viên sân (Staff)**:
  - Cổng `/staff`: Giao diện di động tinh gọn để check-in mã QR của khách và thu 50% tiền còn lại tại sân.

---

## 📁 Cấu Trúc Thư Mục

```
frontend/
├── public/               # Tài nguyên ảnh và logo tĩnh
├── src/
│   ├── app/              # Next.js App Router (venues, matches, bookings, owner, staff, profile)
│   ├── components/       # Các UI Components tái sử dụng (Navbar, Footer, PlayerBottomNav...)
│   └── lib/              # Client API, Auth Context, WebSocket Hook, Geolocation
├── Dockerfile            # Container build manifest
└── package.json          # Dependencies & Scripts (Chạy trên cổng 3000)
```

---

## 🚀 Khởi Chạy Cục Bộ

```bash
npm install
npm run dev
# Mở trình duyệt tại: http://localhost:3000
```
