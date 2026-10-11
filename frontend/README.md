# PickleMatch2K - Cổng người chơi, chủ sân, nhân viên (cổng 3000)

Ứng dụng Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4. Mọi dữ liệu lấy từ API backend;
ứng dụng không tự chứa dữ liệu mẫu.

## Chạy

```powershell
npm ci
npm run dev                     # http://localhost:3000, cần API ở cổng 8000
npm run build; npm start        # bản build chính thức
npx tsc --noEmit                # kiểm tra kiểu
```

Địa chỉ API: mặc định trình duyệt gọi API ở **cùng tên máy, cổng 8000**, nên mở từ điện thoại trong mạng LAN
(`http://192.168.x.x:3000`) vẫn chạy. Chỉ khi API nằm ở địa chỉ khác mới cần tạo `frontend/.env.local`:

```text
NEXT_PUBLIC_API_URL=https://api.ten-mien.vn
NEXT_PUBLIC_ADMIN_URL=https://admin.ten-mien.vn
```

## Các trang

| Đường dẫn | Vai trò | Nội dung |
| :--- | :--- | :--- |
| `/` | Người chơi | Tìm cụm sân theo tên và khu vực; chọn vị trí để danh sách xếp từ gần đến xa |
| `/venues/[id]` | Người chơi | Thông tin sân, lịch trống theo thời gian thực, giữ chỗ, đặt sân, đánh giá |
| `/bookings` | Người chơi | Đơn của tôi, đếm ngược hạn cọc, vé QR, hủy đơn với mức hoàn tiền xem trước |
| `/matches`, `/matches/create` | Người chơi | Phòng do mô hình đề xuất (độ phù hợp từ 70%), mọi phòng đang mở, phòng của tôi; mở phòng trên đơn đã cọc |
| `/survey` | Người chơi | Khảo sát thu nhãn cho mô hình ghép cặp |
| `/profile` | Người chơi | Hồ sơ và 4 thông tin mô hình ghép cặp dùng: trình độ, phong cách, mục đích, khu vực thường chơi |
| `/owner/dashboard` | Chủ sân | Doanh thu và hoạt động của cụm sân |
| `/owner/venues` | Chủ sân | Thông tin và tài khoản nhận tiền, sân con và bảng giá, giờ mở cửa, nhân viên |
| `/owner/bookings` | Chủ sân | Quầy đặt sân |
| `/staff/dashboard`, `/staff/bookings` | Nhân viên | Tổng quan ca trực và quầy đặt sân của cụm sân được phân công |
| `/login`, `/register` | | Đăng nhập, đăng ký người chơi |

Các trang `/owner/courts`, `/owner/pricing`, `/owner/staff`… chỉ chuyển hướng về `/owner/venues`.
Tài khoản quản trị đăng nhập ở đây được chuyển sang cổng quản trị (cổng 3001).

## Mã nguồn

```text
src/
├── app/                    Các trang (App Router)
├── components/
│   ├── BookingDesk.tsx     Quầy đặt sân dùng chung cho chủ sân và nhân viên: lưới lịch, tạo đơn tại quầy,
│   │                       tra mã / quét QR, check-in, thu tiền, dời lịch, hủy, xác nhận hoàn tiền
│   ├── SepayCheckoutModal.tsx   Thanh toán cọc VietQR, theo dõi trạng thái từ máy chủ
│   └── …                   Navbar, Footer, Toast, LocationPickerModal, VenueImageHoverSlider…
└── lib/
    ├── api.ts              Gọi API, xử lý lỗi và hết phiên đăng nhập
    ├── auth-context.tsx    Phiên đăng nhập và hồ sơ
    ├── booking.ts          Kiểu dữ liệu, nhãn trạng thái, tiện ích cho đơn đặt
    ├── player.ts           Danh mục trình độ, phong cách, mục đích
    ├── use-websocket.ts    Kết nối WebSocket tự nối lại
    └── location.ts         Vị trí người dùng
```

Trước khi sửa mã, đọc `AGENTS.md`: Next.js 16 có nhiều thay đổi so với các phiên bản trước.

## Ghi chú

- Quét QR bằng camera cần trình duyệt có `BarcodeDetector` và trang chạy trên HTTPS hoặc `localhost`; nếu không,
  nhân viên nhập mã đơn bằng tay.
- `npm run lint` còn báo các cảnh báo tồn đọng (chủ yếu kiểu `any`); chúng không chặn bản build.
- Kiểm thử đầu-cuối: `npm run test:e2e` (xem phần kiểm thử ở README gốc).
