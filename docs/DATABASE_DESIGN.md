# Thiết kế cơ sở dữ liệu - PickleMatch2K

Hệ thống dùng **PostgreSQL 17**. Schema được định nghĩa bằng model SQLAlchemy (`backend/app/models/`) và chỉ thay đổi
qua migration Alembic (`backend/alembic/versions/`). Một ca kiểm thử so sánh CSDL sau migration với model để bảo đảm
hai bên luôn khớp nhau.

Tài liệu này mô tả schema ở revision **0004**.

## 1. Sơ đồ quan hệ

```text
users ──1:1── player_profiles
  │   ──1:1── owner_profiles
  │   ──1:1── staff_profiles ──N:1── venues
  │
  ├──1:N── venues ──1:N── courts
  │           ├──1:N── operating_hours        (mỗi thứ trong tuần một dòng)
  │           ├──1:N── price_rules            (BASE / PEAK / WEEKEND)
  │           ├──1:N── reviews                (mỗi người một đánh giá cho mỗi cụm sân)
  │           └──N:M── amenities              (qua venue_amenities)
  │
  ├──1:N── bookings ──1:N── booking_details   (mỗi dòng = một sân, một khung giờ 60 phút)
  │           └──1:N── payment_transactions   (sổ giao dịch: cọc, phần còn lại, hoàn tiền)
  │
  ├──1:N── matches ──1:N── match_participants (phòng đấu gắn với một đơn đặt đã cọc)
  │
  └──1:N── pair_feedback                      (nhãn khảo sát cho mô hình ghép cặp)
```

## 2. Các bảng

Ký hiệu: **PK** khóa chính, **FK** khóa ngoại, **U** duy nhất, **NN** không được rỗng.

### 2.1. Tài khoản và hồ sơ

**`users`**

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `id` | INTEGER | PK |
| `email` | VARCHAR | U, NN |
| `password_hash` | VARCHAR | NN - bcrypt |
| `role` | VARCHAR | NN - `PLAYER`, `OWNER`, `STAFF`, `ADMIN` |
| `is_active` | BOOLEAN | NN - tài khoản bị khóa không đăng nhập và không gọi API được |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**`player_profiles`** (PK = `user_id` → `users.id`)

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `full_name`, `phone`, `avatar_url`, `date_of_birth` | | Thông tin cá nhân |
| `skill_level` | FLOAT | Trình độ DUPR tự khai |
| `play_style` | VARCHAR | Phong cách chơi |
| `purpose` | VARCHAR | `recreational`, `practice`, `competitive` |
| `availability` | VARCHAR | Danh sách khung rảnh trong tuần (JSON), ví dụ `sat_morning` |
| `preferred_amenities` | VARCHAR | Danh sách mã tiện ích ưa thích (JSON) |
| `budget_max` | FLOAT | Ngân sách tối đa mỗi giờ (VNĐ) |
| `latitude`, `longitude` | FLOAT | Vị trí thường chơi |
| `matches_played`, `matches_won` | INTEGER | |

**`owner_profiles`** (PK = `user_id`): `full_name`, `phone`, `company_name`, `bank_account` (tài khoản nhận tiền của chủ sân).

**`staff_profiles`** (PK = `user_id`): `venue_id` → `venues.id` (cụm sân được phân công), `full_name`, `phone`.

### 2.2. Cụm sân

**`venues`**

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `id` | INTEGER | PK |
| `owner_id` | INTEGER | FK → `users.id`, NN |
| `name`, `address` | VARCHAR | NN |
| `description`, `google_maps_url` | VARCHAR | |
| `latitude`, `longitude` | FLOAT | Tọa độ dùng để tính khoảng cách |
| `image_url` | VARCHAR | Ảnh đại diện |
| `images` | VARCHAR | Danh sách ảnh (JSON) |
| `status` | VARCHAR | `PENDING` (chờ duyệt), `ACTIVE`, `MAINTENANCE`, `INACTIVE`, `REJECTED` |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**`courts`**: `id`, `venue_id` (FK, NN), `name` (NN), `status` (`ACTIVE`, `MAINTENANCE`), `price` (giá riêng của sân, có thể rỗng).

**`operating_hours`**: `venue_id`, `day_of_week` (0 = thứ Hai … 6 = Chủ nhật), `open_time`, `close_time`.
Duy nhất theo (`venue_id`, `day_of_week`).

**`price_rules`**: `venue_id`, `rule_type` (`BASE`, `PEAK`, `WEEKEND`), `start_time`, `end_time`, `price` (VNĐ/giờ).

**`amenities`**: `id`, `name` (U), `icon`. **`venue_amenities`**: (`venue_id`, `amenity_id`) là khóa chính.

**`reviews`**: `user_id`, `venue_id`, `rating`, `comment`, `created_at`. Duy nhất theo (`user_id`, `venue_id`).
Chỉ người chơi có đơn đặt trực tuyến đã hoàn tất ở cụm sân mới được đánh giá (kiểm tra ở tầng nghiệp vụ).

### 2.3. Đặt sân

**`bookings`**

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `id` | INTEGER | PK |
| `booking_code` | VARCHAR(32) | U - `PK2K` + 6 chữ số, cấp từ sequence `booking_code_seq` |
| `user_id` | INTEGER | FK → `users.id`, NN - người đặt (với đơn tại quầy là nhân viên hoặc chủ sân tạo đơn) |
| `source` | VARCHAR | NN - `ONLINE` (người chơi tự đặt), `DESK` (tạo tại quầy) |
| `guest_name`, `guest_phone` | VARCHAR | Khách vãng lai của đơn tại quầy |
| `total_price`, `deposit_amount`, `paid_amount` | FLOAT | Tổng tiền, tiền cọc phải trả, số đã trả |
| `status` | VARCHAR | `PENDING`, `CONFIRMED`, `CHECKED_IN`, `COMPLETED`, `NO_SHOW`, `CANCELLED`, `EXPIRED` |
| `payment_status` | VARCHAR | `UNPAID`, `PARTIALLY_PAID`, `DEPOSIT_PAID`, `FULLY_PAID` |
| `expires_at` | TIMESTAMPTZ | Hạn thanh toán cọc của đơn `PENDING` |
| `checked_in_at`, `checked_in_by_id` | | Thời điểm và người check-in |
| `cancelled_at`, `cancelled_by_id`, `cancel_reason` | | Thông tin hủy |
| `refund_status` | VARCHAR | `PENDING`, `COMPLETED`, `REJECTED` hoặc rỗng |
| `refund_amount`, `refund_bank_account`, `refund_bank_name`, `refund_account_holder`, `refund_reason` | | Yêu cầu hoàn tiền |
| `refunded_at`, `refunded_by_id` | | Thời điểm và người xác nhận đã hoàn |
| `created_at`, `updated_at` | TIMESTAMPTZ | |

**`booking_details`** - mỗi dòng là một khung giờ trên một sân

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `id` | INTEGER | PK |
| `booking_id` | INTEGER | FK → `bookings.id`, NN |
| `court_id` | INTEGER | FK → `courts.id`, NN |
| `date` | DATE | NN |
| `start_time`, `end_time` | TIME | NN |
| `price` | FLOAT | NN - giá của khung giờ tại thời điểm đặt |
| `is_active` | BOOLEAN | NN - `false` khi đơn bị hủy hoặc hết hạn, khung giờ được trả lại |

**`payment_transactions`** - sổ giao dịch: mỗi lần thu hoặc hoàn tiền là một dòng mới

| Cột | Kiểu | Ghi chú |
| :--- | :--- | :--- |
| `id` | INTEGER | PK |
| `transaction_code` | VARCHAR(32) | U - `TX` + 6 chữ số, cấp từ sequence `transaction_code_seq` |
| `booking_id` | INTEGER | FK → `bookings.id`, NN |
| `kind` | VARCHAR | NN - `DEPOSIT` (cọc), `BALANCE` (phần còn lại), `REFUND` (hoàn tiền) |
| `method` | VARCHAR | NN - `BANK_TRANSFER`, `CASH` |
| `gateway` | VARCHAR | NN - nguồn ghi nhận |
| `amount_in` | FLOAT | NN - số tiền của giao dịch |
| `reference_number` | VARCHAR | Mã tham chiếu của ngân hàng / SePay |
| `account_number`, `transaction_content`, `raw_payload` | VARCHAR | Dữ liệu gốc từ webhook |
| `status` | VARCHAR | NN |
| `created_by_id` | INTEGER | FK → `users.id` - nhân viên ghi nhận (giao dịch tại quầy) |
| `transaction_date`, `created_at` | TIMESTAMPTZ | |

Mỗi dòng sổ được ghi cùng lúc với việc cộng `bookings.paid_amount` (trong một giao dịch CSDL); `payment_status` được
suy ra từ `paid_amount` so với tiền cọc và tổng tiền. Doanh thu trên các bảng tổng quan được cộng từ sổ này.

### 2.4. Phòng đấu

**`matches`**: `id`, `creator_id` (FK → `users.id`), `venue_id`, `court_id`, `booking_id` (FK → `bookings.id`, đơn đặt mà
phòng đấu diễn ra trên đó), `date`, `start_time`, `end_time`, `required_skill`, `num_players`, `purpose`,
`status` (`OPEN`, `FULL`, `CANCELLED`, `COMPLETED`), `notes`, `created_at`, `updated_at`.

**`match_participants`**: `match_id`, `user_id`, `status` (`INVITED`, `ACCEPTED`, `REJECTED`), `joined_at`.
Duy nhất theo (`match_id`, `user_id`).

### 2.5. Nhãn cho mô hình ghép cặp

**`pair_feedback`**: `rater_id` (FK → `users.id`), `source`, năm đặc trưng của cặp được hỏi (`level_diff`, `distance_km`,
`availability_overlap`, `purpose_match`, `style_match`), `label` (1 = muốn ghép, 0 = không), `created_at`.
Bảng chỉ lưu đặc trưng của cặp, không lưu danh tính người được so sánh.

## 3. Ràng buộc bảo vệ dữ liệu

Các quy tắc quan trọng được ép ngay trong PostgreSQL, nên vẫn đúng khi nhiều yêu cầu đến cùng lúc.

### 3.1. Không thể đặt trùng một khung giờ

```sql
-- Một khung giờ còn hiệu lực trên một sân chỉ thuộc về một đơn
CREATE UNIQUE INDEX uq_booking_details_active_slot
    ON booking_details (court_id, date, start_time) WHERE is_active;

-- Hai dòng còn hiệu lực của cùng một sân không được có khoảng thời gian giao nhau
CREATE EXTENSION IF NOT EXISTS btree_gist;
ALTER TABLE booking_details ADD CONSTRAINT ex_booking_details_no_overlap
    EXCLUDE USING gist (court_id WITH =, tsrange("date" + start_time, "date" + end_time) WITH &&)
    WHERE (is_active);

ALTER TABLE booking_details ADD CONSTRAINT ck_booking_details_time_order CHECK (end_time > start_time);
```

Khi đơn bị hủy hoặc hết hạn, `is_active` chuyển thành `false`: lịch sử được giữ lại còn khung giờ đặt lại được.
Bộ kiểm thử cho nhiều luồng thật cùng tranh một khung giờ và xác nhận chỉ một luồng thành công.

### 3.2. Một giao dịch ngân hàng chỉ được ghi một lần

```sql
CREATE UNIQUE INDEX uq_payment_transactions_reference
    ON payment_transactions (reference_number)
    WHERE reference_number IS NOT NULL AND reference_number <> '';
```

SePay có thể gửi lại cùng một webhook; lần gửi lặp không tạo thêm giao dịch và không cộng tiền hai lần.

### 3.3. Các ràng buộc duy nhất khác

| Ràng buộc | Ý nghĩa |
| :--- | :--- |
| `uq_match_participants_match_user` | Một người chỉ tham gia một phòng đấu một lần |
| `uq_operating_hours_venue_day` | Mỗi cụm sân có một dòng giờ mở cửa cho mỗi thứ |
| `uq_reviews_user_venue` | Mỗi người một đánh giá cho mỗi cụm sân |
| `ix_bookings_booking_code`, `ix_payment_transactions_transaction_code` | Mã đơn và mã giao dịch không trùng |
| `ix_users_email` | Email không trùng |

### 3.4. Mã đơn và mã giao dịch

Hai sequence `booking_code_seq` và `transaction_code_seq` cấp số tăng dần, nên mã không trùng kể cả khi nhiều đơn được
tạo cùng lúc.

## 4. Chỉ mục phục vụ truy vấn

| Chỉ mục | Phục vụ |
| :--- | :--- |
| `ix_booking_details_court_date (court_id, date)` | Dựng lịch trống của một sân theo ngày |
| `ix_bookings_user_id`, `ix_bookings_status`, `ix_bookings_payment_status`, `ix_bookings_refund_status` | Danh sách đơn theo người đặt và theo trạng thái |
| `ix_payment_transactions_booking_id`, `ix_payment_transactions_reference_number` | Sổ giao dịch của một đơn, khớp webhook |
| `ix_venues_owner_id`, `ix_courts_venue_id`, `ix_operating_hours_venue_id`, `ix_price_rules_venue_id` | Dữ liệu của một cụm sân |
| `ix_matches_date`, `ix_matches_status`, `ix_matches_venue_id`, `ix_matches_booking_id` | Danh sách phòng đấu |
| `ix_pair_feedback_rater_id` | Nhóm nhãn theo người trả lời khi đánh giá mô hình |

## 5. Lịch sử schema

| Revision | Nội dung |
| :--- | :--- |
| `0001` | Schema gốc, đúng với các CSDL được tạo trước khi dự án dùng Alembic |
| `0002` | Chỉnh các sai lệch của CSDL cũ so với model (chỉ mục duy nhất của mã đơn / mã giao dịch, `users.is_active` bắt buộc) |
| `0003` | Lõi đặt sân mới: nguồn đơn và khách vãng lai, tiền cọc / đã trả, hạn thanh toán, check-in, hủy; `is_active` và các ràng buộc chống đặt trùng; sổ giao dịch theo loại và hình thức; phòng đấu gắn với đơn; hồ sơ ghép cặp (mục đích, khung rảnh, tiện ích ưa thích, ngân sách). Dữ liệu cũ được chuyển đổi tại chỗ và migration dừng lại nếu phát hiện đơn còn hiệu lực bị trùng giờ |
| `0004` | Bảng `pair_feedback` |

Nâng cấp một CSDL cũ: `python manage.py migrate` (tự sao lưu trước, xem README gốc).

## 6. Điểm cần lưu ý

- Số tiền dùng kiểu `FLOAT`. Mọi giá trị là số nguyên VNĐ và phép so tiền chuyển khoản cho phép sai số 1 VNĐ;
  chuyển sang kiểu số nguyên là hướng cải thiện về sau.
- Các danh sách (`availability`, `preferred_amenities`, `images`) lưu dạng chuỗi JSON trong cột `VARCHAR`.
- Dữ liệu chuyển đổi từ phiên bản cũ: hệ thống cũ chỉ đánh dấu trạng thái thanh toán mà không ghi đủ sổ giao dịch, nên
  migration `0003` suy ra `paid_amount` của đơn cũ từ trạng thái đó. Với các đơn này, `paid_amount` có thể lớn hơn tổng
  các dòng sổ, và doanh thu trên bảng tổng quan (cộng từ sổ) không gồm phần chênh. Đơn tạo từ phiên bản hiện tại
  không có sai lệch này.
- Thời điểm lưu ở UTC (`TIMESTAMPTZ`); ngày và giờ chơi (`date`, `start_time`, `end_time`) là giờ Việt Nam.
