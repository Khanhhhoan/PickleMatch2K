# Hướng dẫn kỹ thuật cho khóa luận - PickleMatch2K

> **Đề tài**: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

Tài liệu này mô tả **đúng những gì mã nguồn đang làm**: phạm vi chức năng, công thức gợi ý sân, mô hình ghép người chơi
và cách hệ thống được kiểm thử. Mọi con số ở mục 5 lấy từ `backend/app/ml/model_meta.json`; chạy
`python manage.py train-model --report` để tái lập.

## 1. Mục tiêu và phạm vi

| Tác nhân | Chức năng đã cài đặt |
| :--- | :--- |
| **Người chơi** | Đăng ký, đăng nhập, hồ sơ (trình độ DUPR tự khai, phong cách, mục đích, khung rảnh, tiện ích ưa thích, ngân sách); tìm sân theo vị trí; xem lịch trống theo thời gian thực; đặt sân và cọc 50% qua VietQR; vé QR; hủy đơn và yêu cầu hoàn tiền; đánh giá sân đã chơi; mở và tham gia phòng đấu; nhận gợi ý sân và bạn chơi |
| **Chủ sân** | Đăng ký cụm sân (chờ quản trị viên duyệt); sân con, bảng giá, giờ mở cửa, ảnh; tài khoản nhận tiền; nhân viên; quầy đặt sân; doanh thu |
| **Nhân viên** | Quầy đặt sân của cụm sân được phân công: tạo đơn tại quầy, check-in bằng mã hoặc QR, thu tiền, dời lịch, hủy, xác nhận hoàn tiền |
| **Quản trị viên** | Cổng riêng (cổng 3001): duyệt cụm sân, quản lý tài khoản, giám sát đơn đặt, sổ giao dịch, phòng đấu, thông tin mô hình |

Hai trọng tâm học thuật:

1. **Gợi ý cụm sân** - lọc, chấm điểm đa tiêu chí có trọng số, xếp hạng Top-N (mục 4).
2. **Ghép người chơi** - bộ phân loại Random Forest ước lượng xác suất hai người chơi phù hợp (mục 5).

## 2. Kiến trúc

```text
  Cổng người dùng (3000)            Cổng quản trị (3001)
  Next.js 16 / React 19             Next.js 16 / React 19
            │        REST + WebSocket        │
            └───────────────┬────────────────┘
                            ▼
              Backend API (8000) - FastAPI / Python 3.13
   ┌──────────────┬──────────────┬───────────────┬──────────────┐
   │ Đặt sân,     │ Thanh toán   │ Gợi ý cụm sân │ Ghép cặp     │
   │ sổ giao dịch │ SePay VietQR │ (đa tiêu chí) │ (Random      │
   │              │ + giả lập    │               │  Forest)     │
   └──────┬───────┴──────┬───────┴───────────────┴──────┬───────┘
          ▼              ▼                              ▼
   PostgreSQL 17    Redis (tùy chọn:            match_rf_model.pkl
   (Alembic)        giữ chỗ tạm, giới hạn       (scikit-learn)
                    đăng nhập)
```

Thiết kế CSDL và các ràng buộc: [DATABASE_DESIGN.md](DATABASE_DESIGN.md).

## 3. Nghiệp vụ đặt sân

### 3.1. Vòng đời một đơn

```text
           cọc đủ 50%            check-in            hết giờ chơi
PENDING ───────────────▶ CONFIRMED ─────────▶ CHECKED_IN ─────────▶ COMPLETED
   │                         │
   │ quá 15 phút chưa cọc    ├─ hủy ──────────▶ CANCELLED
   ▼                         └─ không đến ────▶ NO_SHOW
EXPIRED
```

- Mỗi khung giờ dài 60 phút; một đơn gồm một hoặc nhiều khung giờ, giá tính riêng cho từng khung.
- Giá một khung giờ: giá cơ sở (giá riêng của sân nếu có, ngược lại giá `BASE`); khung bắt đầu trong giờ cao điểm dùng giá
  `PEAK`; thứ Bảy và Chủ nhật dùng giá `WEEKEND` (trong giờ cao điểm lấy mức cao hơn giữa `PEAK` và `WEEKEND`).
- Đơn tại quầy do nhân viên tạo được xác nhận ngay, không cần cọc trực tuyến.
- Tác vụ nền mỗi 60 giây: hết hạn đơn chưa cọc, hoàn tất đơn đã check-in, đánh dấu vắng mặt.

### 3.2. Chống đặt trùng

Ba lớp, từ ngoài vào trong:

1. **Giữ chỗ tạm** 5 phút khi người chơi đang chọn khung giờ (Redis, hoặc bộ nhớ khi không có Redis), phát qua WebSocket
   để người khác thấy ngay.
2. **Kiểm tra trong giao dịch** khi tạo đơn.
3. **Ràng buộc của PostgreSQL**: chỉ mục duy nhất và ràng buộc loại trừ trên các khung giờ còn hiệu lực. Đây là lớp
   quyết định: kể cả khi hai yêu cầu vượt qua hai lớp trên cùng lúc, CSDL chỉ chấp nhận một.

### 3.3. Thanh toán và hoàn tiền

- Cọc 50% qua chuyển khoản VietQR; SePay báo về bằng webhook, hệ thống khớp theo mã đơn trong nội dung chuyển khoản.
  Mỗi mã tham chiếu chỉ được ghi một lần. Phần còn lại thu tại sân (tiền mặt hoặc chuyển khoản).
- Mọi khoản thu, hoàn là một dòng trong sổ giao dịch, ghi cùng lúc với việc cập nhật số đã trả của đơn; trạng thái
  thanh toán suy ra từ số đã trả, còn doanh thu trên các bảng tổng quan được cộng từ sổ.
- Chính sách hủy theo số giờ trước khung giờ đầu tiên: từ 12 giờ trở lên hoàn 100% số đã trả; từ 6 đến dưới 12 giờ
  không hoàn cọc nhưng được hỗ trợ dời lịch; dưới 6 giờ hoặc không đến thì không hoàn cọc.
- Khi demo, bộ giả lập (`SEPAY_SIMULATOR_ENABLED=true`) tạo giao dịch đi qua đúng luồng xử lý của webhook.

### 3.4. Phòng đấu

Người chơi mở phòng đấu trên một đơn **đã cọc** của chính mình, nên phòng đấu luôn có sân và giờ thật. Người khác tham
gia tới khi đủ số người; phòng tự đóng khi qua giờ hoặc khi đơn đặt bị hủy.

## 4. Gợi ý cụm sân

Cài đặt: `backend/app/services/venue_recommendation_service.py`, tham số ở `backend/app/core/recommendation_config.py`.
API: `GET /api/v1/recommendations/venues`.

### 4.1. Quy trình

1. **Lọc**: chỉ lấy cụm sân đang hoạt động; nếu người dùng đặt bán kính thì bỏ cụm sân nằm ngoài bán kính.
2. **Chuẩn hóa** từng tiêu chí về thang $[0, 1]$.
3. **Tính điểm tổng hợp** có trọng số rồi lấy Top-N.

### 4.2. Điểm tổng hợp

$$\text{Score} = \frac{\sum_{i \in K} w_i \, s_i}{\sum_{i \in K} w_i}$$

$K$ là tập tiêu chí **có dữ liệu**. Khi đủ cả năm tiêu chí, công thức trở thành:

$$\text{Score} = 0.30\,D + 0.25\,P + 0.20\,T + 0.15\,R + 0.10\,S$$

Tiêu chí thiếu dữ liệu (chưa biết vị trí người dùng, chưa khai tiện ích ưa thích) bị loại khỏi phép tính và các trọng số
còn lại được chuẩn hóa lại; hệ thống không gán một điểm "trung tính" tự đặt ra.

### 4.3. Chuẩn hóa từng tiêu chí

| Tiêu chí | Trọng số | Cách tính |
| :--- | :---: | :--- |
| $D$ - khoảng cách | 0.30 | $D = \max(0,\ 1 - d / 20)$ với $d$ là khoảng cách Haversine (km) từ người dùng tới sân; từ 20 km trở lên được 0 điểm |
| $P$ - giá | 0.25 | Có ngân sách $B$: $P = 1$ nếu giá $\le B$, giảm tuyến tính về 0 khi giá đạt $1.5B$. Chưa có ngân sách: min-max trên các sân ứng viên (rẻ nhất 1, đắt nhất 0) |
| $T$ - giờ trống | 0.20 | Tỷ lệ khung giờ còn đặt được trong ngày (hoặc trong khoảng giờ người dùng chọn), không tính khung đã qua |
| $R$ - đánh giá | 0.15 | Trung bình Bayes chia cho 5 (xem dưới) |
| $S$ - tiện ích | 0.10 | Tỷ lệ tiện ích ưa thích của người dùng mà sân đáp ứng |

Giá dùng để chấm là giá trung bình của các khung giờ còn trống trong ngày đang xét (hoặc của mọi khung giờ trong ngày
khi sân đã kín lịch).

**Trung bình Bayes cho đánh giá.** Với $v$ là số đánh giá và $\bar{r}$ là điểm trung bình của sân:

$$R_{\text{bayes}} = \frac{v\,\bar{r} + m\,C}{v + m}, \qquad m = 5$$

$C$ là điểm trung bình toàn hệ thống (chính $C$ cũng được kéo về mốc 4.0 khi tổng số đánh giá còn ít). Nhờ đó một sân
mới có hai đánh giá 5 sao không vượt lên trên sân có năm mươi đánh giá trung bình 4.7.

### 4.4. Ví dụ

Đủ năm tiêu chí, $D = 0.9,\ P = 0.8,\ T = 1.0,\ R = 0.85,\ S = 0.7$:

$$\text{Score} = 0.30(0.9) + 0.25(0.8) + 0.20(1.0) + 0.15(0.85) + 0.10(0.7) = 0.8675$$

Cùng sân đó khi người dùng chưa khai tiện ích ưa thích (bỏ $S$, tổng trọng số còn 0.90):

$$\text{Score} = \frac{0.27 + 0.20 + 0.20 + 0.1275}{0.90} = 0.8861$$

Các phép chuẩn hóa: sân cách 5 km có $D = 1 - 5/20 = 0.75$; ngân sách 200.000 đ, giá 250.000 đ có
$P = 1 - 50.000 / 100.000 = 0.5$; sân có 2 đánh giá 5 sao khi $C = 4.2$ có
$R_{\text{bayes}} = (2 \cdot 5 + 5 \cdot 4.2) / 7 = 4.43$, tức $R = 0.886$.

API trả về điểm tổng hợp, điểm từng tiêu chí và danh sách tiêu chí đã dùng, để giao diện giải thích được vì sao một
sân được xếp trên.

## 5. Ghép người chơi bằng Random Forest

Cài đặt: `backend/app/ml/features.py` (đặc trưng), `backend/app/ml/train_model.py` (huấn luyện, đánh giá),
`backend/app/services/ml_service.py` (phục vụ). API: `GET /api/v1/ml/recommend-partners`, `POST /api/v1/ml/predict-match`.

### 5.1. Đặc trưng

Mô hình nhận năm đặc trưng của **một cặp** người chơi, đều đối xứng giữa hai người:

| Đặc trưng | Định nghĩa |
| :--- | :--- |
| `level_diff` | $\lvert \text{DUPR}_A - \text{DUPR}_B \rvert$ |
| `distance_km` | Khoảng cách Haversine giữa hai vị trí thường chơi, chặn trên 50 km. Thiếu vị trí của một bên thì dùng giá trị trung tính 10 km và báo hồ sơ còn thiếu |
| `availability_overlap` | Chỉ số Jaccard giữa hai tập khung rảnh trong tuần (7 ngày × sáng, chiều, tối) |
| `purpose_match` | 1 nếu cùng mục đích chơi (giao lưu, luyện tập, thi đấu), ngược lại 0 |
| `style_match` | 1 nếu cùng phong cách hoặc một bên chơi toàn diện, ngược lại 0 |

Cùng một module tạo đặc trưng cho huấn luyện, khảo sát và suy luận, nên dữ liệu huấn luyện và dữ liệu phục vụ luôn
nhất quán. Thiếu trình độ của một trong hai người thì không dự đoán.

### 5.2. Dữ liệu huấn luyện

Hệ thống chưa có đủ dữ liệu ghép cặp thật, nên có hai nguồn:

1. **Dữ liệu tổng hợp khởi tạo** (đang dùng): 60.000 cặp sinh ngẫu nhiên; nhãn được gán bằng một quy tắc viết tay
   (`synthetic_rule_score`: ưu tiên chênh lệch trình độ nhỏ, ở gần, trùng giờ rảnh, cùng mục đích và phong cách)
   cộng nhiễu Gauss $\sigma = 0.08$. Nguồn này chỉ để hệ thống có mô hình chạy được từ đầu.
2. **Nhãn thật từ khảo sát** trong ứng dụng (trang `/survey`): người chơi xem các hồ sơ ứng viên giả định xoay quanh
   hồ sơ của chính mình (trải đều các mức chênh trình độ, khoảng cách, độ trùng lịch) và trả lời có muốn ghép hay
   không; câu trả lời lưu vào bảng `pair_feedback` cùng đặc trưng của cặp. Khi có từ 300 nhãn trở lên,
   `train-model` tự chuyển sang huấn luyện bằng nhãn thật và đánh giá bằng **GroupKFold theo người trả lời**, để nhãn
   của cùng một người không nằm ở cả tập huấn luyện lẫn tập kiểm tra.

### 5.3. Mô hình

`RandomForestClassifier` của scikit-learn: 200 cây, độ sâu tối đa 8, tối thiểu 20 mẫu mỗi lá, `class_weight="balanced"`,
`random_state=42`. Mô hình được lưu thành `match_rf_model.pkl`, kèm `model_meta.json` ghi nguồn dữ liệu, cách đánh giá
và các chỉ số.

### 5.4. Kết quả đánh giá hiện tại

Dữ liệu tổng hợp, 60.000 cặp, tỷ lệ nhãn dương 50,62%, tách ngẫu nhiên 80/20 có phân tầng:

| Mô hình | Accuracy | Precision | Recall | F1 | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Đoán theo lớp đa số | 0.5062 | 0.5062 | 1.0000 | 0.6722 | - |
| Luật một ngưỡng: chênh trình độ ≤ 0.5 | 0.8818 | 0.8914 | 0.8728 | 0.8820 | - |
| Hồi quy logistic | 0.9259 | 0.9226 | 0.9319 | 0.9272 | 0.9789 |
| **Random Forest** | **0.9319** | **0.9354** | **0.9297** | **0.9326** | **0.9843** |
| Quy tắc sinh nhãn, không nhiễu (mốc trần) | 0.9330 | 0.9351 | 0.9323 | 0.9337 | - |

Mức đóng góp của đặc trưng: `level_diff` 0.821, `distance_km` 0.089, `purpose_match` 0.038, `availability_overlap` 0.038,
`style_match` 0.015.

**Cách đọc các con số này.** Nhãn tổng hợp được sinh từ một quy tắc cộng nhiễu, nên:

- Mốc trần 93,30% là độ chính xác của chính quy tắc sinh nhãn; không mô hình nào vượt được vì phần còn lại là nhiễu.
- Random Forest đạt 93,19%, tức gần như học lại trọn quy tắc và cao hơn luật một ngưỡng (88,18%) cùng hồi quy logistic
  (92,59%).
- Các con số cho thấy quy trình huấn luyện, đánh giá hoạt động đúng. Chúng **chưa** nói lên mức độ mô hình dự đoán
  đúng mong muốn của người chơi thật; kết luận đó cần nhãn khảo sát thật (mục 5.2).

### 5.5. Phục vụ trên API

```text
Người chơi A ──▶ lọc ứng viên: người chơi đang hoạt động, trình độ trong khoảng ±1.5, trong bán kính (nếu đặt)
             ──▶ tạo 5 đặc trưng cho từng cặp (A, ứng viên)
             ──▶ model.predict_proba ──▶ xác suất phù hợp
             ──▶ sắp xếp: xác suất giảm dần, rồi chênh trình độ, rồi khoảng cách
```

Kết quả trả về gồm xác suất, các đặc trưng đã dùng và danh sách mục hồ sơ còn thiếu của người hỏi, để giao diện nhắc
bổ sung. Danh sách phòng đấu cũng hiển thị độ phù hợp trung bình giữa người xem và những người đã ở trong phòng.
Khi chưa có file mô hình, API trả danh sách rỗng kèm lý do, không tự đặt ra điểm số.

## 6. Kiểm thử

| Loại | Cách làm |
| :--- | :--- |
| **Kiểm thử tự động backend** | pytest trên một CSDL PostgreSQL riêng, schema dựng bằng chính các migration. Bao phủ bảo mật và phân quyền (mọi API không công khai đều đòi đăng nhập), vòng đời đơn, hủy và hoàn tiền, đơn tại quầy, webhook thanh toán, phòng đấu, gợi ý sân, mô hình ghép cặp |
| **Kiểm thử đồng thời** | Nhiều luồng thật cùng tranh một khung giờ, cùng gửi một giao dịch, cùng vào chỗ cuối của một phòng đấu; kiểm tra chỉ một luồng thành công và dữ liệu không sai lệch |
| **Kiểm thử phụ thuộc thời gian** | Đồng hồ nghiệp vụ được điều khiển trong test để kiểm tra hạn cọc 15 phút và các mốc hủy 12 giờ, 6 giờ |
| **Kiểm thử đầu-cuối qua trình duyệt** | `scripts/e2e_smoke.js`: 18 bước cho cả bốn vai trò, từ đặt sân, giả lập cọc, vé QR, phòng đấu, hủy và hoàn tiền tới quầy của nhân viên và cổng quản trị |
| **Đánh giá mô hình** | So sánh Random Forest với các mốc so sánh ở mục 5.4 |

Lệnh chạy và cách tổ chức: [README gốc](../README.md) và [backend/tests/README.md](../backend/tests/README.md).

## 7. Giới hạn và hướng phát triển

- Thu nhãn khảo sát thật và đánh giá lại mô hình ghép cặp; khi đó mới so sánh được với luật đơn giản một cách có ý nghĩa.
- Trọng số gợi ý sân đang cố định; có thể hiệu chỉnh theo hành vi đặt sân thực tế.
- Trình độ DUPR do người chơi tự khai, chưa được xác thực.
- Triển khai nhiều tiến trình cần chuyển kênh WebSocket và tác vụ nền sang hạ tầng dùng chung (ví dụ Redis pub/sub).
- Hoàn tiền được nhân viên chuyển khoản thủ công rồi xác nhận trên hệ thống; chưa tự động qua cổng thanh toán.
