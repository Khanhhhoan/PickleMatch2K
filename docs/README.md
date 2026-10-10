# Tài liệu - PickleMatch2K

| Tài liệu | Nội dung |
| :--- | :--- |
| [HUONG_DAN_KLTN.md](HUONG_DAN_KLTN.md) | Phạm vi chức năng, kiến trúc, nghiệp vụ đặt sân, công thức gợi ý cụm sân, mô hình Random Forest ghép người chơi và kết quả đánh giá, cách kiểm thử |
| [DATABASE_DESIGN.md](DATABASE_DESIGN.md) | Sơ đồ quan hệ, mô tả từng bảng, các ràng buộc chống đặt trùng và chống ghi trùng giao dịch, chỉ mục, lịch sử schema |
| [DANH_SACH_TAI_KHOAN_TEST.md](DANH_SACH_TAI_KHOAN_TEST.md) | 33 tài khoản demo do `python manage.py seed` tạo (mật khẩu `123456`) |
| `DANH_SACH_TAI_KHOAN_TEST.docx` | Bản in của danh sách tài khoản; bản `.md` là bản được cập nhật theo mã nguồn |
| `Mau_Nhap_Du_Lieu_Pickleball.xlsx` | Mẫu Excel để nhập cụm sân bằng `python manage.py import-excel` |
| `Nhom_6_Khanh_va_Khang.docx` | Báo cáo khóa luận của nhóm |

Hướng dẫn cài đặt, chạy và kiểm thử nằm ở [README gốc](../README.md); tài liệu kỹ thuật của backend ở
[backend/README.md](../backend/README.md).

Các tài liệu Markdown ở đây được viết theo mã nguồn hiện tại. Báo cáo `.docx` là văn bản của nhóm và có thể còn mô tả
phiên bản trước của hệ thống (ví dụ SQLite, số lượng kiểm thử, kết quả mô hình); khi cập nhật báo cáo, hãy đối chiếu
số liệu với hai tài liệu trên và với `backend/app/ml/model_meta.json`.
