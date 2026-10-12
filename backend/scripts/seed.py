"""
Nạp bộ dữ liệu demo của đồ án PickleMatch2K.

    python scripts/seed.py               # nạp khi CSDL còn trống (dừng nếu đã có dữ liệu)
    python scripts/seed.py --if-empty    # đã có dữ liệu thì bỏ qua, không báo lỗi (dùng cho Docker)
    python scripts/seed.py --reset       # XÓA toàn bộ dữ liệu rồi nạp lại (phải xác nhận, hoặc thêm --yes)
    python scripts/seed.py --preferences # chỉ bổ sung mục đích chơi và ngày sinh mẫu cho các tài khoản demo đang để trống
    python scripts/seed.py --feedback    # chỉ nạp phiếu ghép cặp MÔ PHỎNG để huấn luyện mô hình từ CSDL
                                         # (thêm --regenerate: sinh lại các phiếu mô phỏng theo quy tắc hiện tại)
    python scripts/seed.py --matches     # nạp THÊM người chơi và phòng đấu mẫu để thử chức năng ghép trận
    python scripts/seed.py --activity    # nạp THÊM hoạt động mẫu cho cụm sân mới chưa có đơn nào (--venue ID: chỉ một cụm sân)

Nội dung: 8 tiện ích, 3 cụm sân, 33 tài khoản khai báo ngay trong file này (VENUES, PLAYERS)
(1 admin, 3 chủ sân, 9 nhân viên, 20 người chơi) cùng đơn đặt sân, giao dịch, phòng đấu và đánh giá mẫu,
và 10.000 phiếu ghép cặp mô phỏng (ghi rõ nguồn "simulated") làm dữ liệu huấn luyện mô hình.

Đơn đặt, thanh toán, check-in, hủy và phòng đấu được tạo bằng chính các hàm nghiệp vụ của ứng dụng
(đồng hồ nghiệp vụ được "tua" về quá khứ để có dữ liệu lịch sử), nên dữ liệu mẫu luôn hợp lệ theo
các ràng buộc hiện hành. Mọi ngày tháng tính tương đối so với ngày chạy script.

MẬT KHẨU DEMO dùng chung là 123456: chỉ dành cho môi trường phát triển/bảo vệ đồ án.
"""
import json
import random
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts._common import ensure_schema, rebuild_empty_schema  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal, engine  # noqa: E402
from app.ml.features import FEATURE_NAMES, ProfileView, canonical_style, pair_features  # noqa: E402
from app.models.booking import Booking, BookingDetail, BookingSource  # noqa: E402
from app.models.match import Match, MatchParticipant  # noqa: E402
from app.models.ml import SIMULATED_SOURCE, PairFeedback  # noqa: E402
from app.models.payment import PaymentKind, PaymentMethod, PaymentTransaction  # noqa: E402
from app.models.user import StaffProfile, User, UserRole  # noqa: E402
from app.models.venue import Amenity, Court, OperatingHour, PriceRule, Review, Venue  # noqa: E402
from app.schemas.match import MatchCreate  # noqa: E402
from app.services import booking_service, ledger, match_service, ml_service  # noqa: E402
from app.services.availability_service import get_operating_hour, iter_day_slots  # noqa: E402
from app.services.booking_service import SlotRequest  # noqa: E402
from app.services.user_service import create_user  # noqa: E402
from app.utils import timeutils  # noqa: E402
from app.utils.timeutils import today_vn, vn_datetime  # noqa: E402

DEMO_PASSWORD = "123456"

AMENITIES = [
    ("led", "Đèn LED chống lóa 500 Lux", "Lightbulb"),
    ("indoor", "Sân có mái che / Trong nhà", "Umbrella"),
    ("rental", "Cho thuê vợt & bóng Franklin X-40", "Package"),
    ("canteen", "Căng tin & Nước giải khát thể thao", "Coffee"),
    ("parking", "Bãi đỗ xe ô tô & xe máy miễn phí", "Car"),
    ("shower", "Phòng thay đồ & Tắm nóng lạnh", "Shower"),
    ("lounge", "Phòng nghỉ điều hòa máy lạnh", "Wind"),
    ("coach", "HLV đào tạo & Trọng tài DUPR", "Award"),
]

_CLOUD = "https://res.cloudinary.com/dwmtdx9ly/image/upload"


@dataclass(frozen=True)
class VenueSeed:
    key: str
    name: str
    address: str
    lat: float
    lng: float
    maps: str
    images: Tuple[str, ...]
    desc: str
    courts: int
    open: time
    close: time
    base: int
    peak: int
    weekend: int
    amenities: Tuple[str, ...]  # tiện ích mẫu suy ra từ phần mô tả; chủ sân chỉnh lại trong cổng quản lý
    owner: Tuple[str, str, str, str]  # email, họ tên, điện thoại, tên đơn vị
    staff: Tuple[Tuple[str, str, str], ...]  # email, họ tên, điện thoại


VENUES = [
    VenueSeed(
        key="rudal",
        name="RUDAL Pickleball & Academy",
        address="28 Đường số 12, Khu phố 3, phường An Khánh, TP. Hồ Chí Minh",
        lat=10.7901357, lng=106.7321982,
        maps="https://maps.app.goo.gl/qNTCu1dJhADjvU836",
        images=(
            f"{_CLOUD}/v1791118272/picklematch2k/venues/v1_e24bf86c.webp",
            f"{_CLOUD}/v1791118304/picklematch2k/venues/v1_848e2155.jpg",
            f"{_CLOUD}/v1791118328/picklematch2k/venues/v1_959b8776.jpg",
        ),
        desc="Cụm 6 sân tại khu vực An Khánh chuẩn thi đấu quốc tế. Không gian rộng rãi, thoáng mát "
             "cùng hệ thống chiếu sáng LED hiện đại.",
        courts=6, open=time(5, 0), close=time(23, 0),
        base=160000, peak=230000, weekend=160000,
        amenities=("led", "rental", "canteen", "parking", "shower", "coach"),
        owner=("owner_rudal@pickleball.vn", "Nguyễn Rudal (Chủ Sân)", "0938375999", "RUDAL Pickleball & Academy Vietnam"),
        staff=(
            ("staff_rudal_1@pickleball.vn", "Lê Quốc Hưng (NV Rudal)", "0938375001"),
            ("staff_rudal_2@pickleball.vn", "Phạm Hoài Nam (NV Rudal)", "0938375002"),
            ("staff_rudal_3@pickleball.vn", "Đỗ Minh Tuấn (NV Rudal)", "0938375003"),
        ),
    ),
    VenueSeed(
        key="djoy",
        name="D-Joy Pickleball Thủ Thiêm",
        address="Công viên bờ sông Sài Gòn (khu vực cầu Ba Son), phường An Khánh, TP. Hồ Chí Minh",
        lat=10.7771396, lng=106.7116654,
        maps="https://maps.app.goo.gl/mg8MigCTNSiXdXLf6",
        images=(
            f"{_CLOUD}/v1791118336/picklematch2k/venues/v2_4fd87a3b.webp",
            f"{_CLOUD}/v1791118346/picklematch2k/venues/v2_c5d10092.jpg",
        ),
        desc="Cụm 11 sân ngoài trời đẳng cấp tại Công viên bờ sông Sài Gòn, view Landmark 81 cực đẹp, "
             "tổ chức nhiều giải đấu quy mô.",
        courts=11, open=time(6, 0), close=time(23, 0),
        base=180000, peak=250000, weekend=180000,
        amenities=("led", "rental", "canteen", "parking"),
        owner=("owner_djoy_thuthiem@pickleball.vn", "Đặng D-Joy (Chủ Sân)", "0706256789", "D-Joy Sports Entertainment"),
        staff=(
            ("staff_djoy_1@pickleball.vn", "Trần Bảo Long (NV D-Joy)", "0706256001"),
            ("staff_djoy_2@pickleball.vn", "Vũ Đình Trọng (NV D-Joy)", "0706256002"),
            ("staff_djoy_3@pickleball.vn", "Ngô Thế Vinh (NV D-Joy)", "0706256003"),
        ),
    ),
    VenueSeed(
        key="no152",
        name="Pickleball 152 Nguyễn Oanh",
        address="152 Nguyễn Oanh, Phường 17, Quận Gò Vấp, TP. Hồ Chí Minh",
        lat=10.8334109, lng=106.676412,
        maps="https://maps.app.goo.gl/6cJLC4jncpX8GRwV7",
        images=(
            f"{_CLOUD}/v1791118363/picklematch2k/venues/v3_2a1e7083.webp",
        ),
        desc="Cụm 4 sân trong nhà cao cấp tại Quận Gò Vấp, sàn US Open đàn hồi tốt, hệ thống quạt mát "
             "và máy lạnh phòng nghỉ đầy đủ.",
        courts=4, open=time(5, 30), close=time(23, 0),
        base=120000, peak=200000, weekend=120000,
        amenities=("led", "indoor", "rental", "canteen", "shower", "lounge"),
        owner=("owner_152nguyenoanh@pickleball.vn", "Chị Vân Anh (Chủ Sân)", "0765883535", "CLB Thể Thao 152 Nguyễn Oanh"),
        staff=(
            ("staff_152no_1@pickleball.vn", "Nguyễn Thanh Bình (NV 152 NO)", "0765883001"),
            ("staff_152no_2@pickleball.vn", "Hoàng Hải Đăng (NV 152 NO)", "0765883002"),
            ("staff_152no_3@pickleball.vn", "Bùi Quang Khải (NV 152 NO)", "0765883003"),
        ),
    ),
]
VENUE_BY_KEY = {v.key: v for v in VENUES}


@dataclass(frozen=True)
class PlayerSeed:
    email: str
    full_name: str
    phone: str
    skill_level: float            # DUPR tự khai
    play_style: str
    date_of_birth: Optional[date]
    lat: float
    lng: float
    matches_played: int
    matches_won: int
    purpose: str


PLAYERS = [
    PlayerSeed("khanhhoan121209@gmail.com", "Nguyễn Hoàng Khánh", "0908888999", 3.5, "Dinking & Control", date(1998, 5, 15), 10.8322, 106.6863, 10, 6,
     "recreational"),
    PlayerSeed("player@example.com", "Trần Minh Nam", "0912345678", 3.5, "All-Round", date(1996, 8, 20), 10.7769, 106.7009, 10, 6,
     "recreational"),
    PlayerSeed("player01@gmail.com", "Lê Hoàng Long", "0901112233", 3.0, "Dinking & Control", date(1999, 3, 10), 10.7735, 106.6685, 10, 6,
     "practice"),
    PlayerSeed("player02@gmail.com", "Phạm Minh Tuấn", "0902223344", 4.0, "Offensive", date(1995, 11, 22), 10.7901, 106.7322, 10, 7,
     "competitive"),
    PlayerSeed("player03@gmail.com", "Vũ Đức Cường", "0903334455", 4.5, "Serve & Volley", date(2001, 7, 4), 10.8225, 106.7198, 10, 8,
     "competitive"),
    PlayerSeed("player04@gmail.com", "Hoàng Gia Huy", "0904445566", 2.5, "Defensive", date(1990, 2, 18), 10.7958, 106.6908, 10, 5,
     "recreational"),
    PlayerSeed("player05@gmail.com", "Đỗ Bảo Nam", "0905556677", 3.5, "Offensive", date(1997, 12, 5), 10.8334, 106.6764, 10, 6,
     "recreational"),
    PlayerSeed("player06@gmail.com", "Bùi Phương Thảo", "0906667788", 3.0, "All-Round", date(1988, 9, 14), 10.7485, 106.7262, 10, 4,
     "recreational"),
    PlayerSeed("player07@gmail.com", "Ngô Quang Hải", "0907778899", 4.0, "Serve & Volley", date(2000, 1, 30), 10.7812, 106.6854, 10, 7,
     "competitive"),
    PlayerSeed("player08@gmail.com", "Trịnh Thu Hà", "0908889900", 2.0, "Defensive", date(1994, 6, 25), 10.7995, 106.6562, 10, 3,
     "practice"),
    PlayerSeed("player09@gmail.com", "Dương Tiến Đạt", "0909990011", 3.5, "Dinking & Control", date(1998, 10, 12), 10.7771, 106.7117, 12, 8,
     "practice"),
    PlayerSeed("player10@gmail.com", "Mai Tuấn Kiên", "0911122233", 5.0, "Offensive", date(2002, 4, 19), 10.7745, 106.6912, 10, 6,
     "competitive"),
    PlayerSeed("player11@gmail.com", "Đặng Thùy Linh", "0912233344", 3.0, "All-Round", date(1993, 4, 9), 10.8123, 106.7045, 12, 8,
     "recreational"),
    PlayerSeed("player12@gmail.com", "Phan Đình Trọng", "0913344455", 3.5, "Offensive", date(1985, 7, 21), 10.8412, 106.6698, 12, 8,
     "recreational"),
    PlayerSeed("player13@gmail.com", "Lâm Thảo My", "0914455566", 2.5, "Defensive", date(2003, 11, 2), 10.7689, 106.6712, 12, 8,
     "practice"),
    PlayerSeed("player14@gmail.com", "Huỳnh Tấn Tài", "0915566677", 4.0, "Serve & Volley", date(1991, 1, 17), 10.7934, 106.7410, 12, 8,
     "competitive"),
    PlayerSeed("player15@gmail.com", "Cao Minh Trí", "0916677788", 3.5, "Dinking & Control", date(1979, 9, 30), 10.7350, 106.7180, 12, 8,
     "practice"),
    PlayerSeed("player16@gmail.com", "Đoàn Ngọc Ánh", "0917788899", 3.0, "All-Round", date(1996, 6, 8), 10.8050, 106.6500, 12, 8,
     "recreational"),
    PlayerSeed("player17@gmail.com", "Lương Gia Bảo", "0918899900", 4.5, "Offensive", date(2000, 12, 12), 10.7980, 106.6850, 12, 8,
     "competitive"),
    PlayerSeed("player18@gmail.com", "Hà Quốc Việt", "0919900011", 3.5, "All-Round", date(1972, 3, 26), 10.7710, 106.6980, 12, 8,
     "recreational"),
]


# ---------------------------------------------------------------------------
# Dữ liệu nền: tiện ích, tài khoản, cụm sân
# ---------------------------------------------------------------------------
def seed_amenities(db: Session) -> Dict[str, Amenity]:
    amenities = {}
    for key, name, icon in AMENITIES:
        amenity = db.query(Amenity).filter(Amenity.name == name).first()
        if amenity is None:
            amenity = Amenity(name=name, icon=icon)
            db.add(amenity)
        amenities[key] = amenity
    db.flush()
    return amenities


def _owner_bank_account() -> Optional[str]:
    """Tài khoản nhận tiền mẫu lấy từ cấu hình SEPAY_* (không ghi số tài khoản nào vào mã nguồn)."""
    if settings.SEPAY_BANK_ACCOUNT and (settings.SEPAY_BANK_NAME or settings.SEPAY_BANK_CODE):
        return f"{settings.SEPAY_BANK_ACCOUNT} - {settings.SEPAY_BANK_NAME or settings.SEPAY_BANK_CODE}"
    return None


def seed_accounts_and_venues(db: Session, amenities: Dict[str, Amenity]) -> dict:
    ctx = {"venues": {}, "courts": {}, "staff": {}, "owners": {}, "players": {}}

    create_user(db, email="admin@example.com", password=DEMO_PASSWORD, role=UserRole.ADMIN.value, commit=False)

    for item in VENUES:
        email, full_name, phone, company = item.owner
        owner = create_user(db, email=email, password=DEMO_PASSWORD, role=UserRole.OWNER.value,
                            full_name=full_name, phone=phone, commit=False)
        db.refresh(owner)
        owner.owner_profile.company_name = settings.SEPAY_ACCOUNT_HOLDER or company
        owner.owner_profile.bank_account = _owner_bank_account()

        venue = Venue(
            owner_id=owner.id, name=item.name, description=item.desc, address=item.address,
            latitude=item.lat, longitude=item.lng, google_maps_url=item.maps,
            image_url=item.images[0], images=json.dumps(list(item.images)), status="ACTIVE",
        )
        venue.amenities = [amenities[key] for key in item.amenities]
        db.add(venue)
        db.flush()

        courts = [Court(venue_id=venue.id, name=f"Sân {i}", status="ACTIVE") for i in range(1, item.courts + 1)]
        db.add_all(courts)
        for day in range(7):
            db.add(OperatingHour(venue_id=venue.id, day_of_week=day, open_time=item.open, close_time=item.close))
        db.add(PriceRule(venue_id=venue.id, rule_type="BASE", start_time=time(6, 0), end_time=time(17, 0), price=item.base))
        db.add(PriceRule(venue_id=venue.id, rule_type="PEAK", start_time=time(17, 0), end_time=time(23, 0), price=item.peak))
        db.add(PriceRule(venue_id=venue.id, rule_type="WEEKEND", price=item.weekend))
        db.flush()

        staff_users = [
            create_user(db, email=s_email, password=DEMO_PASSWORD, role=UserRole.STAFF.value,
                        full_name=s_name, phone=s_phone, venue_id=venue.id, commit=False)
            for s_email, s_name, s_phone in item.staff
        ]
        ctx["venues"][item.key] = venue
        ctx["courts"][item.key] = courts
        ctx["staff"][item.key] = staff_users
        ctx["owners"][item.key] = owner

    for player in PLAYERS:
        user = create_user(db, email=player.email, password=DEMO_PASSWORD, role=UserRole.PLAYER.value,
                           full_name=player.full_name, phone=player.phone, commit=False)
        db.refresh(user)
        profile = user.player_profile
        profile.skill_level, profile.play_style = player.skill_level, player.play_style
        profile.date_of_birth = player.date_of_birth
        profile.latitude, profile.longitude = player.lat, player.lng
        profile.matches_played, profile.matches_won = player.matches_played, player.matches_won
        ctx["players"][player.email] = user

    db.commit()
    apply_demo_preferences(db)
    return ctx


def apply_demo_preferences(db: Session) -> int:
    """
    Điền mục đích chơi và ngày sinh mẫu cho các tài khoản demo (cả các tài khoản ghepNN của seed --matches).
    Chỉ điền vào trường đang trống, nên chạy lại nhiều lần hoặc chạy trên CSDL đang dùng đều an toàn.
    Trả về số tài khoản vừa được bổ sung.
    """
    updated = 0
    for player in [*PLAYERS, *MATCH_DEMO_PLAYERS]:
        user = db.query(User).filter(User.email == player.email).first()
        profile = user.player_profile if user else None
        if profile is None:
            continue
        changed = False
        if not profile.purpose:
            profile.purpose, changed = player.purpose, True
        if profile.date_of_birth is None and player.date_of_birth is not None:
            profile.date_of_birth, changed = player.date_of_birth, True
        updated += int(changed)
    db.commit()
    return updated


# ---------------------------------------------------------------------------
# Phiếu ghép cặp mô phỏng: dữ liệu huấn luyện nằm trong CSDL
# ---------------------------------------------------------------------------
SIMULATED_FEEDBACK_PER_PLAYER = 500
SIMULATED_FEEDBACK_SEED = 2026


def seed_simulated_feedback(db: Session, per_player: int = SIMULATED_FEEDBACK_PER_PLAYER, replace: bool = False) -> int:
    """
    Nạp phiếu ghép cặp MÔ PHỎNG (source = "simulated") để mô hình có dữ liệu huấn luyện nằm trong CSDL.

    Mỗi tài khoản người chơi demo "trả lời" per_player phiếu về các hồ sơ ứng viên giả định xoay quanh chân dung của
    mình (lấy từ PLAYERS ở trên, không phụ thuộc hồ sơ đang lưu), sinh bằng đúng hàm mà trang khảo sát dùng. Nhãn
    "muốn ghép / không" sinh từ quy tắc viết tay có cộng nhiễu của app/ml/train_model.py. Bộ sinh số ngẫu nhiên cố
    định hạt giống nên chạy ở đâu cũng ra cùng một bộ dữ liệu.

    Bỏ qua nếu CSDL đã có phiếu mô phỏng, trừ khi replace=True: khi đó các phiếu mô phỏng cũ được thay bằng bộ sinh
    theo quy tắc hiện tại, trong cùng một giao dịch (dùng sau khi đổi quy tắc sinh nhãn). Câu trả lời khảo sát thật
    không bao giờ bị đụng tới. Trả về số phiếu vừa nạp.
    """
    import numpy as np
    import pandas as pd

    from app.ml.train_model import noisy_rule_labels

    existing = db.query(PairFeedback).filter(PairFeedback.source == SIMULATED_SOURCE)
    if existing.count():
        if not replace:
            return 0
        existing.delete(synchronize_session=False)   # chưa commit: nếu không sinh được bộ mới thì phiếu cũ còn nguyên

    rows = []
    for index, player in enumerate(PLAYERS):
        user = db.query(User).filter(User.email == player.email).first()
        if user is None:
            continue
        rng = random.Random(SIMULATED_FEEDBACK_SEED + index)
        me = ProfileView(skill_level=player.skill_level, purpose=player.purpose, play_style=canonical_style(player.play_style))
        for _ in range(per_player):
            candidate, distance, age_gap = ml_service.hypothetical_candidate(rng, me)
            rows.append({"rater_id": user.id, **pair_features(me, candidate, distance_km=distance, age_diff=age_gap)})
    if not rows:
        db.rollback()
        return 0

    frame = pd.DataFrame(rows)
    labels = noisy_rule_labels(frame[FEATURE_NAMES], np.random.default_rng(SIMULATED_FEEDBACK_SEED))
    db.bulk_insert_mappings(PairFeedback, [
        {
            "rater_id": int(row["rater_id"]),
            "source": SIMULATED_SOURCE,
            "level_diff": float(row["level_diff"]),
            "distance_km": float(row["distance_km"]),
            "purpose_match": int(row["purpose_match"]),
            "style_match": int(row["style_match"]),
            "age_diff": float(row["age_diff"]),
            "label": int(label),
        }
        for row, label in zip(rows, labels)
    ])
    db.commit()
    return len(rows)


# ---------------------------------------------------------------------------
# Hoạt động mẫu: đơn đặt, thanh toán, check-in, hủy, phòng đấu, đánh giá
# ---------------------------------------------------------------------------
class DemoActivity:
    def __init__(self, db: Session, ctx: dict):
        self.db, self.ctx = db, ctx
        self.today = today_vn()
        self._moment: Optional[datetime] = None
        self._reference = 0

    # -- đồng hồ nghiệp vụ ---------------------------------------------------
    def at(self, day: date, hour: int, minute: int = 0) -> datetime:
        """Tua đồng hồ nghiệp vụ tới một thời điểm (giờ Việt Nam)."""
        self._moment = vn_datetime(day, time(hour, minute))
        timeutils.set_clock(lambda: self._moment)
        return self._moment

    def now(self) -> None:
        self._moment = None
        timeutils.set_clock(None)

    def _stamp(self, booking: Booking) -> None:
        """Ghi lại thời điểm mô phỏng vào created_at (mặc định CSDL luôn ghi giờ thật lúc chạy script)."""
        if self._moment is None:
            return
        if booking.created_at is None or booking.created_at > self._moment:
            booking.created_at = self._moment
        for txn in self.db.query(PaymentTransaction).filter(PaymentTransaction.booking_id == booking.id):
            if txn.created_at is None or txn.created_at > self._moment:
                txn.created_at = txn.transaction_date = self._moment
        self.db.commit()

    # -- tiện ích --------------------------------------------------------------
    def player(self, email: str) -> User:
        return self.ctx["players"][email]

    def slots(self, venue_key: str, court_no: int, day: date, from_hour: int, count: int = 1) -> List[SlotRequest]:
        """`count` khung giờ liên tiếp trên lưới của cụm sân, bắt đầu từ khung đầu tiên không sớm hơn from_hour."""
        item = VENUE_BY_KEY[venue_key]
        grid = iter_day_slots(item.open, item.close)
        start = next(i for i, (begin, _) in enumerate(grid) if begin >= time(from_hour, 0))
        court = self.ctx["courts"][venue_key][court_no - 1]
        return [SlotRequest(court.id, day, begin, end) for begin, end in grid[start:start + count]]

    def book(self, email: str, venue_key: str, court_no: int, day: date, from_hour: int, count: int = 1) -> Booking:
        booking = booking_service.create_booking(
            self.db, user=self.player(email), slots=self.slots(venue_key, court_no, day, from_hour, count)
        )
        self._stamp(booking)
        return booking

    def pay_deposit(self, booking: Booking) -> Booking:
        """Mô phỏng SePay báo đã nhận đủ tiền cọc qua chuyển khoản."""
        self._reference += 1
        amount = float(booking.deposit_amount)
        ledger.record_transaction(
            self.db, booking, amount=amount, kind=PaymentKind.DEPOSIT.value,
            method=PaymentMethod.BANK_TRANSFER.value, gateway="SePay_VietQR",
            reference_number=f"DEMO{self._reference:06d}", content=f"{booking.booking_code} chuyen khoan coc",
        )
        booking_service.apply_payment(self.db, booking, amount)
        self.db.commit()
        self.db.refresh(booking)
        self._stamp(booking)
        return booking

    def play(self, booking: Booking, venue_key: str) -> Booking:
        """Khách đến nhận sân (thu phần còn lại bằng tiền mặt) rồi chơi hết giờ."""
        staff = self.ctx["staff"][venue_key][0]
        start = booking_service.first_slot_start(booking)
        end = booking_service.last_slot_end(booking)
        self.at(start.date(), start.hour, start.minute)
        booking_service.check_in(self.db, booking, staff)
        self._stamp(booking)
        finished = end + timedelta(minutes=5)
        self.at(finished.date(), finished.hour, finished.minute)
        booking_service.finalize_past_bookings(self.db)
        self.db.refresh(booking)
        return booking

    def review(self, email: str, venue_key: str, rating: float, comment: str, day: date) -> None:
        self.db.add(Review(
            user_id=self.player(email).id, venue_id=self.ctx["venues"][venue_key].id,
            rating=rating, comment=comment, created_at=vn_datetime(day, time(21, 30)),
        ))
        self.db.commit()

    # -- kịch bản --------------------------------------------------------------
    def past(self) -> None:
        t = self.today
        completed = [
            # người chơi, cụm sân, sân, cách đây (ngày), giờ, số khung, điểm, nhận xét
            ("khanhhoan121209@gmail.com", "no152", 1, 6, 18, 2, 5.0, "Sân trong nhà mát, mặt sân bám tốt, nhân viên hỗ trợ nhanh."),
            ("player@example.com", "djoy", 2, 5, 19, 1, 5.0, "View bờ sông rất đẹp, đèn sáng đều, đánh buổi tối rất thích."),
            ("player02@gmail.com", "rudal", 1, 4, 17, 2, 4.0, "Sân chuẩn, có HLV hướng dẫn. Giờ cao điểm hơi đông."),
            ("player05@gmail.com", "no152", 2, 3, 6, 1, 4.0, "Buổi sáng vắng, dễ đặt. Phòng thay đồ sạch sẽ."),
            ("player09@gmail.com", "djoy", 1, 3, 18, 2, 5.0, "Nhiều sân nên dễ tìm khung giờ, bãi xe rộng."),
            ("player07@gmail.com", "rudal", 3, 2, 20, 1, 3.0, "Sân ổn nhưng khung 20h phải chờ nhóm trước ra sân trễ vài phút."),
        ]
        for email, venue_key, court_no, days_ago, hour, count, rating, comment in completed:
            day = t - timedelta(days=days_ago)
            self.at(day - timedelta(days=1), 9)
            booking = self.book(email, venue_key, court_no, day, hour, count)
            self.at(day - timedelta(days=1), 9, 5)
            self.pay_deposit(booking)
            self.play(booking, venue_key)
            self.review(email, venue_key, rating, comment, day)

        # Đã cọc nhưng không đến sân -> NO_SHOW
        day = t - timedelta(days=2)
        self.at(day - timedelta(days=1), 10)
        no_show = self.book("player12@gmail.com", "no152", 1, day, 19, 1)
        self.pay_deposit(no_show)
        self.at(day, 22)
        booking_service.finalize_past_bookings(self.db)

        # Người chơi hủy sớm (trước giờ chơi hơn 12 tiếng) -> hoàn 100%, chủ sân đã chuyển hoàn
        day = t - timedelta(days=1)
        self.at(day - timedelta(days=2), 14)
        cancelled = self.book("player03@gmail.com", "rudal", 2, day, 18, 1)
        self.pay_deposit(cancelled)
        self.at(day - timedelta(days=1), 8)
        booking_service.cancel_by_player(self.db, cancelled.id, self.player("player03@gmail.com"), _RefundInfo(
            bank_account="1900000001", bank_name="Vietcombank", account_holder="VU DUC CUONG", reason="Bận việc đột xuất",
        ))
        self.at(day - timedelta(days=1), 15)
        cancelled = booking_service.get_booking_or_404(self.db, cancelled.id)
        booking_service.confirm_refund(self.db, cancelled, self.ctx["owners"]["rudal"], "Đã chuyển hoàn cọc")
        self._stamp(cancelled)

        # Khách vãng lai trả tiền mặt tại quầy hôm qua
        self.at(day, 9, 50)
        staff = self.ctx["staff"]["djoy"][0]
        walk_in = booking_service.create_booking(
            self.db, user=staff, slots=self.slots("djoy", 5, day, 10, 1), source=BookingSource.DESK.value,
            guest_name="Anh Minh (khách vãng lai)", guest_phone="0987000111", desk_paid="FULL", check_in_now=True,
        )
        self._stamp(walk_in)
        self.at(day, 11, 5)
        booking_service.finalize_past_bookings(self.db)
        self.now()

    def upcoming(self) -> None:
        t = self.today
        self.now()

        def confirmed(email, venue_key, court_no, days_ahead, hour, count):
            booking = self.book(email, venue_key, court_no, t + timedelta(days=days_ahead), hour, count)
            return self.pay_deposit(booking)

        def open_match(booking, email, *, skill, players, purpose, notes, joiners=()):
            match = match_service.create_match(self.db, self.player(email), MatchCreate(
                booking_id=booking.id, required_skill=skill, num_players=players, purpose=purpose, notes=notes,
            ))
            for joiner in joiners:
                match_service.join_match(self.db, match.id, self.player(joiner).id)

        open_match(
            confirmed("khanhhoan121209@gmail.com", "no152", 1, 1, 18, 2), "khanhhoan121209@gmail.com",
            skill=3.5, players=4, purpose="recreational", notes="Giao lưu vui vẻ trình 3.5, chia đều tiền sân.",
            joiners=("player05@gmail.com", "player12@gmail.com"),
        )
        open_match(
            confirmed("player02@gmail.com", "rudal", 1, 2, 19, 2), "player02@gmail.com",
            skill=4.0, players=4, purpose="competitive", notes="Đánh đôi tính điểm, cần thêm 1 người trình 4.0.",
            joiners=("player07@gmail.com", "player14@gmail.com"),
        )
        open_match(
            confirmed("player09@gmail.com", "djoy", 3, 1, 6, 2), "player09@gmail.com",
            skill=3.5, players=2, purpose="practice", notes="Tập dink và drop buổi sáng.",
            joiners=("player15@gmail.com",),
        )
        confirmed("player06@gmail.com", "djoy", 4, 3, 17, 1)

        # Người chơi vừa hủy (còn hơn 12 tiếng) -> chờ chủ sân hoàn cọc
        to_refund = confirmed("player01@gmail.com", "no152", 3, 2, 20, 1)
        booking_service.cancel_by_player(self.db, to_refund.id, self.player("player01@gmail.com"), _RefundInfo(
            bank_account="1900000002", bank_name="MBBank", account_holder="LE HOANG LONG", reason="Đổi kế hoạch",
        ))

        # Khách gọi điện giữ sân, sẽ trả tiền khi đến
        booking_service.create_booking(
            self.db, user=self.ctx["staff"]["rudal"][0], slots=self.slots("rudal", 4, t + timedelta(days=1), 9, 1),
            source=BookingSource.DESK.value, guest_name="Chị Hoa (đặt qua điện thoại)", guest_phone="0977000222",
            desk_paid="NONE",
        )


class _RefundInfo:
    def __init__(self, bank_account: str, bank_name: str, account_holder: str, reason: str):
        self.bank_account, self.bank_name = bank_account, bank_name
        self.account_holder, self.reason = account_holder, reason


# ---------------------------------------------------------------------------
# Người chơi và phòng đấu mẫu để thử chức năng ghép trận (python manage.py seed --matches)
# ---------------------------------------------------------------------------
# Nạp THÊM vào CSDL đang có dữ liệu: chỉ tạo các tài khoản ghepNN@example.com cùng đơn đặt sân và phòng đấu của
# chính các tài khoản này; không sửa tài khoản hay dữ liệu đã có. Ngày tính từ hôm chạy lệnh và phòng nào đã có thì
# bỏ qua, nên có thể chạy lại (ví dụ trước buổi bảo vệ) để có phòng mới cho tuần tới.
MATCH_DEMO_GATEWAY = "Dữ liệu mẫu"  # nhãn trên giao dịch cọc của các đơn mẫu, để phân biệt với tiền thật

MATCH_DEMO_PLAYERS = [
    # email, họ tên, điện thoại, DUPR, phong cách, ngày sinh, vĩ độ, kinh độ, số trận, số thắng, mục đích
    PlayerSeed("ghep01@example.com", "Trần Quốc Bảo", "0900000101", 3.5, "All-Round", date(1997, 2, 14), 10.7850, 106.7200, 24, 13,
     "recreational"),
    PlayerSeed("ghep02@example.com", "Nguyễn Thị Mai Anh", "0900000102", 3.5, "Dinking & Control", date(1994, 8, 3), 10.8000, 106.7100, 18, 10,
     "recreational"),
    PlayerSeed("ghep03@example.com", "Lê Minh Khôi", "0900000103", 4.0, "Offensive", date(1990, 5, 27), 10.7760, 106.7000, 40, 26,
     "competitive"),
    PlayerSeed("ghep04@example.com", "Phạm Gia Hân", "0900000104", 3.0, "Defensive", date(2001, 10, 19), 10.8300, 106.6800, 12, 5,
     "practice"),
    PlayerSeed("ghep05@example.com", "Võ Thành Đạt", "0900000105", 4.5, "Serve & Volley", date(1988, 12, 1), 10.7900, 106.6900, 60, 41,
     "competitive"),
    PlayerSeed("ghep06@example.com", "Đinh Ngọc Lan", "0900000106", 2.5, "Defensive", date(1975, 4, 11), 10.8000, 106.7250, 6, 2,
     "recreational"),
    PlayerSeed("ghep07@example.com", "Bùi Anh Tuấn", "0900000107", 3.0, "All-Round", date(1983, 6, 30), 10.8250, 106.6850, 15, 7,
     "recreational"),
    PlayerSeed("ghep08@example.com", "Hồ Thanh Tùng", "0900000108", 4.0, "Serve & Volley", date(1995, 1, 22), 10.7830, 106.7150, 35, 21,
     "competitive"),
    PlayerSeed("ghep09@example.com", "Trương Mỹ Duyên", "0900000109", 3.5, "Offensive", date(1999, 9, 9), 10.7800, 106.7050, 20, 11,
     "practice"),
    PlayerSeed("ghep10@example.com", "Lý Hoàng Phúc", "0900000110", 5.0, "Offensive", date(1992, 3, 5), 10.8300, 106.6700, 80, 60,
     "competitive"),
    PlayerSeed("ghep11@example.com", "Đặng Khánh Vy", "0900000111", 3.0, "Dinking & Control", date(2004, 7, 15), 10.8400, 106.6800, 10, 4,
     "recreational"),
    PlayerSeed("ghep12@example.com", "Châu Nhật Minh", "0900000112", 4.5, "Offensive", date(1986, 11, 28), 10.7950, 106.7280, 55, 36,
     "competitive"),
]


@dataclass(frozen=True)
class RoomSeed:
    host: str                      # email người mở phòng
    venue: int                     # thứ tự cụm sân đang hoạt động (0 = cụm đầu tiên theo id)
    days_ahead: int
    hour: int                      # khung giờ đầu tiên trên lưới của cụm sân không sớm hơn giờ này
    hours: int                     # số khung 60 phút liên tiếp
    players: int
    purpose: str
    notes: str
    joiners: Tuple[str, ...] = ()


def _g(number: int) -> str:
    return f"ghep{number:02d}@example.com"


# Đủ các tình huống cần thử: phòng mới mở, còn đúng 1 chỗ, đã đủ người, phòng 2 người, phòng xoay vòng 6 người,
# nhiều mức trình độ (2.5 - 5.0) và hai phòng trùng giờ trong cùng một tối (phòng 1 và 2).
MATCH_DEMO_ROOMS = [
    RoomSeed(_g(1), 0, 1, 18, 2, 4, "recreational", "Giao lưu sau giờ làm, trình 3.5, chia đều tiền sân.", (_g(2),)),
    RoomSeed(_g(3), 1, 1, 19, 1, 4, "competitive", "Đánh đôi tính điểm, cần thêm 1 người trình 4.0.", (_g(8), _g(5))),
    RoomSeed(_g(9), 1, 2, 6, 1, 2, "practice", "Tập dink và drop buổi sáng, một kèm một."),
    RoomSeed(_g(5), 0, 2, 20, 2, 4, "competitive", "Đánh đôi tốc độ cao, ưu tiên trình 4.5.", (_g(12),)),
    RoomSeed(_g(10), 2, 2, 20, 1, 2, "competitive", "Tìm đối đánh đơn trình 4.5 - 5.0."),
    RoomSeed(_g(4), 2, 3, 17, 2, 4, "recreational", "Nhóm 3.0 đánh vui, còn thiếu 1 người cho đủ đôi.", (_g(7), _g(11))),
    RoomSeed(_g(2), 1, 3, 19, 2, 6, "recreational", "Xoay vòng 6 người, trình 3.0 - 3.5 đều vào được.", (_g(1), _g(9))),
    RoomSeed(_g(6), 0, 4, 7, 1, 4, "practice", "Mới chơi, đánh nhẹ nhàng làm quen."),
    RoomSeed(_g(8), 1, 5, 8, 2, 4, "competitive", "Đủ đội hình, hẹn có mặt trước 10 phút.", (_g(3), _g(5), _g(12))),
    RoomSeed(_g(9), 2, 6, 18, 2, 4, "recreational", "Cuối tuần giao lưu, có sẵn bóng và vợt dự phòng."),
]


def _demo_player(db: Session, player: PlayerSeed) -> Tuple[User, bool]:
    """Tài khoản người chơi mẫu theo email; tạo mới kèm hồ sơ đầy đủ nếu chưa có. Trả về (tài khoản, vừa tạo?)."""
    user = db.query(User).filter(User.email == player.email).first()
    if user is not None:
        return user, False
    user = create_user(db, email=player.email, password=DEMO_PASSWORD, role=UserRole.PLAYER.value,
                       full_name=player.full_name, phone=player.phone, commit=False)
    db.refresh(user)
    profile = user.player_profile
    profile.skill_level, profile.play_style = player.skill_level, player.play_style
    profile.latitude, profile.longitude = player.lat, player.lng
    profile.matches_played, profile.matches_won = player.matches_played, player.matches_won
    profile.purpose, profile.date_of_birth = player.purpose, player.date_of_birth
    return user, True


def _court_slot_options(venue: Venue, day: date, from_hour: int, count: int) -> List[List[SlotRequest]]:
    """Với từng sân đang hoạt động: `count` khung liên tiếp, bắt đầu từ khung đầu tiên không sớm hơn from_hour."""
    opening = get_operating_hour(venue, day)
    if opening is None:
        return []
    grid = iter_day_slots(opening.open_time, opening.close_time)
    start = next((i for i, (begin, _) in enumerate(grid) if begin >= time(from_hour, 0)), None)
    if start is None or start + count > len(grid):
        return []
    window = grid[start:start + count]
    courts = sorted((c for c in venue.courts if c.status == "ACTIVE"), key=lambda c: c.id)
    return [[SlotRequest(court.id, day, begin, end) for begin, end in window] for court in courts]


def _in_active_room(db: Session, user_id: int, day: date, start: time, end: time) -> bool:
    return db.query(Match.id).join(MatchParticipant, MatchParticipant.match_id == Match.id).filter(
        MatchParticipant.user_id == user_id,
        Match.status.in_(match_service.ACTIVE_MATCH_STATUSES),
        Match.date == day, Match.start_time < end, Match.end_time > start,
    ).first() is not None


def seed_match_demo(db: Session) -> dict:
    """
    Nạp thêm người chơi và phòng đấu mẫu vào CSDL đang dùng. Mỗi phòng gắn với một đơn đã cọc của chủ phòng
    (tiền cọc ghi vào sổ giao dịch với nhãn "Dữ liệu mẫu"), tạo bằng chính các hàm nghiệp vụ của ứng dụng.
    Trả về {"players": số tài khoản vừa tạo, "rooms": [phòng vừa mở], "skipped": [lý do bỏ qua]}.
    """
    result: dict = {"players": 0, "rooms": [], "skipped": []}
    venues = db.query(Venue).filter(Venue.status == "ACTIVE").order_by(Venue.id).all()
    if not venues:
        result["skipped"].append("CSDL chưa có cụm sân nào đang hoạt động.")
        return result

    users: Dict[str, User] = {}
    for player in MATCH_DEMO_PLAYERS:
        users[player.email], created = _demo_player(db, player)
        result["players"] += int(created)
    db.commit()

    today = today_vn()
    for room in MATCH_DEMO_ROOMS:
        host, venue = users[room.host], venues[room.venue % len(venues)]
        day = today + timedelta(days=room.days_ahead)
        label = f"{day:%d/%m} từ {room.hour}h tại {venue.name}"
        options = _court_slot_options(venue, day, room.hour, room.hours)
        if not options:
            result["skipped"].append(f"{label}: cụm sân không mở cửa khung giờ này.")
            continue
        start, end = options[0][0].start_time, options[0][-1].end_time
        if _in_active_room(db, host.id, day, start, end):
            result["skipped"].append(f"{label}: chủ phòng đã có phòng trong khung giờ này (đã nạp trước đó).")
            continue

        booking, reason = None, "mọi sân đều đã có người đặt"
        for slots in options:
            try:
                booking = booking_service.create_booking(db, user=host, slots=slots)
                break
            except HTTPException as exc:
                db.rollback()
                if exc.status_code != 409:   # không phải do sân bận thì thử sân khác cũng vô ích
                    reason = str(exc.detail)
                    break
        if booking is None:
            result["skipped"].append(f"{label}: {reason}.")
            continue

        deposit = float(booking.deposit_amount)
        ledger.record_transaction(
            db, booking, amount=deposit, kind=PaymentKind.DEPOSIT.value, method=PaymentMethod.BANK_TRANSFER.value,
            gateway=MATCH_DEMO_GATEWAY, reference_number=f"DEMO-{booking.booking_code}",
            content=f"{booking.booking_code} tien coc (du lieu mau)",
        )
        booking_service.apply_payment(db, booking, deposit)
        db.commit()

        match = match_service.create_match(db, host, MatchCreate(
            booking_id=booking.id, required_skill=host.player_profile.skill_level,
            num_players=room.players, purpose=room.purpose, notes=room.notes,
        ))
        for email in room.joiners:
            try:
                match = match_service.join_match(db, match.id, users[email].id)
            except HTTPException:
                db.rollback()   # ví dụ người này đã ở phòng khác trùng giờ từ lần nạp trước
        result["rooms"].append({
            "day": day, "start": start, "end": end, "venue": venue.name, "court": match.court_name,
            "host": host.player_profile.full_name, "level": host.player_profile.skill_level,
            "members": len(match.participants), "players": match.num_players, "status": match.status,
            "booking_code": booking.booking_code, "deposit": deposit,
        })
    return result


def report_match_demo(result: dict) -> None:
    for room in result["rooms"]:
        print(f"  {room['day']:%d/%m} {room['start']:%H:%M}-{room['end']:%H:%M}  {room['venue']} ({room['court']})  "
              f"chủ phòng {room['host']} (trình {room['level']})  {room['members']}/{room['players']} người  "
              f"{'đã đủ' if room['status'] == 'FULL' else 'đang tuyển'}  [{room['booking_code']}]")
    for reason in result["skipped"]:
        print(f"  bỏ qua - {reason}")
    deposits = sum(room["deposit"] for room in result["rooms"])
    print(f"Đã tạo {result['players']} tài khoản người chơi mẫu và mở {len(result['rooms'])} phòng đấu "
          f"(tiền cọc mẫu ghi sổ: {deposits:,.0f}đ, nhãn \"{MATCH_DEMO_GATEWAY}\").")
    print(f"Tài khoản mẫu: {MATCH_DEMO_PLAYERS[0].email} ... {MATCH_DEMO_PLAYERS[-1].email}, mật khẩu {DEMO_PASSWORD}.")


# ---------------------------------------------------------------------------
# Hoạt động mẫu cho một cụm sân mới (python manage.py seed --activity [--venue ID])
# ---------------------------------------------------------------------------
# Cụm sân nhập thêm (ví dụ bằng import-excel) chưa có nhân viên, đơn đặt, giao dịch, phòng đấu hay đánh giá nào.
# Lệnh này nạp THÊM một bộ hoạt động mẫu cho cụm sân đó bằng chính các hàm nghiệp vụ của ứng dụng, dùng các tài
# khoản người chơi demo đang có. Cụm sân đã có đơn thì bỏ qua, nên chạy lại không nạp trùng. Tiền cọc chuyển khoản
# mang nhãn "Dữ liệu mẫu", các dòng sổ còn lại được ghi chú "(dữ liệu mẫu)", để phân biệt với tiền thật.
DEMO_NOTE = "(dữ liệu mẫu)"
DEMO_STAFF_NAMES = ("Trương Minh Khoa", "Lý Thanh Tâm")


@dataclass(frozen=True)
class VisitSeed:
    player: str                    # email người chơi demo; để trống với khách đặt tại quầy
    days: int                      # ngày chơi so với hôm nay (âm = đã qua)
    hour: int                      # khung đầu tiên trên lưới của cụm sân không sớm hơn giờ này
    hours: int = 1                 # số khung 60 phút liên tiếp
    rating: Optional[float] = None
    comment: str = ""


@dataclass(frozen=True)
class VenueRoomSeed:
    visit: VisitSeed               # đơn đặt sân của chủ phòng
    players: int
    purpose: str
    notes: str
    joiners: Tuple[str, ...] = ()


# Mỗi lượt dùng một khoảng giờ riêng trong ngày, nên cụm sân chỉ có một sân cũng không trùng lịch. Người chơi và ngày
# mở phòng được chọn để không đụng phòng đấu của bộ dữ liệu demo gốc (một người không thể ở hai phòng trùng giờ).
VENUE_PAST_VISITS = [
    VisitSeed("player04@gmail.com", -6, 6, 1, 5.0, "Buổi sáng sân thoáng, dễ đặt khung sớm, mặt sân bám tốt."),
    VisitSeed("player11@gmail.com", -5, 18, 2, 4.0, "Đánh buổi tối ổn, sân đủ sáng. Giờ cao điểm hơi đông."),
    VisitSeed("player16@gmail.com", -4, 17, 1, 5.0, "Giá hợp lý so với khu vực, đặt sân trên ứng dụng nhanh."),
    VisitSeed("player06@gmail.com", -3, 15, 1, 4.0, "Nhân viên hướng dẫn nhiệt tình, nhận sân đúng giờ."),
    VisitSeed("player18@gmail.com", -2, 18, 2, 5.0, "Nhận sân nhanh, nhóm mình sẽ quay lại."),
]
VENUE_NO_SHOW = VisitSeed("player08@gmail.com", -2, 20)
VENUE_REFUNDED = VisitSeed("player15@gmail.com", -1, 18)
VENUE_WALK_IN = VisitSeed("", -1, 9)
VENUE_TONIGHT = VisitSeed("player07@gmail.com", 0, 20)
VENUE_PHONE_HOLD = VisitSeed("", 1, 10)
VENUE_ROOMS = [
    VenueRoomSeed(VisitSeed("player13@gmail.com", 1, 6), 2, "practice",
                  "Tập cơ bản buổi sáng: dink và trả giao bóng, cần một bạn tập cùng."),
    VenueRoomSeed(VisitSeed("player12@gmail.com", 2, 18, 2), 4, "recreational",
                  "Giao lưu sau giờ làm, chia đều tiền sân.", ("player05@gmail.com",)),
]
VENUE_REFUND_PENDING = VisitSeed("player17@gmail.com", 2, 20)
VENUE_CONFIRMED = VisitSeed("player14@gmail.com", 3, 19)


class _VenueActivity:
    """Kịch bản hoạt động mẫu của MỘT cụm sân; phần đã qua được dựng với đồng hồ nghiệp vụ tua lùi."""

    def __init__(self, db: Session, venue: Venue):
        self.db, self.venue, self.today = db, venue, today_vn()
        self.courts = sorted((c for c in venue.courts if c.status == "ACTIVE"), key=lambda c: c.id)
        self.bookings: List[Booking] = []
        self.summary: dict = {"venue": venue.name, "owner": venue.owner.email if venue.owner else None,
                              "staff": [], "rooms": 0, "reviews": 0, "skipped": []}
        self._moment: Optional[datetime] = None

    # -- đồng hồ nghiệp vụ ---------------------------------------------------
    def at(self, moment: datetime) -> None:
        self._moment = moment
        timeutils.set_clock(lambda: self._moment)

    def now(self) -> None:
        self._moment = None
        timeutils.set_clock(None)

    def _stamp(self, booking: Booking) -> None:
        """Ghi thời điểm mô phỏng vào created_at của đơn và các dòng sổ (CSDL mặc định ghi giờ thật lúc chạy lệnh)."""
        if self._moment is None:
            return
        if booking.created_at is None or booking.created_at > self._moment:
            booking.created_at = self._moment
        for txn in self.db.query(PaymentTransaction).filter(PaymentTransaction.booking_id == booking.id):
            if txn.created_at is None or txn.created_at > self._moment:
                txn.created_at = txn.transaction_date = self._moment
        self.db.commit()

    # -- tiện ích --------------------------------------------------------------
    def _book(self, court: int, visit: VisitSeed, *, booked_days_before: int = 1, **desk) -> Optional[Booking]:
        """Tạo đơn cho một lượt chơi; không tạo được thì ghi lý do vào báo cáo và trả về None."""
        day = self.today + timedelta(days=visit.days)
        label = f"đơn ngày {day:%d/%m} lúc {visit.hour}h"
        options = _court_slot_options(self.venue, day, visit.hour, visit.hours)
        if not options:
            self.summary["skipped"].append(f"{label}: cụm sân không mở cửa khung giờ này.")
            return None
        slots = options[court % len(options)]
        user = desk.pop("user", None) or self.db.query(User).filter(User.email == visit.player).first()
        if user is None:
            self.summary["skipped"].append(f"{label}: chưa có tài khoản {visit.player}.")
            return None
        if visit.days < 0:   # khách tại quầy đến trước giờ chơi 10 phút, khách online đặt từ (các) hôm trước
            start = vn_datetime(day, slots[0].start_time)
            self.at(start - timedelta(minutes=10) if desk else vn_datetime(day - timedelta(days=booked_days_before), time(9, 0)))
        try:
            booking = booking_service.create_booking(self.db, user=user, slots=slots, **desk)
        except HTTPException as exc:
            self.db.rollback()
            self.summary["skipped"].append(f"{label}: {exc.detail}")
            return None
        self._stamp(booking)
        self.bookings.append(booking)
        return booking

    def _pay_deposit(self, booking: Booking) -> Booking:
        """Ghi sổ khoản cọc chuyển khoản của đơn, mang nhãn dữ liệu mẫu."""
        if self._moment is not None:
            self.at(self._moment + timedelta(minutes=5))
        deposit = float(booking.deposit_amount)
        ledger.record_transaction(
            self.db, booking, amount=deposit, kind=PaymentKind.DEPOSIT.value, method=PaymentMethod.BANK_TRANSFER.value,
            gateway=MATCH_DEMO_GATEWAY, reference_number=f"DEMO-{booking.booking_code}",
            content=f"{booking.booking_code} tien coc (du lieu mau)",
        )
        booking_service.apply_payment(self.db, booking, deposit)
        self.db.commit()
        self.db.refresh(booking)
        self._stamp(booking)
        return booking

    def _finish(self, booking: Booking) -> None:
        """Tua tới 5 phút sau giờ chơi rồi cho tác vụ nền chốt đơn: COMPLETED nếu đã nhận sân, NO_SHOW nếu không đến."""
        self.at(booking_service.last_slot_end(booking) + timedelta(minutes=5))
        booking_service.finalize_past_bookings(self.db)
        self.db.refresh(booking)

    def _review(self, booking: Booking, visit: VisitSeed) -> None:
        reviewed = self.db.query(Review.id).filter(Review.user_id == booking.user_id, Review.venue_id == self.venue.id).first()
        if booking.status != "COMPLETED" or visit.rating is None or reviewed:
            return
        self.db.add(Review(user_id=booking.user_id, venue_id=self.venue.id, rating=visit.rating, comment=visit.comment,
                           created_at=booking_service.last_slot_end(booking) + timedelta(hours=1)))
        self.db.commit()
        self.summary["reviews"] += 1

    def _staff(self) -> List[User]:
        """Nhân viên của cụm sân; cụm sân chưa có ai thì tạo hai tài khoản nhân viên mẫu."""
        staff = (self.db.query(User).join(StaffProfile, StaffProfile.user_id == User.id)
                 .filter(StaffProfile.venue_id == self.venue.id, User.is_active.is_(True)).order_by(User.id).all())
        if staff:
            return staff
        local = (self.venue.owner.email if self.venue.owner else "").partition("@")[0]
        slug = local[len("owner_"):] if local.startswith("owner_") and len(local) > len("owner_") else f"venue{self.venue.id}"
        for number, name in enumerate(DEMO_STAFF_NAMES, start=1):
            email = f"staff_{slug}_{number}@pickleball.vn"
            staff.append(create_user(self.db, email=email, password=DEMO_PASSWORD, role=UserRole.STAFF.value,
                                     full_name=f"{name} (NV {slug.replace('_', ' ').title()})", venue_id=self.venue.id))
            self.summary["staff"].append(email)
        return staff

    # -- kịch bản --------------------------------------------------------------
    def run(self) -> dict:
        if not self.courts:
            self.summary["skipped"].append("cụm sân chưa có sân nào đang hoạt động.")
            return self.summary
        staff = self._staff()
        self._past(staff)
        self.now()
        self._upcoming(staff)
        return self._close()

    def _past(self, staff: List[User]) -> None:
        # Đã chơi xong: cọc chuyển khoản từ hôm trước, phần còn lại trả tiền mặt lúc nhận sân, sau đó để lại đánh giá
        for court, visit in enumerate(VENUE_PAST_VISITS):
            booking = self._book(court, visit)
            if booking is None:
                continue
            self._pay_deposit(booking)
            self.at(booking_service.first_slot_start(booking))
            booking_service.check_in(self.db, booking, staff[0])
            self._stamp(booking)
            self._finish(booking)
            self._review(booking, visit)

        # Đã cọc nhưng không đến sân
        absent = self._book(3, VENUE_NO_SHOW)
        if absent is not None:
            self._pay_deposit(absent)
            self._finish(absent)

        # Hủy sớm (trước giờ chơi hơn 12 tiếng): được hoàn toàn bộ cọc và cụm sân đã chuyển hoàn
        refunded = self._book(2, VENUE_REFUNDED, booked_days_before=2)
        if refunded is not None:
            self._pay_deposit(refunded)
            day_before = self.today + timedelta(days=VENUE_REFUNDED.days - 1)
            self.at(vn_datetime(day_before, time(8, 0)))
            booking_service.cancel_by_player(self.db, refunded.id, refunded.user, _RefundInfo(
                bank_account="1900000003", bank_name="Vietcombank", account_holder="KHACH HANG MAU", reason="Bận việc đột xuất",
            ))
            self.at(vn_datetime(day_before, time(15, 0)))
            refunded = booking_service.get_booking_or_404(self.db, refunded.id)
            booking_service.confirm_refund(self.db, refunded, self.venue.owner or staff[0], f"Đã chuyển hoàn cọc {DEMO_NOTE}")
            self._stamp(refunded)

        # Khách vãng lai trả đủ tiền mặt tại quầy hôm qua
        walk_in = self._book(3, VENUE_WALK_IN, user=staff[0], source=BookingSource.DESK.value,
                             guest_name="Chị Lan (khách vãng lai)", guest_phone="0987000333",
                             desk_paid="FULL", check_in_now=True)
        if walk_in is not None:
            self._finish(walk_in)

    def _upcoming(self, staff: List[User]) -> None:
        # Tối nay: một đơn đã cọc để thử thao tác nhận sân tại quầy (chạy lệnh sau 20h thì khung này không còn đặt được)
        tonight = self._book(1, VENUE_TONIGHT)
        if tonight is not None:
            self._pay_deposit(tonight)

        # Hai đơn đã cọc có mở phòng đấu
        for court, room in enumerate(VENUE_ROOMS):
            booking = self._book(court, room.visit)
            if booking is None:
                continue
            self._pay_deposit(booking)
            host = booking.user
            try:
                match = match_service.create_match(self.db, host, MatchCreate(
                    booking_id=booking.id, required_skill=host.player_profile.skill_level if host.player_profile else None,
                    num_players=room.players, purpose=room.purpose, notes=room.notes,
                ))
            except HTTPException as exc:
                self.db.rollback()   # ví dụ chủ phòng đang ở một phòng khác trùng giờ: đơn vẫn giữ, chỉ không mở phòng
                self.summary["skipped"].append(f"phòng đấu của {room.visit.player}: {exc.detail}")
                continue
            self.summary["rooms"] += 1
            for email in room.joiners:
                joiner = self.db.query(User).filter(User.email == email).first()
                try:
                    if joiner is not None:
                        match_service.join_match(self.db, match.id, joiner.id)
                except HTTPException:
                    self.db.rollback()   # người này đang ở một phòng khác trùng giờ: phòng vẫn mở, chỉ thiếu một người

        # Khách gọi điện giữ sân, sẽ trả tiền khi đến
        self._book(3, VENUE_PHONE_HOLD, user=staff[0], source=BookingSource.DESK.value,
                   guest_name="Anh Tùng (đặt qua điện thoại)", guest_phone="0977000444", desk_paid="NONE")

        # Vừa hủy khi còn hơn 12 tiếng: đang chờ cụm sân hoàn cọc
        pending = self._book(2, VENUE_REFUND_PENDING)
        if pending is not None:
            self._pay_deposit(pending)
            booking_service.cancel_by_player(self.db, pending.id, pending.user, _RefundInfo(
                bank_account="1900000004", bank_name="MBBank", account_holder="KHACH HANG MAU", reason="Đổi kế hoạch",
            ))

        # Một đơn đã cọc bình thường
        confirmed = self._book(2, VENUE_CONFIRMED)
        if confirmed is not None:
            self._pay_deposit(confirmed)

    def _close(self) -> dict:
        ids = [booking.id for booking in self.bookings]
        rows = self.db.query(PaymentTransaction).filter(PaymentTransaction.booking_id.in_(ids)).all() if ids else []
        for txn in rows:   # dòng thu tại quầy và dòng hoàn tiền do hàm nghiệp vụ ghi: thêm ghi chú để nhận ra dữ liệu mẫu
            if txn.gateway != MATCH_DEMO_GATEWAY and DEMO_NOTE not in (txn.transaction_content or ""):
                txn.transaction_content = f"{txn.transaction_content or ''} {DEMO_NOTE}".strip()
        self.db.commit()
        statuses: Dict[str, int] = {}
        for booking in self.bookings:
            self.db.refresh(booking)
            statuses[booking.status] = statuses.get(booking.status, 0) + 1
        self.summary.update(
            bookings=len(self.bookings), statuses=statuses,
            collected=sum(t.amount_in for t in rows if t.kind != PaymentKind.REFUND.value),
            refunded=sum(t.amount_in for t in rows if t.kind == PaymentKind.REFUND.value),
        )
        return self.summary


def seed_venue_activity(db: Session, venue_id: Optional[int] = None) -> dict:
    """
    Nạp hoạt động mẫu (nhân viên, đơn đặt ở nhiều trạng thái, giao dịch, phòng đấu, đánh giá) cho cụm sân đang hoạt
    động chưa có đơn nào: cụm sân mang `venue_id`, hoặc mọi cụm sân như vậy khi không chỉ định. Dữ liệu đã có không
    bị sửa. Trả về {"venues": [báo cáo của từng cụm sân], "skipped": [lý do bỏ qua]}.
    """
    result: dict = {"venues": [], "skipped": []}
    query = db.query(Venue).filter(Venue.status == "ACTIVE")
    venues = (query.filter(Venue.id == venue_id) if venue_id is not None else query).order_by(Venue.id).all()
    if venue_id is not None and not venues:
        result["skipped"].append(f"Không có cụm sân đang hoạt động nào mang id {venue_id}.")
    for venue in venues:
        booked = db.query(BookingDetail.id).join(Court, Court.id == BookingDetail.court_id).filter(Court.venue_id == venue.id).first()
        if booked is not None:
            if venue_id is not None:
                result["skipped"].append(f"{venue.name}: đã có đơn đặt sân nên không nạp thêm.")
            continue
        try:
            result["venues"].append(_VenueActivity(db, venue).run())
        finally:
            timeutils.set_clock(None)
    return result


def add_venue_activity(venue_id: Optional[int] = None) -> dict:
    """
    Chạy seed_venue_activity trong MỘT giao dịch CSDL: nạp trọn vẹn, hoặc không ghi gì nếu có lỗi giữa chừng.
    Nhờ vậy ứng dụng đang chạy song song (tác vụ nền chốt đơn quá giờ mỗi phút) không bao giờ thấy một đơn mẫu
    còn dựng dở, ví dụ đơn của hôm qua đã cọc nhưng chưa kịp ghi nhận sân.
    """
    if settings.is_sqlite:
        with SessionLocal() as db:
            return seed_venue_activity(db, venue_id)
    with engine.connect() as connection, connection.begin():
        with SessionLocal(bind=connection, join_transaction_mode="create_savepoint") as db:
            return seed_venue_activity(db, venue_id)


def report_venue_activity(result: dict) -> None:
    for item in result["venues"]:
        statuses = ", ".join(f"{count} {name}" for name, count in sorted(item.get("statuses", {}).items()))
        print(f"{item['venue']}:")
        print(f"  {item.get('bookings', 0)} đơn đặt sân ({statuses}) | {item['rooms']} phòng đấu | {item['reviews']} đánh giá")
        print(f"  sổ giao dịch mẫu: thu {item.get('collected', 0):,.0f}đ, hoàn {item.get('refunded', 0):,.0f}đ "
              f"(tiền cọc chuyển khoản mang nhãn \"{MATCH_DEMO_GATEWAY}\")")
        if item["staff"]:
            print(f"  tài khoản nhân viên mới: {', '.join(item['staff'])} (mật khẩu {DEMO_PASSWORD})")
        if item["owner"]:
            print(f"  tài khoản chủ sân: {item['owner']}")
        for reason in item["skipped"]:
            print(f"  bỏ qua - {reason}")
    for reason in result["skipped"]:
        print(f"bỏ qua - {reason}")
    if not result["venues"] and not result["skipped"]:
        print("Không có cụm sân nào cần nạp: mọi cụm sân đang hoạt động đều đã có đơn đặt sân.")


# ---------------------------------------------------------------------------
# Điểm vào
# ---------------------------------------------------------------------------
def seed_database(if_empty: bool = False, reset: bool = False, assume_yes: bool = False) -> bool:
    """Nạp dữ liệu demo. Trả về True nếu đã nạp, False nếu bỏ qua vì CSDL đã có dữ liệu."""
    if reset:
        rebuild_empty_schema("Nạp lại dữ liệu demo", assume_yes)
    else:
        ensure_schema()

    db = SessionLocal()
    try:
        existing = db.query(User).count()
        if existing:
            if if_empty:
                print(f"CSDL đã có {existing} tài khoản: bỏ qua bước nạp dữ liệu demo.")
                return False
            raise SystemExit(
                f"CSDL đã có {existing} tài khoản. Dùng --reset để xóa và nạp lại, "
                "hoặc --preferences để chỉ bổ sung mục đích chơi và ngày sinh mẫu cho tài khoản demo."
            )

        print("Đang nạp tiện ích, tài khoản và cụm sân...")
        ctx = seed_accounts_and_venues(db, seed_amenities(db))
        print("Đang tạo đơn đặt sân, giao dịch, phòng đấu và đánh giá mẫu...")
        activity = DemoActivity(db, ctx)
        try:
            activity.past()
            activity.upcoming()
        finally:
            timeutils.set_clock(None)

        from app.models.match import Match

        print("Đang nạp phiếu ghép cặp mô phỏng cho mô hình...")
        simulated = seed_simulated_feedback(db)

        print("=" * 72)
        print(f"Đã nạp: {db.query(User).count()} tài khoản | {db.query(Venue).count()} cụm sân | "
              f"{db.query(Court).count()} sân | {db.query(Booking).count()} đơn đặt | "
              f"{db.query(PaymentTransaction).count()} giao dịch | {db.query(Match).count()} phòng đấu | "
              f"{db.query(Review).count()} đánh giá | {simulated:,} phiếu ghép cặp mô phỏng")
        print(f"Mật khẩu demo dùng chung: {DEMO_PASSWORD}  (các tài khoản chính: README.md, mục Tài khoản demo)")
        print("=" * 72)
        return True
    finally:
        db.close()


def report_simulated_feedback(added: int) -> None:
    if added:
        print(f"Đã nạp {added:,} phiếu ghép cặp mô phỏng vào bảng pair_feedback (nguồn \"{SIMULATED_SOURCE}\").")
        print("Huấn luyện mô hình từ dữ liệu này: python manage.py train-model")
    else:
        print("Không nạp thêm: CSDL đã có phiếu mô phỏng, hoặc chưa có tài khoản người chơi demo.")
        print("Muốn thay các phiếu mô phỏng bằng bộ sinh theo quy tắc hiện tại: python manage.py seed --feedback --regenerate")


def main() -> None:
    args = set(sys.argv[1:])
    if "--preferences" in args:
        ensure_schema()
        with SessionLocal() as db:
            print(f"Đã bổ sung mục đích chơi, ngày sinh mẫu cho {apply_demo_preferences(db)} tài khoản demo.")
        return
    if "--feedback" in args:
        ensure_schema()
        with SessionLocal() as db:
            report_simulated_feedback(seed_simulated_feedback(db, replace="--regenerate" in args))
        return
    if "--matches" in args:
        ensure_schema()
        with SessionLocal() as db:
            report_match_demo(seed_match_demo(db))
        return
    if "--activity" in args:
        argv, venue_id = sys.argv[1:], None
        if "--venue" in argv:
            value = argv[argv.index("--venue") + 1:][:1]
            if not value or not value[0].isdigit():
                raise SystemExit("--venue cần id của cụm sân, ví dụ: --activity --venue 4")
            venue_id = int(value[0])
        ensure_schema()
        report_venue_activity(add_venue_activity(venue_id))
        return
    seed_database(if_empty="--if-empty" in args, reset="--reset" in args, assume_yes="--yes" in args)


if __name__ == "__main__":
    main()
