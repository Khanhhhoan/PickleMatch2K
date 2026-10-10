# 👑 PickleMatch2K - Cổng Quản Trị Hệ Thống (Port 3001)

Cổng điều hành và quản trị độc lập dành riêng cho **Super Admin**, xây dựng trên nền tảng **Next.js 16 (App Router)** với thiết kế Executive Dark sang trọng, tối ưu tính bảo mật và cách ly hoàn toàn với cổng người dùng thông thường.

---

## 🌟 Chức Năng Quản Trị

- **Tổng quan KPI**: Thống kê doanh thu thời gian thực, tổng số booking, tổng số người dùng và cụm sân hoạt động.
- **Quản lý Cụm Sân**: Phê duyệt hoặc từ chối các cụm sân mới đăng ký từ chủ sân.
- **Quản lý Tài Khoản (CRM)**: Xem chi tiết thông tin người dùng, trạng thái kích hoạt (`is_active`), khóa/mở tài khoản tức thì.
- **Đối soát Giao dịch**: Theo dõi dòng tiền thanh toán cọc và tất toán qua cổng SePay VietQR.
- **Giám sát Mô hình AI**: Xem trạng thái mô hình Random Forest, tỷ lệ ghép trận và độ chính xác phân loại.

---

## 📁 Cấu Trúc Thư Mục

```
admin-portal/
├── src/
│   ├── app/              # Trang điều hành trung tâm (page.tsx) & đăng nhập (login/)
│   └── lib/              # Client API & Auth Context độc lập
├── Dockerfile            # Container build manifest (Cổng 3001)
└── package.json          # Dependencies & Scripts
```

---

## 🚀 Khởi Chạy Cục Bộ

```bash
npm install
npm run dev
# Mở trình duyệt tại: http://localhost:3001
```
