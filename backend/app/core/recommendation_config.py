"""Tham số của thuật toán gợi ý cụm sân (lọc -> chấm điểm đa tiêu chí -> xếp hạng)."""

# Score = Σ w_i * s_i / Σ w_i trên các tiêu chí CÓ dữ liệu.
# Tiêu chí thiếu dữ liệu (chưa biết vị trí người dùng, chưa khai sở thích) bị loại khỏi phép tính
# và trọng số còn lại được chuẩn hóa lại, thay vì gán một điểm trung tính bịa ra.
WEIGHTS = {
    "distance": 0.30,
    "price": 0.25,
    "time": 0.20,
    "rating": 0.15,
    "preference": 0.10,
}

# Khoảng cách: 0 km -> 1 điểm, từ MAX_EXPECTED_DISTANCE_KM trở lên -> 0 điểm
MAX_EXPECTED_DISTANCE_KM = 20.0

# Giá (VNĐ/giờ) khi người dùng có ngân sách: giá <= ngân sách -> 1 điểm,
# giảm tuyến tính về 0 khi giá vượt ngân sách BUDGET_OVERRUN_LIMIT (50%).
# Không có ngân sách: chuẩn hóa min-max trên các sân ứng viên (rẻ nhất 1 điểm, đắt nhất 0 điểm).
BUDGET_OVERRUN_LIMIT = 0.5

# Đánh giá: trung bình Bayes (v*R + m*C) / (v + m) để sân ít đánh giá không bị đẩy lên/xuống quá mức.
MAX_RATING = 5.0
RATING_PRIOR_WEIGHT = 5        # m: số đánh giá "ảo" kéo về điểm trung bình toàn hệ thống
RATING_PRIOR_FALLBACK = 4.0    # C khi toàn hệ thống chưa có đánh giá nào
