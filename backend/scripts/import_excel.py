"""
Nhập cụm sân từ file Excel theo mẫu docs/Mau_Nhap_Du_Lieu_Pickleball.xlsx. Chỉ BỔ SUNG, không xóa dữ liệu.

    python scripts/import_excel.py [duong_dan.xlsx] [--dry-run] [--password MAT_KHAU]

Mỗi dòng tạo (hoặc cập nhật theo email + tên cụm sân) tài khoản chủ sân, cụm sân, sân con,
giờ mở cửa cả tuần và bảng giá. Dòng thiếu ô bắt buộc bị bỏ qua và được báo lại; script không tự
điền số điện thoại, tài khoản ngân hàng hay toạ độ thay thế. Toạ độ chỉ được lấy khi link Google Maps
có dạng ...?q=<vĩ độ>,<kinh độ>.

Tài khoản chủ sân mới nhận mật khẩu ngẫu nhiên (in ra một lần ở cuối), trừ khi truyền --password.
--dry-run: kiểm tra và in kết quả nhưng không ghi vào CSDL.
"""
import argparse
import json
import re
import secrets
import sys
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from scripts._common import ensure_schema  # noqa: E402

import pandas as pd  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.models.venue import Amenity, Court, OperatingHour, PriceRule, Venue  # noqa: E402
from app.services.user_service import create_user, get_user_by_email  # noqa: E402

DEFAULT_TEMPLATE = BACKEND_DIR.parent / "docs" / "Mau_Nhap_Du_Lieu_Pickleball.xlsx"

# từ khóa trong tên cột (chữ thường) -> tên trường
COLUMN_KEYWORDS = [
    ("tên cụm", "name"), ("địa chỉ", "address"), ("sân con", "courts"),
    ("giá thường", "base_price"), ("cao điểm", "peak_price"), ("cuối tuần", "weekend_price"),
    ("mở cửa", "open_time"), ("đóng cửa", "close_time"), ("họ tên chủ", "owner_name"), ("email", "owner_email"),
    ("điện thoại", "phone"), ("ngân hàng", "bank"), ("tiện ích", "amenities"), ("mô tả", "description"),
    ("maps", "maps"), ("ảnh", "image"),
]
REQUIRED = {"name": "Tên cụm sân", "address": "Địa chỉ", "courts": "Danh sách sân con",
            "owner_email": "Email chủ sân", "base_price": "Giá thường"}

# từ khóa trong ô "Tiện ích" -> tên tiện ích chuẩn trong CSDL
AMENITY_KEYWORDS = [
    ("mái che", "Sân có mái che / Trong nhà"), ("trong nhà", "Sân có mái che / Trong nhà"),
    ("đèn", "Đèn LED chống lóa 500 Lux"),
    ("phòng nghỉ", "Phòng nghỉ điều hòa máy lạnh"), ("máy lạnh", "Phòng nghỉ điều hòa máy lạnh"),
    ("căn tin", "Căng tin & Nước giải khát thể thao"), ("căng tin", "Căng tin & Nước giải khát thể thao"),
    ("thuê vợt", "Cho thuê vợt & bóng Franklin X-40"),
    ("đỗ xe", "Bãi đỗ xe ô tô & xe máy miễn phí"), ("bãi xe", "Bãi đỗ xe ô tô & xe máy miễn phí"),
    ("thay đồ", "Phòng thay đồ & Tắm nóng lạnh"), ("tắm", "Phòng thay đồ & Tắm nóng lạnh"),
    ("hlv", "HLV đào tạo & Trọng tài DUPR"), ("lớp học", "HLV đào tạo & Trọng tài DUPR"),
]


def _text(value) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _money(value) -> Optional[float]:
    raw = _text(value)
    if raw is None:
        return None
    try:
        amount = float(raw.replace(",", "").replace(" ", ""))
    except ValueError:
        return None
    return amount if amount > 0 else None


def _clock(value) -> Optional[time]:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    raw = _text(value)
    match = re.match(r"^(\d{1,2})(?:[:h](\d{2}))?", raw or "")
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2) or 0)
    return time(hour, minute) if hour < 24 and minute < 60 else None


def _phone(value) -> Optional[str]:
    raw = _text(value)
    if raw is None:
        return None
    digits = re.sub(r"\D", "", raw[:-2] if raw.endswith(".0") else raw)
    if not digits:
        return None
    # Excel thường làm mất số 0 đầu của số điện thoại 9 chữ số
    return digits if digits.startswith("0") or len(digits) != 9 else "0" + digits


def _coordinates(maps_url: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    match = re.search(r"[?&]q(?:uery)?=(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", maps_url or "")
    if not match:
        return None, None
    lat, lng = float(match.group(1)), float(match.group(2))
    return (lat, lng) if -90 <= lat <= 90 and -180 <= lng <= 180 else (None, None)


def read_rows(excel_path: Path) -> List[Dict[str, object]]:
    workbook = pd.ExcelFile(excel_path)
    sheet = next((n for n in workbook.sheet_names if "danh_sach" in n.lower() or "danh sách" in n.lower()),
                 workbook.sheet_names[0])
    frame = pd.read_excel(workbook, sheet_name=sheet)
    fields = {}
    for column in frame.columns:
        normalised = str(column).lower().replace("\n", " ")
        field = next((name for keyword, name in COLUMN_KEYWORDS if keyword in normalised), None)
        if field and field not in fields:
            fields[field] = column
    return [{field: row[column] for field, column in fields.items()} | {"_line": index + 2}
            for index, row in frame.iterrows()]


def parse_row(raw: Dict[str, object]) -> Tuple[Optional[dict], List[str]]:
    """Chuẩn hóa một dòng; trả về (dữ liệu, danh sách lỗi)."""
    maps = _text(raw.get("maps"))
    lat, lng = _coordinates(maps)
    data = {
        "name": _text(raw.get("name")),
        "address": _text(raw.get("address")),
        "courts": [c.strip() for c in (_text(raw.get("courts")) or "").split(",") if c.strip()],
        "base_price": _money(raw.get("base_price")),
        "peak_price": _money(raw.get("peak_price")),
        "weekend_price": _money(raw.get("weekend_price")),
        "open_time": _clock(raw.get("open_time")),
        "close_time": _clock(raw.get("close_time")),
        "owner_name": _text(raw.get("owner_name")),
        "owner_email": (_text(raw.get("owner_email")) or "").lower() or None,
        "phone": _phone(raw.get("phone")),
        "bank": _text(raw.get("bank")),
        "amenities": (_text(raw.get("amenities")) or "").lower(),
        "description": _text(raw.get("description")),
        "maps": maps, "lat": lat, "lng": lng,
        "image": _text(raw.get("image")),
    }
    if not data["name"]:
        return None, []  # dòng trống
    errors = [f"thiếu {label}" for field, label in REQUIRED.items() if not data[field]]
    if data["owner_email"] and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", data["owner_email"]):
        errors.append("email chủ sân không hợp lệ")
    if not data["open_time"] or not data["close_time"]:
        errors.append("thiếu giờ mở/đóng cửa")
    elif data["open_time"] >= data["close_time"]:
        errors.append("giờ mở cửa phải trước giờ đóng cửa")
    return data, errors


def ensure_amenities(db) -> Dict[str, Amenity]:
    from scripts.seed import seed_amenities

    seed_amenities(db)
    return {a.name: a for a in db.query(Amenity).all()}


def import_row(db, data: dict, amenities: Dict[str, Amenity], password: Optional[str], created_accounts: list) -> str:
    owner = get_user_by_email(db, data["owner_email"])
    if owner is None:
        secret = password or secrets.token_urlsafe(8)
        owner = create_user(db, email=data["owner_email"], password=secret, role=UserRole.OWNER.value,
                            full_name=data["owner_name"], phone=data["phone"], commit=False)
        db.refresh(owner)
        created_accounts.append((data["owner_email"], secret))
    elif owner.role != UserRole.OWNER.value:
        raise ValueError(f"email {data['owner_email']} đã thuộc về tài khoản vai trò {owner.role}")
    profile = owner.owner_profile
    if profile is not None:
        profile.full_name = data["owner_name"] or profile.full_name
        profile.phone = data["phone"] or profile.phone
        profile.bank_account = data["bank"] or profile.bank_account

    venue = db.query(Venue).filter(Venue.owner_id == owner.id, Venue.name == data["name"]).first()
    action = "cập nhật" if venue else "tạo mới"
    if venue is None:
        venue = Venue(owner_id=owner.id, name=data["name"], address=data["address"], status="ACTIVE")
        db.add(venue)
    venue.address = data["address"]
    venue.description = data["description"] or venue.description
    venue.google_maps_url = data["maps"] or venue.google_maps_url
    if data["lat"] is not None:
        venue.latitude, venue.longitude = data["lat"], data["lng"]
    if data["image"] and not venue.image_url:
        venue.image_url, venue.images = data["image"], json.dumps([data["image"]])
    db.flush()

    wanted = {amenities[name] for keyword, name in AMENITY_KEYWORDS if keyword in data["amenities"] and name in amenities}
    for amenity in wanted - set(venue.amenities):
        venue.amenities.append(amenity)

    existing_courts = {c.name for c in venue.courts}
    for name in data["courts"]:
        if name not in existing_courts:
            db.add(Court(venue_id=venue.id, name=name, status="ACTIVE"))
    if not venue.operating_hours:
        for day in range(7):
            db.add(OperatingHour(venue_id=venue.id, day_of_week=day, open_time=data["open_time"], close_time=data["close_time"]))
    if not venue.price_rules:
        db.add(PriceRule(venue_id=venue.id, rule_type="BASE", start_time=time(6, 0), end_time=time(17, 0), price=data["base_price"]))
        db.add(PriceRule(venue_id=venue.id, rule_type="PEAK", start_time=time(17, 0), end_time=time(23, 0),
                         price=data["peak_price"] or data["base_price"]))
        db.add(PriceRule(venue_id=venue.id, rule_type="WEEKEND", price=data["weekend_price"] or data["base_price"]))
    db.flush()
    return action


def import_from_excel(excel_path, dry_run: bool = False, password: Optional[str] = None) -> dict:
    excel_path = Path(excel_path)
    if not excel_path.exists():
        raise SystemExit(f"Không tìm thấy file: {excel_path}")
    ensure_schema()

    summary = {"imported": 0, "skipped": [], "accounts": []}
    db = SessionLocal()
    try:
        amenities = ensure_amenities(db)
        for raw in read_rows(excel_path):
            data, errors = parse_row(raw)
            if data is None:
                continue
            if not errors:
                try:
                    with db.begin_nested():
                        action = import_row(db, data, amenities, password, summary["accounts"])
                    print(f"  ✓ dòng {raw['_line']}: {action} '{data['name']}' ({len(data['courts'])} sân)"
                          + ("" if data["lat"] is not None else " - chưa có toạ độ"))
                    summary["imported"] += 1
                    continue
                except ValueError as exc:
                    errors = [str(exc)]
            summary["skipped"].append((raw["_line"], data["name"], errors))
            print(f"  ✗ dòng {raw['_line']}: bỏ qua '{data['name']}' ({'; '.join(errors)})")

        if dry_run:
            db.rollback()
            print("Chạy thử (--dry-run): không ghi gì vào CSDL.")
        else:
            db.commit()
    finally:
        db.close()

    print(f"Đã nhập {summary['imported']} cụm sân, bỏ qua {len(summary['skipped'])} dòng.")
    if summary["accounts"] and not dry_run:
        print("Tài khoản chủ sân mới (hãy đổi mật khẩu sau lần đăng nhập đầu):")
        for email, secret in summary["accounts"]:
            print(f"    {email}  /  {secret}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Nhập cụm sân từ file Excel")
    parser.add_argument("file", nargs="?", default=str(DEFAULT_TEMPLATE), help="Đường dẫn file .xlsx")
    parser.add_argument("--dry-run", action="store_true", help="Chỉ kiểm tra, không ghi vào CSDL")
    parser.add_argument("--password", default=None, help="Mật khẩu cho tài khoản chủ sân mới (mặc định: ngẫu nhiên)")
    args = parser.parse_args()
    import_from_excel(args.file, dry_run=args.dry_run, password=args.password)


if __name__ == "__main__":
    main()
