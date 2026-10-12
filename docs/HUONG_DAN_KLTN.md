# Hướng dẫn kỹ thuật cho khóa luận - PickleMatch2K

> **Đề tài**: Xây dựng hệ thống đặt sân Pickleball tích hợp gợi ý sân và AI ghép người chơi thông minh.

Tài liệu này mô tả **đúng những gì mã nguồn đang làm**: phạm vi chức năng, công thức gợi ý sân, mô hình ghép người chơi
và cách hệ thống được kiểm thử. Mọi con số ở mục 5 lấy từ `backend/app/ml/model_meta.json`; chạy
`python manage.py train-model --report` để tái lập.

## 1. Mục tiêu và phạm vi

| Tác nhân | Chức năng đã cài đặt |
| :--- | :--- |
| **Người chơi** | Đăng ký, đăng nhập, hồ sơ (trình độ DUPR tự khai, phong cách, mục đích, khu vực thường chơi); tìm sân theo vị trí; xem lịch trống theo thời gian thực; đặt sân và cọc 50% qua VietQR; vé QR; hủy đơn và yêu cầu hoàn tiền; đánh giá sân đã chơi; mở phòng đấu trên đơn đã cọc; tham gia phòng đấu do mô hình đề xuất |
| **Chủ sân** | Đăng ký cụm sân (chờ quản trị viên duyệt); sân con, bảng giá, giờ mở cửa, ảnh; tài khoản nhận tiền; nhân viên; quầy đặt sân; doanh thu |
| **Nhân viên** | Quầy đặt sân của cụm sân được phân công: tạo đơn tại quầy, check-in bằng mã hoặc QR, thu tiền, dời lịch, hủy, xác nhận hoàn tiền |
| **Quản trị viên** | Cổng riêng (cổng 3001): duyệt cụm sân, quản lý tài khoản, giám sát đơn đặt, sổ giao dịch, phòng đấu |

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
gia tới khi đủ số người; phòng tự đóng khi qua giờ hoặc khi đơn đặt bị hủy. Một người không thể ở trong hai phòng còn
hoạt động trùng giờ nhau (kể cả phòng do chính mình mở): muốn vào phòng khác thì phải rời phòng đang trùng giờ trước.

## 4. Gợi ý cụm sân

Cài đặt: `backend/app/services/venue_recommendation_service.py`, tham số ở `backend/app/core/recommendation_config.py`.
API: `GET /api/v1/recommendations/venues`.

> **Trạng thái:** thuật toán và API này vẫn hoạt động và có kiểm thử, nhưng giao diện web không còn gọi tới: trang chủ
> liệt kê cụm sân theo khoảng cách, và hồ sơ người chơi không còn lưu tiện ích ưa thích hay ngân sách. Hai tiêu chí
> giá-theo-ngân-sách và tiện ích vì vậy chỉ có dữ liệu khi yêu cầu API truyền `budget_max` và `amenity_ids`. Nếu báo cáo
> vẫn trình bày phần này, cần ghi rõ đây là thành phần backend chưa đưa lên giao diện.

### 4.1. Quy trình

1. **Lọc**: chỉ lấy cụm sân đang hoạt động; nếu người dùng đặt bán kính thì bỏ cụm sân nằm ngoài bán kính.
2. **Chuẩn hóa** từng tiêu chí về thang $[0, 1]$.
3. **Tính điểm tổng hợp** có trọng số rồi lấy Top-N.

### 4.2. Điểm tổng hợp

$$\text{Score} = \frac{\sum_{i \in K} w_i \, s_i}{\sum_{i \in K} w_i}$$

$K$ là tập tiêu chí **có dữ liệu**. Khi đủ cả năm tiêu chí, công thức trở thành:

$$\text{Score} = 0.30\,D + 0.25\,P + 0.20\,T + 0.15\,R + 0.10\,S$$

Tiêu chí thiếu dữ liệu (chưa biết vị trí người dùng, yêu cầu không nêu tiện ích mong muốn) bị loại khỏi phép tính và các trọng số
còn lại được chuẩn hóa lại; hệ thống không gán một điểm "trung tính" tự đặt ra.

### 4.3. Chuẩn hóa từng tiêu chí

| Tiêu chí | Trọng số | Cách tính |
| :--- | :---: | :--- |
| $D$ - khoảng cách | 0.30 | $D = \max(0,\ 1 - d / 20)$ với $d$ là khoảng cách Haversine (km) từ người dùng tới sân; từ 20 km trở lên được 0 điểm |
| $P$ - giá | 0.25 | Có ngân sách $B$: $P = 1$ nếu giá $\le B$, giảm tuyến tính về 0 khi giá đạt $1.5B$. Chưa có ngân sách: min-max trên các sân ứng viên (rẻ nhất 1, đắt nhất 0) |
| $T$ - giờ trống | 0.20 | Tỷ lệ khung giờ còn đặt được trong ngày (hoặc trong khoảng giờ người dùng chọn), không tính khung đã qua |
| $R$ - đánh giá | 0.15 | Trung bình Bayes chia cho 5 (xem dưới) |
| $S$ - tiện ích | 0.10 | Tỷ lệ tiện ích người dùng yêu cầu mà sân đáp ứng |

Giá dùng để chấm là giá trung bình của các khung giờ còn trống trong ngày đang xét (hoặc của mọi khung giờ trong ngày
khi sân đã kín lịch).

**Trung bình Bayes cho đánh giá.** Với $v$ là số đánh giá và $\bar{r}$ là điểm trung bình của sân:

$$R_{\text{bayes}} = \frac{v\,\bar{r} + m\,C}{v + m}, \qquad m = 5$$

$C$ là điểm trung bình toàn hệ thống (chính $C$ cũng được kéo về mốc 4.0 khi tổng số đánh giá còn ít). Nhờ đó một sân
mới có hai đánh giá 5 sao không vượt lên trên sân có năm mươi đánh giá trung bình 4.7.

### 4.4. Ví dụ

Đủ năm tiêu chí, $D = 0.9,\ P = 0.8,\ T = 1.0,\ R = 0.85,\ S = 0.7$:

$$\text{Score} = 0.30(0.9) + 0.25(0.8) + 0.20(1.0) + 0.15(0.85) + 0.10(0.7) = 0.8675$$

Cùng sân đó khi yêu cầu không nêu tiện ích mong muốn (bỏ $S$, tổng trọng số còn 0.90):

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
| `purpose_match` | 1 nếu cùng mục đích chơi (giao lưu, luyện tập, thi đấu), ngược lại 0 |
| `style_match` | 1 nếu cùng phong cách hoặc một bên chơi toàn diện, ngược lại 0 |
| `age_diff` | Chênh lệch tuổi tính theo năm (tuổi lấy từ ngày sinh trong hồ sơ), chặn trên 50. Thiếu ngày sinh của một bên thì dùng giá trị trung tính 10 và báo hồ sơ còn thiếu |

Cùng một module tạo đặc trưng cho huấn luyện, khảo sát và suy luận, nên dữ liệu huấn luyện và dữ liệu phục vụ luôn
nhất quán. Thiếu trình độ của một trong hai người thì không dự đoán.

Tuổi chỉ được dùng để tính độ phù hợp: người chơi không nhìn thấy ngày sinh hay tuổi của nhau, và các API cũng không
trả về chênh lệch tuổi của một cặp.

Thời gian không phải là đặc trưng. Mỗi phòng đấu gắn với một đơn đặt sân nên đã có ngày giờ cố định ghi ngay trên thẻ
phòng; người chơi tự chọn phòng theo giờ mình đi được, mô hình chỉ trả lời câu hỏi "những người trong phòng có hợp
với mình không".

### 5.2. Dữ liệu huấn luyện

Dữ liệu huấn luyện nằm trong bảng `pair_feedback` của CSDL. Mỗi dòng là một "phiếu ghép cặp": 5 đặc trưng của một cặp,
người trả lời, nhãn muốn ghép (1) hay không (0), và cột `source` ghi nguồn. Hệ thống hiện dùng dữ liệu tự nạp; thu
thập câu trả lời của người chơi thật là hướng phát triển:

1. **Phiếu ghép cặp mô phỏng** (`source = simulated`, **đang dùng**): 10.000 phiếu nạp bằng
   `python manage.py seed --feedback`. Mỗi tài khoản trong 20 tài khoản người chơi demo "trả lời" 500 phiếu. Hồ sơ ứng
   viên được sinh bằng đúng hàm mà trang khảo sát dùng (trải các mức chênh trình độ, khoảng cách và tuổi; chênh trình
   độ nhỏ xuất hiện nhiều hơn chênh lớn). Câu trả lời được sinh từ một quy tắc viết tay (`synthetic_rule_score`, bảng
   bên dưới) cộng nhiễu Gauss $\sigma = 0.15$. Nhiễu mô tả sự dao động giữa những người trả lời: một cặp hợp nhau được
   trả lời "muốn ghép" với xác suất cao nhưng không phải lúc nào cũng vậy. Hạt giống ngẫu nhiên cố định nên cài ở đâu
   cũng ra cùng một bộ dữ liệu. Đây là dữ liệu mô phỏng để minh họa quy trình, **không phải** câu trả lời của người
   chơi thật.
2. **Nhãn khảo sát thật** (`source = survey`, **hướng phát triển**): trang `/survey` cho người chơi trả lời về các hồ sơ
   ứng viên giả định xoay quanh hồ sơ của chính mình. Các câu trả lời được lưu riêng và chưa tham gia huấn luyện; khi
   có từ 300 nhãn thật trở lên, lệnh huấn luyện tự chuyển sang chỉ học từ các nhãn này. Câu trả lời thu trước khi có
   tiêu chí tuổi không có chênh lệch tuổi nên không được tính.
3. **Dữ liệu tổng hợp trong bộ nhớ**: 60.000 cặp sinh từ cùng quy tắc, chỉ dùng khi CSDL chưa có đủ 300 phiếu.

Quy tắc sinh câu trả lời mô phỏng: điểm của một cặp bằng 0,50 cộng điểm của năm tiêu chí trong bảng dưới, cộng thêm
nhiễu; từ 0,50 trở lên là "muốn ghép". Các mức điểm được chọn để mô hình học ra mức đóng góp xấp xỉ: trình độ 55%,
khoảng cách 20%, mục đích 10%, phong cách 9%, tuổi 7%.

| Tiêu chí | Điểm cộng / trừ |
| :--- | :--- |
| Chênh trình độ | ≤ 0,25: +0,19 · ≤ 0,5: +0,11 · ≤ 1,0: −0,06 · ≤ 1,5: −0,34 · lớn hơn: −0,49 |
| Khoảng cách | ≤ 3 km: +0,11 · ≤ 8 km: +0,04 · ≤ 15 km: −0,07 · xa hơn: −0,20 |
| Mục đích chơi | cùng: +0,12 · khác: −0,09 |
| Phong cách | hợp: +0,11 · không hợp: −0,07 |
| Chênh lệch tuổi | ≤ 5: +0,08 · ≤ 10: +0,03 · ≤ 20: −0,05 · lớn hơn: −0,13 |

Chênh trình độ từ 1,5 trở lên bị trừ nặng, để các tiêu chí còn lại không bù được một khoảng cách trình độ lớn.

Dữ liệu lấy từ CSDL (nguồn 1 và 2) được đánh giá bằng **GroupKFold theo người trả lời**, để phiếu của cùng một người
không nằm ở cả tập huấn luyện lẫn tập kiểm tra.

Quy trình đầy đủ:

```text
python manage.py seed --feedback                # nạp phiếu mô phỏng vào bảng pair_feedback (bỏ qua nếu đã có)
python manage.py seed --feedback --regenerate   # thay phiếu mô phỏng cũ sau khi đổi quy tắc sinh nhãn
python manage.py train-model                    # đọc bảng pair_feedback, đánh giá, ghi match_rf_model.pkl + model_meta.json
```

Giao diện (cổng người chơi lẫn cổng quản trị) chỉ hiện kết quả: độ phù hợp của từng phòng và mục Phòng Đề Xuất, không
hiện chi tiết kỹ thuật. Thông tin về mô hình đang chạy (nguồn dữ liệu, số phiếu, cách đánh giá, các chỉ số) xem ở
`GET /api/v1/ml/model-info` (qua trang `/docs`, cần đăng nhập) hoặc file `backend/app/ml/model_meta.json`; bảng đánh giá
đầy đủ in ra bằng `python manage.py train-model --report`.

### 5.3. Mô hình

`RandomForestClassifier` của scikit-learn: 200 cây, độ sâu tối đa 8, mỗi lá gom ít nhất 1% số phiếu huấn luyện (100
phiếu với bộ 10.000 phiếu, không bao giờ dưới 25), `random_state=42`. Xác suất của mô hình được hiện cho người chơi
dưới dạng độ phù hợp, nên rừng được cấu hình để xác suất đó là một tỉ lệ đáng tin: lá phải gom đủ nhiều phiếu (lá chỉ
vài phiếu dễ cho ra 0% hoặc 100%) và hai lớp không bị cân lại trọng số (cân lại làm xác suất lệch khỏi tỉ lệ "muốn
ghép" có thật trong dữ liệu). Mô hình được lưu thành `match_rf_model.pkl`, kèm `model_meta.json` ghi nguồn dữ liệu,
cách đánh giá và các chỉ số.

Cách mô hình tính độ phù hợp của một cặp:

1. Mỗi cây trong 200 cây được dựng từ một mẫu ngẫu nhiên (lấy có hoàn lại) của các phiếu, và ở mỗi nút chỉ xét ngẫu
   nhiên một phần đặc trưng, nên các cây khác nhau.
2. Một cây là chuỗi câu hỏi dạng ngưỡng trên 5 đặc trưng (ví dụ "chênh trình độ ≤ 0.75?", "sân cách ≤ 8.05 km?"). Đi hết
   các câu hỏi, cặp đang xét rơi vào một lá; lá ghi tỉ lệ phiếu "muốn ghép" trong nhóm phiếu huấn luyện giống cặp đó.
3. Rừng lấy trung bình tỉ lệ của 200 lá (`predict_proba`). Trung bình đó nhân 100 là độ phù hợp của cặp.

Rừng đang dùng: mỗi cây có 36 đến 51 lá (trung bình 43), sâu tối đa 8 tầng, mỗi nút xét 2 trong 5 đặc trưng. Câu hỏi
đầu tiên của 78 cây là về chênh lệch trình độ, 57 cây về khoảng cách, 44 cây về mục đích chơi, 17 cây về phong cách và
4 cây về tuổi.

Random Forest là mô hình duy nhất của dự án: hệ thống không huấn luyện, không phục vụ và không so sánh với mô hình nào
khác; khi thiếu file mô hình, API trả kết quả rỗng chứ không thay bằng công thức khác.

### 5.4. Kết quả đánh giá hiện tại

10.000 phiếu mô phỏng của 20 tài khoản demo, tỷ lệ nhãn "muốn ghép" 40,8%. Random Forest được đánh giá bằng GroupKFold
5 phần theo người trả lời: mỗi lượt học từ phiếu của 16 người và đo trên phiếu của 4 người còn lại (số trong bảng là
trung bình của 5 lượt):

| Chỉ số | Random Forest | Ý nghĩa |
| :--- | :---: | :--- |
| Accuracy | 0.8531 | Tỉ lệ phiếu mô hình đoán đúng câu trả lời |
| Precision | 0.8340 | Trong các cặp mô hình cho là hợp, tỉ lệ cặp được trả lời "muốn ghép" |
| Recall | 0.7968 | Trong các cặp được trả lời "muốn ghép", tỉ lệ cặp mô hình nhận ra |
| F1 | 0.8147 | Trung bình điều hòa của precision và recall |
| ROC-AUC | 0.9305 | Khả năng xếp cặp hợp lên trên cặp không hợp (1.0 là xếp đúng hoàn toàn) |

Mức đóng góp của đặc trưng trong mô hình đã huấn luyện:

| Tiêu chí | Mức đóng góp | Mục tiêu khi thiết kế quy tắc |
| :--- | :---: | :---: |
| Trình độ (`level_diff`) | 54,6% | 55% |
| Khoảng cách (`distance_km`) | 19,5% | 20% |
| Mục đích chơi (`purpose_match`) | 10,1% | 10% |
| Phong cách (`style_match`) | 8,5% | 9% |
| Tuổi (`age_diff`) | 7,3% | 7% |

**Cách đọc các con số này.**

- Câu trả lời mô phỏng có dao động ngẫu nhiên: 14,4% số phiếu có nhãn khác với quy tắc sinh nhãn. Phần dao động này
  không học được, nên độ chính xác tối đa có thể đạt trên bộ dữ liệu này là 85,6%. Random Forest đạt 85,31%, tức gần
  như học lại trọn quy tắc.
- Mức đóng góp là kết quả đo trên mô hình (độ giảm tạp chất Gini mà mỗi đặc trưng mang lại), không phải con số gán
  tay; nó khớp mục tiêu vì các mức điểm của quy tắc sinh nhãn được chọn theo mục tiêu đó.
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

Độ phù hợp là một ước lượng nên không bao giờ là 100%: với mô hình hiện tại, xác suất của một cặp nằm trong khoảng
từ gần 0% đến 98,7%. Vài giá trị điển hình (cùng lứa = lệch không quá 5 tuổi):

| Cặp người chơi | Độ phù hợp |
| :--- | :---: |
| Cùng trình độ, sân cách 6 km, cùng mục đích, hợp phong cách, cùng lứa | 96% |
| Như trên nhưng khác mục đích | 92% |
| Như trên nhưng không hợp phong cách | 91% |
| Như trên nhưng lệch 30 tuổi | 85% |
| Như trên nhưng sân cách 25 km | 83% |
| Cùng trình độ, sân cách 6 km, khác mục đích, không hợp phong cách, cùng lứa | 71% |
| Lệch 1,0 trình độ, sân cách 2 km, cùng mục đích, hợp phong cách, cùng lứa | 91% |
| Lệch 1,0 trình độ, sân cách 6 km, khác mục đích, không hợp phong cách, cùng lứa | 30% |
| Lệch 1,5 trình độ, sân cách 2 km, cùng mục đích, hợp phong cách, cùng lứa | 36% |
| Lệch 2,0 trình độ, sân cách 6 km, khác mục đích, không hợp phong cách | 4% |

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
| **Kiểm thử đầu-cuối qua trình duyệt** | `scripts/e2e_smoke.js`: 22 bước cho cả bốn vai trò, từ đặt sân, giả lập cọc, vé QR, phòng đấu do mô hình đề xuất, hủy và hoàn tiền tới quầy của nhân viên và cổng quản trị |
| **Đánh giá mô hình** | Random Forest được đánh giá bằng GroupKFold theo người trả lời; kết quả ở mục 5.4 |

Lệnh chạy và cách tổ chức: [README gốc](../README.md) và [backend/tests/README.md](../backend/tests/README.md).

## 7. Giới hạn và hướng phát triển

- Thu thập câu trả lời của người chơi thật (trang `/survey` đã sẵn sàng) rồi huấn luyện và đánh giá lại Random Forest
  trên dữ liệu đó.
- Ngưỡng đề xuất phòng (70%) đang cố định; có thể hiệu chỉnh khi có nhãn thật.
- Trình độ DUPR do người chơi tự khai, chưa được xác thực.
- Triển khai nhiều tiến trình cần chuyển kênh WebSocket và tác vụ nền sang hạ tầng dùng chung (ví dụ Redis pub/sub).
- Hoàn tiền được nhân viên chuyển khoản thủ công rồi xác nhận trên hệ thống; chưa tự động qua cổng thanh toán.
