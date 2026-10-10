# 📑 Hướng Dẫn Thực Hiện Khóa Luận Tốt Nghiệp (KLTN)
> **Đề tài**: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh (**PickleMatch2K**)

---

## 🎯 1. Mục Tiêu Đề Tài

* **Người chơi (Player)**: Tìm kiếm sân theo GPS, xem lịch trống thời gian thực, đặt cọc SePay VietQR, nhận gợi ý sân phù hợp, tạo kèo & ghép cặp thi đấu.
* **Chủ sân (Owner)**: Quản lý cụm sân, upload hình ảnh, cấu hình bảng giá linh hoạt, phân công nhân viên ca trực, đối soát doanh thu.
* **Nhân viên (Staff)**: Check-in mã QR khách tại sân, thu tiền đợt 2, chốt ca trực.
* **Quản trị viên (Admin)**: Cổng điều hành độc lập (Port 3001) giám sát toàn hệ thống, phê duyệt sân, đối soát giao dịch, quản lý mô hình AI.

**Điểm nhấn kỹ thuật**:
1. **Gợi ý cụm sân**: Thuật toán đánh giá đa tiêu chí (MCDA) chuẩn hóa thang điểm $\rightarrow$ Xếp hạng Top-N.
2. **AI ghép người chơi**: Mô hình học máy **Random Forest Classifier** dự đoán mức độ phù hợp giữa 2 người chơi.

---

## 🏗️ 2. Phân Tích & Thiết Kế Hệ Thống

| Nhóm yêu cầu | Nội dung thực hiện |
| :--- | :--- |
| **Khảo sát nghiệp vụ** | Đặc tả 4 nhóm tác nhân: `Player`, `Venue Owner`, `Staff`, `Admin` |
| **Mô hình hóa** | Use Case Diagrams, Activity Diagrams, Sequence Diagrams |
| **Cơ sở dữ liệu** | Thiết kế ERD chuẩn hóa quan hệ (Users, Venues, Courts, Bookings, Matches, Payments) |
| **Kiến trúc** | Client-Server Asynchronous RESTful API + WebSockets Realtime |

---

## ⚙️ 3. Phân Hệ Nghiệp Vụ Cốt Lõi

### 3.1. Phân hệ Người Chơi (Player)
* **Tài khoản**: Đăng ký, đăng nhập JWT, cập nhật hồ sơ & trình độ DUPR cá nhân.
* **Tìm kiếm**: Định vị GPS, tính khoảng cách (Haversine), bộ lọc tiện ích & mức giá.
* **Đặt sân**: Chọn khung giờ trống theo thời gian thực, đặt cọc 50% qua SePay VietQR tự động.
* **Kèo đấu**: Tạo trận đấu công khai, mời bạn bè, sử dụng AI gợi ý bạn đấu.

### 3.2. Phân hệ Chủ Cụm Sân (Owner)
* **Quản lý sân**: Danh sách sân, bộ sưu tập ảnh đa góc, tiện ích (mái che, đèn, bãi đỗ).
* **Bảng giá**: Khung giờ thường, giờ cao điểm, phụ thu cuối tuần.
* **Vận hành**: Chống đặt trùng khung giờ (Slot Locking Mechanism), phân quyền nhân viên ca trực.

---

## 🌟 4. Chức Năng Gợi Ý Sân (Venue Recommendation)

Quy trình: **Lọc sân khả dụng** $\rightarrow$ **Chuẩn hóa thang điểm [0, 1]** $\rightarrow$ **Tính điểm tổng hợp** $\rightarrow$ **Top-N Sân tốt nhất**.

### Công thức tính điểm tổng hợp:
$$\text{Score} = 0.30 \cdot D + 0.25 \cdot P + 0.20 \cdot T + 0.15 \cdot R + 0.10 \cdot S$$

Trong đó:
* **$D$ (Distance)**: Điểm khoảng cách địa lý GPS.
* **$P$ (Price)**: Điểm phù hợp ngân sách mong muốn.
* **$T$ (Time Slot)**: Điểm sẵn sàng khung giờ trống.
* **$R$ (Rating)**: Điểm đánh giá sao trung bình của cụm sân.
* **$S$ (Service)**: Điểm tiện ích phù hợp sở thích người dùng.

> **Ví dụ**: $D=0.9, P=0.8, T=1.0, R=0.85, S=0.7$  
> $\Rightarrow \text{Score} = 0.30(0.9) + 0.25(0.8) + 0.20(1.0) + 0.15(0.85) + 0.10(0.7) = \mathbf{0.8675} \ (86.75\%)$

---

## 🤖 5. Chức Năng AI Ghép Người Chơi (Random Forest Matchmaking)

### 5.1. Đặc trưng đầu vào (Input Features)
1. **Chênh lệch trình độ**: $|\text{DUPR}_A - \text{DUPR}_B|$
2. **Khoảng cách địa lý**: Khoảng cách tính bằng Km giữa 2 vị trí.
3. **Độ trùng thời gian**: Mức độ giao thoa các khung giờ rảnh trong tuần.
4. **Mục đích chơi**: Giao lưu, Luyện tập, Leo rank/Thi đấu.
5. **Phong cách chơi**: Tấn công uy lực, Phòng thủ/Dinking, Đa năng.

### 5.2. Pipeline Huấn luyện & Đánh giá
$$\text{Dataset} \rightarrow \text{Data Preprocessing} \rightarrow \text{Train/Test Split (80/20)} \rightarrow \text{Random Forest} \rightarrow \text{Model Evaluation} \rightarrow \text{Export (.pkl)}$$

* **Thư viện**: `scikit-learn`, `pandas`, `numpy`, `joblib`.
* **Tiêu chí đánh giá**: Precision, Recall, F1-Score, ROC-AUC (so sánh vượt trội so với Rule-based Baseline).

### 5.3. Tích hợp Backend API
```text
Player A ───> Backend lấy danh sách ứng viên ───> Vector hóa Features
                                                          │
                                                          ▼
Client <─── Xếp hạng giảm dần <─── Trích xuất % Match <─── model.predict_proba()
```

| Ứng viên (Player) | Trình độ DUPR | Khoảng cách | Mục đích | Xác suất phù hợp (Match %) |
| :--- | :--- | :--- | :--- | :--- |
| **Player B** | 3.5 | 1.8 km | Giao lưu | **91.5%** |
| **Player C** | 3.6 | 3.2 km | Luyện tập | **84.0%** |
| **Player D** | 4.0 | 2.5 km | Thi đấu | **72.3%** |
| **Player E** | 5.0 | 12.0 km | Giao lưu | **38.0%** |

---

## 💻 6. Kiến Trúc Công Nghệ

```
┌─────────────────────────────────────────────────────────────┐
│                    PICKLEMATCH2K SYSTEM                     │
├──────────────────────────────┬──────────────────────────────┤
│      Frontend (Port 3000)    │    Admin Portal (Port 3001)  │
│  Next.js 16 / React 19 / TS  │  Next.js 16 / Dark Theme     │
└──────────────┬───────────────┴──────────────┬───────────────┘
               │                              │
               └──────────────┬───────────────┘
                              ▼
        ┌─────────────────────────────────────────────┐
        │          Backend API (Port 8000)            │
        │          FastAPI (Python 3.11+)             │
        ├──────────────────────┬──────────────────────┤
        │  • Business Services │  • AI Matchmaker     │
        │  • WebSocket Manager │  • SePay VietQR      │
        └──────────┬───────────┴──────────┬───────────┘
                   │                      │
                   ▼                      ▼
        ┌─────────────────────┐┌──────────────────────┐
        │  PostgreSQL 15/17   ││ Random Forest (.pkl) │
        │ (Relational DB RDBMS││ (Scikit-Learn Model)  │
        └─────────────────────┘└──────────────────────┘
```

---

## 🧪 7. Kiểm Thử & Đánh Giá Hệ Thống

1. **Kiểm thử chức năng**: Đăng ký/đăng nhập, tìm sân GPS, đặt cọc SePay, QR check-in, hủy sân.
2. **Kiểm thử đồng thời**: Mô phỏng nhiều luồng cùng bấm đặt 1 slot (Slot Lock Test).
3. **Kiểm thử mô hình AI**: Đánh giá F1-score của Random Forest so với baseline.
4. **Kiểm thử luồng nghiệp vụ**: Liên thông 4 vai trò (Player $\rightarrow$ Owner $\rightarrow$ Staff $\rightarrow$ Admin).

---

## 📌 8. Tóm Tắt Trọng Tâm Khóa Luận

```
[Nghiệp vụ cốt lõi: Đặt sân & Vận hành] 
       │
       ├──> [Hỗ trợ lựa chọn: Gợi ý cụm sân Top-N (MCDA)]
       │
       └──> [Hỗ trợ kết nối: AI Ghép cặp đấu (Random Forest Classifier)]
```
