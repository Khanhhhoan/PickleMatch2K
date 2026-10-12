# PickleMatch2K - Cổng quản trị (cổng 3001)

Ứng dụng Next.js 16 riêng cho quản trị viên, tách khỏi cổng người dùng. Chỉ tài khoản có vai trò `ADMIN` đăng nhập được;
phiên đăng nhập lưu riêng (`admin_token`) nên không lẫn với phiên của cổng 3000.

## Chạy

```powershell
npm ci
npm run dev                     # http://localhost:3001, cần API ở cổng 8000
npm run build; npm start
npx tsc --noEmit
```

Địa chỉ API: mặc định là cùng tên máy, cổng 8000. Đặt `NEXT_PUBLIC_API_URL` trong `admin-portal/.env.local` nếu API ở nơi khác.

## Các thẻ chức năng

| Thẻ | Nội dung | API chính |
| :--- | :--- | :--- |
| Tổng quan | Số liệu toàn hệ thống; thống kê thực thu và số đơn đặt theo từng ngày, từng tháng hoặc từng năm; phân bố trạng thái của đơn đặt, cụm sân, phòng đấu | `/bookings/owner/stats` |
| Cụm sân | Duyệt / từ chối cụm sân chờ duyệt, đổi trạng thái, tạo, sửa, xóa | `/venues/admin/*` |
| Tài khoản | Xem chi tiết, tạo, sửa, khóa / mở khóa, xóa (tài khoản đã có lịch sử thì chỉ bị khóa) | `/users/admin/users` |
| Đơn đặt sân | Tra cứu toàn bộ đơn và tình trạng hoàn tiền, đổi trạng thái, xóa đơn | `/bookings/admin/all` |
| Sổ giao dịch | Tiền cọc, phần thu tại sân, tiền hoàn; lọc theo chủ sân | `/payments/transactions` |
| Phòng đấu | Tạo, đổi trạng thái, xóa phòng đấu; xem và gỡ người tham gia | `/matches/admin/*` |

Mọi số liệu lấy trực tiếp từ API; cổng không tự tính hay hiển thị số liệu giả. Phần thống kê theo thời gian dùng chuỗi
theo ngày (`daily`, tính theo giờ Việt Nam) mà API trả về, cổng chỉ gom các ngày thành tháng và năm.

## Mã nguồn

```text
src/
├── app/page.tsx            Khung trang: tải dữ liệu, điều hướng thẻ, thông báo kết quả thao tác
├── app/login/              Đăng nhập quản trị
├── components/ui.tsx       Thành phần giao diện dùng chung
├── components/tabs/        OverviewTab, VenuesTab, UsersTab, BookingsTab, TransactionsTab, MatchesTab
└── lib/                    api.ts, auth-context.tsx, types.ts, labels.ts, stats.ts, use-websocket.ts
```
