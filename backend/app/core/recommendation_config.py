"""Tham số của thuật toán gợi ý cụm sân (lọc -> chấm điểm đa tiêu chí -> xếp hạng)."""

# Thang 100 điểm: gần tối đa 40, giá tối đa 35, giờ còn trống tối đa 25 (đánh giá không được tính).
# Score = Σ w_i * s_i / Σ w_i trên các tiêu chí CÓ dữ liệu: chưa biết vị trí người dùng thì tiêu chí khoảng cách
# bị loại và hai tiêu chí còn lại được quy về thang 100, thay vì gán một điểm trung tính bịa ra.
WEIGHTS = {
    "distance": 0.40,
    "price": 0.35,
    "time": 0.25,
}

# Khoảng cách: chuẩn hóa min-max trên các sân ứng viên, giống cách so giá khi không có ngân sách:
# sân gần người dùng nhất 1 điểm, sân xa nhất 0 điểm. Đổi vị trí thì thứ hạng đổi theo rõ ràng, thay vì mọi sân
# trong thành phố (cách nhau vài km) đều được điểm khoảng cách gần như nhau như cách tính cũ 1 - d/20 km.

# Giá (VNĐ/giờ) khi người dùng có ngân sách: giá <= ngân sách -> 1 điểm,
# giảm tuyến tính về 0 khi giá vượt ngân sách BUDGET_OVERRUN_LIMIT (50%).
# Không có ngân sách: chuẩn hóa min-max trên các sân ứng viên (rẻ nhất 1 điểm, đắt nhất 0 điểm).
BUDGET_OVERRUN_LIMIT = 0.5
