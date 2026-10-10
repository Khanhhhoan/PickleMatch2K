"""Tham số nghiệp vụ đặt sân. Giao diện (Footer, hộp thoại hủy) hiển thị đúng các giá trị này."""
from datetime import timedelta

SLOT_MINUTES = 60                         # Mỗi khung giờ đặt sân dài 60 phút
DEPOSIT_RATE = 0.5                        # Đặt cọc 50% tổng tiền
PENDING_PAYMENT_TTL = timedelta(minutes=15)  # Thời hạn thanh toán cọc của đơn mới tạo
SLOT_HOLD_SECONDS = 300                   # Giữ chỗ tạm khi đang chọn slot (5 phút)

MAX_SLOTS_PER_BOOKING = 12                # Số khung giờ tối đa trong một đơn
MAX_PENDING_BOOKINGS_PER_USER = 3         # Số đơn chờ cọc tối đa của một người chơi
MAX_HELD_SLOTS_PER_USER = 12              # Số slot một người được giữ tạm cùng lúc
MAX_ADVANCE_DAYS = 60                     # Chỉ đặt trước tối đa 60 ngày

# Chính sách hủy của người chơi (tính theo số giờ trước khung giờ đầu tiên)
CANCEL_FULL_REFUND_HOURS = 12             # Hủy trước >= 12 giờ: hoàn 100% số tiền đã trả
CANCEL_RESCHEDULE_HOURS = 6               # Từ 6 đến dưới 12 giờ: không hoàn cọc, được hỗ trợ dời lịch
                                          # Dưới 6 giờ hoặc không đến: không hoàn cọc

PAYMENT_TOLERANCE = 1.0                   # Sai số làm tròn (VNĐ) khi so tiền chuyển khoản


def deposit_for(total_price: float) -> float:
    return float(round(total_price * DEPOSIT_RATE))
