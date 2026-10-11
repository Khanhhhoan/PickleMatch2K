"""
In báo cáo tổng quan dữ liệu trong CSDL đang cấu hình (chỉ đọc).

    python scripts/show_db.py
"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import scripts._common  # noqa: E402,F401  (cấu hình sys.path và mã hóa đầu ra)

from sqlalchemy import func  # noqa: E402

from app.db.database import SessionLocal, engine  # noqa: E402
from app.models.booking import Booking  # noqa: E402
from app.models.match import Match  # noqa: E402
from app.models.ml import PairFeedback  # noqa: E402
from app.models.payment import PaymentKind, PaymentTransaction  # noqa: E402
from app.models.user import PlayerProfile, User  # noqa: E402
from app.models.venue import Amenity, Court, Review, Venue  # noqa: E402

LINE = "=" * 88


def _counts(db, column):
    return dict(db.query(column, func.count()).group_by(column).all())


def show_db_stats() -> None:
    db = SessionLocal()
    try:
        print(LINE)
        print(f"BÁO CÁO DỮ LIỆU - CSDL '{engine.url.database}' ({engine.dialect.name})")
        print(LINE)

        roles = _counts(db, User.role)
        print(f"Tài khoản: {sum(roles.values())}  " + "  ".join(f"{role}={count}" for role, count in sorted(roles.items()))
              + f"  (đang khóa: {db.query(User).filter(User.is_active.is_(False)).count()})")
        print(f"Cụm sân: {db.query(Venue).count()}  |  Sân: {db.query(Court).count()}  |  "
              f"Tiện ích: {db.query(Amenity).count()}  |  Đánh giá: {db.query(Review).count()}")
        print("Đơn đặt theo trạng thái: " + (", ".join(f"{k}={v}" for k, v in sorted(_counts(db, Booking.status).items())) or "chưa có"))
        print("Phòng đấu theo trạng thái: " + (", ".join(f"{k}={v}" for k, v in sorted(_counts(db, Match.status).items())) or "chưa có"))

        money = dict(db.query(PaymentTransaction.kind, func.coalesce(func.sum(PaymentTransaction.amount_in), 0))
                     .filter(PaymentTransaction.status == "SUCCESS").group_by(PaymentTransaction.kind).all())
        collected = money.get(PaymentKind.DEPOSIT.value, 0) + money.get(PaymentKind.BALANCE.value, 0)
        refunded = money.get(PaymentKind.REFUND.value, 0)
        print(f"Sổ giao dịch: đã thu {collected:,.0f}đ  |  đã hoàn {refunded:,.0f}đ  |  thực thu {collected - refunded:,.0f}đ")
        filled = db.query(PlayerProfile).filter(PlayerProfile.purpose.isnot(None)).count()
        print(f"Hồ sơ người chơi đã khai mục đích chơi: {filled}/{db.query(PlayerProfile).count()}  |  "
              f"Nhãn khảo sát ghép cặp: {db.query(PairFeedback).count()}")

        print(f"\n{'ID':<4} {'Cụm sân':<34} {'Trạng thái':<12} {'Sân':<4} {'Chủ sân':<34}")
        print("-" * 88)
        for venue in db.query(Venue).order_by(Venue.id).all():
            owner = venue.owner.email if venue.owner else "-"
            print(f"{venue.id:<4} {venue.name[:32]:<34} {venue.status or '-':<12} {len(venue.courts):<4} {owner[:32]:<34}")

        print(f"\n{'Mã đơn':<12} {'Khách':<22} {'Cụm sân':<24} {'Tổng tiền':>11} {'Đã trả':>11}  {'Trạng thái':<11}")
        print("-" * 88)
        for booking in db.query(Booking).order_by(Booking.id.desc()).limit(10).all():
            venue_name = booking.details[0].venue_name if booking.details else "-"
            print(f"{booking.booking_code or '#' + str(booking.id):<12} {booking.user_name[:20]:<22} {venue_name[:22]:<24} "
                  f"{booking.total_price:>10,.0f}đ {booking.paid_amount or 0:>10,.0f}đ  {booking.status:<11}")
        print(LINE)
    finally:
        db.close()


if __name__ == "__main__":
    show_db_stats()
