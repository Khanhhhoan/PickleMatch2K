# Kiểm thử backend

```bash
# từ thư mục gốc dự án, với môi trường ảo đã kích hoạt
pip install -r backend/requirements-dev.txt
python -m pytest                      # toàn bộ (khoảng 2-3 phút)
python -m pytest backend/tests/test_booking_flow.py -q
python -m pytest -k "webhook or concurrency"
```

## CSDL dùng cho test

Bộ test **không bao giờ chạm vào CSDL đang dùng**. Trước khi ứng dụng tạo kết nối, `conftest.py` trỏ sang một
CSDL PostgreSQL riêng có tên kết thúc bằng `_test`:

- mặc định: `pickleball_test` trên cùng máy chủ và tài khoản với `DATABASE_URL` trong `.env` (tự tạo nếu chưa có);
- hoặc đặt `TEST_DATABASE_URL=postgresql://user:pass@host:5432/<tên>_test`.

Mỗi phiên test xóa schema của CSDL test và dựng lại bằng chính các migration Alembic, nên migration cũng được
kiểm tra. Mỗi test bắt đầu với các bảng trống. Redis, Cloudinary và SePay thật không được gọi.

## Đồng hồ nghiệp vụ

Nghiệp vụ phụ thuộc thời gian (hạn cọc 15 phút, mốc hủy 12 giờ / 6 giờ, check-in đúng ngày…) nên mọi test chạy
với đồng hồ **đứng yên ở 08:00 hôm nay (giờ Việt Nam)**. Test chủ động tua bằng fixture `clock`:

```python
def test_vi_du(client, world, clock):
    booking = create_booking(client, world.p1, world.court, clock.day(1), hours=(18,))
    clock.advance(minutes=16)          # quá hạn thanh toán cọc
    clock.set(clock.day(1), 17, 50)    # 17:50 ngày mai
```

## Nội dung

| File | Phạm vi |
| :--- | :--- |
| `test_security.py` | Băm mật khẩu, nâng cấp hash cũ, token, đăng ký, khóa đăng nhập sai, tài khoản bị khóa |
| `test_permissions.py` | Mọi endpoint không công khai đều đòi đăng nhập; phân quyền theo vai trò và theo cụm sân |
| `test_users.py` | Hồ sơ, đổi mật khẩu, quản trị tài khoản (khóa thay vì xóa khi đã có lịch sử) |
| `test_venue_config.py` | Giá từng khung giờ, lịch trống, sân con, giờ hoạt động, ảnh, đánh giá, duyệt cụm sân |
| `test_booking_flow.py` | Tạo đơn, kiểm tra đầu vào, hết hạn giữ chỗ, check-in, hoàn tất, ràng buộc chống đặt trùng ở CSDL |
| `test_booking_cancellation.py` | Mức hoàn tiền theo thời điểm hủy, xác nhận hoàn tiền |
| `test_desk_booking.py` | Đơn tại quầy, khách vãng lai, dời lịch, thống kê từ sổ giao dịch |
| `test_payments.py` | Thông tin chuyển khoản, webhook SePay (xác thực, khớp đơn, ghi trùng, tiền đến muộn), giả lập |
| `test_concurrency.py` | Nhiều luồng thật tranh một khung giờ / một giao dịch / chỗ cuối của phòng đấu |
| `test_slot_holds.py` | Giữ chỗ tạm trên bộ nhớ và Redis (client giả), Redis lỗi |
| `test_matches.py` | Phòng đấu gắn với đơn đặt, tham gia/rời, tự cập nhật, quyền riêng tư |
| `test_recommendation.py` | Chuẩn hóa từng tiêu chí và xếp hạng gợi ý cụm sân |
| `test_ml.py` | Đặc trưng, huấn luyện/đánh giá, phục vụ mô hình, khảo sát thu nhãn, phiếu mô phỏng nạp trong CSDL (tách khỏi nhãn thật) |
| `test_infrastructure.py` | Schema sau migration, nâng cấp CSDL cũ bằng `manage.py migrate`, tác vụ nền, WebSocket, script seed / nhập Excel / reset |

`helpers.py` chứa hàm dựng dữ liệu và thao tác API dùng chung; `conftest.py` chứa fixture (`db`, `client`,
`clock`, `world`).
