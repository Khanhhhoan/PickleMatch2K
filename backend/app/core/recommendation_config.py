"""Tham số của thuật toán gợi ý cụm sân (lọc -> chấm điểm đa tiêu chí -> xếp hạng)."""

# Thang 100 điểm: gần tối đa 40, giá tối đa 35, giờ còn trống tối đa 25 (đánh giá không được tính).
# Score = Σ w_i * s_i / Σ w_i trên các tiêu chí CÓ dữ liệu: chưa biết vị trí người dùng thì tiêu chí khoảng cách
# bị loại và hai tiêu chí còn lại được quy về thang 100, thay vì gán một điểm trung tính bịa ra.
WEIGHTS = {
    "distance": 0.40,
    "price": 0.35,
    "time": 0.25,
}

# Khoảng cách: 0 km -> 1 điểm, từ MAX_EXPECTED_DISTANCE_KM trở lên -> 0 điểm
MAX_EXPECTED_DISTANCE_KM = 20.0

# Giá (VNĐ/giờ) khi người dùng có ngân sách: giá <= ngân sách -> 1 điểm,
# giảm tuyến tính về 0 khi giá vượt ngân sách BUDGET_OVERRUN_LIMIT (50%).
# Không có ngân sách: chuẩn hóa min-max trên các sân ứng viên (rẻ nhất 1 điểm, đắt nhất 0 điểm).
BUDGET_OVERRUN_LIMIT = 0.5
