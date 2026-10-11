# Hướng dẫn kỹ thuật cho khóa luận - PickleMatch2K

> **Đề tài**: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

Tài liệu này mô tả **đúng những gì mã nguồn đang làm**: phạm vi chức năng, công thức gợi ý sân, mô hình ghép người chơi
và cách hệ thống được kiểm thử. Mọi con số ở mục 5 lấy từ `backend/app/ml/model_meta.json`; chạy
`python manage.py train-model --report` để tái lập.

## 1. Mục tiêu và phạm vi

| Tác nhân | Chức năng đã cài đặt |
| :--- | :--- |
| **Người chơi** | Đăng ký, đăng nhập, hồ sơ (trình độ DUPR tự khai, phong cách, mục đích, khung rảnh, khu vực thường chơi); tìm sân theo vị trí; xem lịch trống theo thời gian thực; đặt sân và cọc 50% qua VietQR; vé QR; hủy đơn và yêu cầu hoàn tiền; đánh giá sân đã chơi; mở phòng đấu trên đơn đã cọc; tham gia phòng đấu do mô hình đề xuất |
| **Chủ sân** | Đăng ký cụm sân (chờ quản trị viên duyệt); sân con, bảng giá, giờ mở cửa, ảnh; tài khoản nhận tiền; nhân viên; quầy đặt sân; doanh thu |
| **Nhân viên** | Quầy đặt sân của cụm sân được phân công: tạo đơn tại quầy, check-in bằng mã hoặc QR, thu tiền, dời lịch, hủy, xác nhận hoàn tiền |
| **Quản trị viên** | Cổng riêng (cổng 3001): duyệt cụm sân, quản lý tài khoản, giám sát đơn đặt, sổ giao dịch, phòng đấu, thông tin mô hình |

Hai trọng tâm của hệ thống:

1. **Quy trình đặt sân** - từ giữ chỗ, đặt, cọc, check-in tới hủy và hoàn tiền, với chống đặt trùng ở tầng CSDL (mục 3).
2. **Ghép trận bằng Random Forest** - bộ phân loại ước lượng xác suất hai người chơi phù hợp; hệ thống dùng nó để đề xuất
   những phòng đấu đã mở có độ phù hợp cao với người xem (mục 5).

Thuật toán gợi ý cụm sân (mục 4) vẫn được cài đặt và kiểm thử ở backend, nhưng giao diện web hiện không dùng tới.

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

> **Trạng thái:** thuật toán và API này vẫn hoạt động và có kiểm thử, nhưng giao diện web không còn gọi tới: trang chủ
> liệt kê cụm sân theo khoảng cách, hồ sơ không còn ô tiện ích ưa thích và ngân sách. Nếu báo cáo vẫn trình bày phần
> này, cần ghi rõ đây là thành phần backend chưa đưa lên giao diện.

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
`backend/app/services/ml_service.py` (phục vụ). API: `GET /api/v1/matches` (độ phù hợp của từng phòng),
`GET /api/v1/ml/model-info`, `POST /api/v1/ml/predict-match`, `GET /api/v1/ml/recommend-partners`.

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

Dữ liệu huấn luyện nằm trong bảng `pair_feedback` của CSDL. Mỗi dòng là một "phiếu ghép cặp": 5 đặc trưng của một cặp,
người trả lời, nhãn muốn ghép (1) hay không (0), và cột `source` ghi nguồn. Lệnh huấn luyện chọn nguồn theo thứ tự:

1. **Nhãn khảo sát thật** (`source = survey`): người chơi trả lời trên trang `/survey` về các hồ sơ ứng viên giả định xoay
   quanh hồ sơ của chính mình. Khi có từ 300 nhãn thật trở lên, mô hình chỉ học từ các nhãn này.
2. **Phiếu ghép cặp mô phỏng** (`source = simulated`, **đang dùng**): 3.000 phiếu nạp bằng
   `python manage.py seed --feedback`. Mỗi tài khoản trong 20 tài khoản người chơi demo "trả lời" 150 phiếu. Hồ sơ ứng
   viên được sinh bằng đúng hàm mà trang khảo sát dùng (trải các mức chênh trình độ, khoảng cách, độ trùng lịch); câu trả
   lời được sinh từ một quy tắc viết tay (`synthetic_rule_score`: ưu tiên chênh lệch trình độ nhỏ, ở gần, trùng giờ
   rảnh, cùng mục đích và phong cách) cộng nhiễu Gauss $\sigma = 0.08$. Hạt giống ngẫu nhiên cố định nên cài ở đâu
   cũng ra cùng một bộ dữ liệu. Đây là dữ liệu mô phỏng để minh họa quy trình, **không phải** câu trả lời của người
   chơi thật.
3. **Dữ liệu tổng hợp trong bộ nhớ**: 60.000 cặp sinh từ cùng quy tắc, chỉ dùng khi CSDL chưa có đủ 300 dòng.

Dữ liệu lấy từ CSDL (nguồn 1 và 2) được đánh giá bằng **GroupKFold theo người trả lời**, để phiếu của cùng một người
không nằm ở cả tập huấn luyện lẫn tập kiểm tra.

Quy trình đầy đủ:

```text
python manage.py seed --feedback     # nạp phiếu mô phỏng vào bảng pair_feedback (bỏ qua nếu đã có)
python manage.py train-model         # đọc bảng pair_feedback, đánh giá, ghi match_rf_model.pkl + model_meta.json
```

Cổng quản trị (thẻ Tổng quan) có khối "Mô hình ghép trận": thuật toán, số phiếu và nguồn dữ liệu huấn luyện, độ chính
xác, bảng so sánh với các cách làm đơn giản hơn và các yếu tố ảnh hưởng tới đề xuất. Giao diện người chơi chỉ hiện độ
phù hợp của từng phòng, không hiện chi tiết kỹ thuật. Bảng đánh giá đầy đủ (kèm mốc trần) in ra bằng
`python manage.py train-model --report`.

### 5.3. Mô hình

`RandomForestClassifier` của scikit-learn: 200 cây, độ sâu tối đa 8, tối thiểu 5 mẫu mỗi lá (20 khi dữ liệu có từ 5.000
dòng), `class_weight="balanced"`, `random_state=42`. Mô hình được lưu thành `match_rf_model.pkl`, kèm `model_meta.json`
ghi nguồn dữ liệu, cách đánh giá và các chỉ số.

### 5.4. Kết quả đánh giá hiện tại

3.000 phiếu mô phỏng của 20 tài khoản demo, tỷ lệ nhãn "muốn ghép" 41,8%, GroupKFold 5 phần theo người trả lời (số
trong bảng là trung bình của 5 phần):

| Mô hình | Accuracy | Precision | Recall | F1 | ROC-AUC |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Đoán theo lớp đa số | 0.5817 | 0.0000 | 0.0000 | 0.0000 | - |
| Luật một ngưỡng: chênh trình độ ≤ 0.5 | 0.8910 | 0.8772 | 0.8607 | 0.8684 | - |
| Hồi quy logistic | 0.9254 | 0.9143 | 0.9067 | 0.9105 | 0.9792 |
| **Random Forest** | **0.9313** | **0.9046** | **0.9343** | **0.9191** | **0.9826** |
| Quy tắc sinh nhãn, không nhiễu (mốc trần) | 0.9380 | 0.9287 | 0.9223 | 0.9254 | - |

Mức đóng góp của đặc trưng: `level_diff` 0.787, `distance_km` 0.117, `availability_overlap` 0.053, `purpose_match` 0.028,
`style_match` 0.015.

**Cách đọc các con số này.** Nhãn mô phỏng được sinh từ một quy tắc cộng nhiễu, nên:

- Mốc trần 93,80% là độ chính xác của chính quy tắc sinh nhãn; không mô hình nào vượt được vì phần còn lại là nhiễu.
- Random Forest đạt 93,13%, tức gần như học lại trọn quy tắc và cao hơn luật một ngưỡng (89,10%) cùng hồi quy logistic
  (92,54%).
- Các con số cho thấy quy trình dữ liệu → huấn luyện → đánh giá → phục vụ hoạt động đúng. Chúng **không** nói lên mức
  độ mô hình dự đoán đúng mong muốn của người chơi thật; kết luận đó cần nhãn khảo sát thật.

### 5.5. Đề xuất phòng đấu

Giao diện dùng mô hình để **đề xuất những phòng đấu đã được tạo**:

```text
Người xem A ──▶ các phòng đang tuyển người
            ──▶ với mỗi phòng: tạo 5 đặc trưng cho từng cặp (A, thành viên của phòng);
                khoảng cách tính từ vị trí của A tới sân của phòng
            ──▶ model.predict_proba cho từng cặp
            ──▶ độ phù hợp của phòng = trung bình các xác suất (0-100%)
            ──▶ phòng đạt từ 70% trở lên được gắn nhãn "mô hình đề xuất" và xếp trước
```

Ngưỡng 70% nằm ở `backend/app/core/matching_policy.py`: bộ phân loại tách hai lớp ở 50%, ngưỡng cao hơn chỉ giữ lại
những phòng mô hình đánh giá rõ ràng là phù hợp. `GET /api/v1/matches` trả `compatibility` và `is_recommended` cho từng
phòng; trang Ghép trận có ba mục: Phòng đề xuất, Tất cả phòng mở, Phòng của tôi. `GET /api/v1/ml/model-info` cho biết
ngưỡng đang dùng và các mục hồ sơ người xem còn thiếu để giao diện nhắc bổ sung.

API xếp hạng từng người chơi (`GET /api/v1/ml/recommend-partners`: lọc ứng viên có trình độ trong khoảng ±1.5, sắp theo
xác suất giảm dần) vẫn có ở backend nhưng giao diện không hiển thị danh sách này. Khi chưa có file mô hình, các API trả
kết quả rỗng kèm lý do, không tự đặt ra điểm số.

## 6. Kiểm thử

| Loại | Cách làm |
| :--- | :--- |
| **Kiểm thử tự động backend** | pytest trên một CSDL PostgreSQL riêng, schema dựng bằng chính các migration. Bao phủ bảo mật và phân quyền (mọi API không công khai đều đòi đăng nhập), vòng đời đơn, hủy và hoàn tiền, đơn tại quầy, webhook thanh toán, phòng đấu, gợi ý sân, mô hình ghép cặp |
| **Kiểm thử đồng thời** | Nhiều luồng thật cùng tranh một khung giờ, cùng gửi một giao dịch, cùng vào chỗ cuối của một phòng đấu; kiểm tra chỉ một luồng thành công và dữ liệu không sai lệch |
| **Kiểm thử phụ thuộc thời gian** | Đồng hồ nghiệp vụ được điều khiển trong test để kiểm tra hạn cọc 15 phút và các mốc hủy 12 giờ, 6 giờ |
| **Kiểm thử đầu-cuối qua trình duyệt** | `scripts/e2e_smoke.js`: 20 bước cho cả bốn vai trò, từ đặt sân, giả lập cọc, vé QR, phòng đấu do mô hình đề xuất, hủy và hoàn tiền tới quầy của nhân viên và cổng quản trị |
| **Đánh giá mô hình** | So sánh Random Forest với các mốc so sánh ở mục 5.4 |

Lệnh chạy và cách tổ chức: [README gốc](../README.md) và [backend/tests/README.md](../backend/tests/README.md).

## 7. Giới hạn và hướng phát triển

- Thu nhãn khảo sát thật và đánh giá lại mô hình ghép cặp; khi đó mới so sánh được với luật đơn giản một cách có ý nghĩa.
- Ngưỡng đề xuất phòng (70%) đang cố định; có thể hiệu chỉnh khi có nhãn thật.
- Trình độ DUPR do người chơi tự khai, chưa được xác thực.
- Triển khai nhiều tiến trình cần chuyển kênh WebSocket và tác vụ nền sang hạ tầng dùng chung (ví dụ Redis pub/sub).
- Hoàn tiền được nhân viên chuyển khoản thủ công rồi xác nhận trên hệ thống; chưa tự động qua cổng thanh toán.
