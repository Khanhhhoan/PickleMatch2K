import hashlib
import io
import logging
import os
import re
import time
import uuid
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.booking import Booking, RefundProof
from app.utils.timeutils import now_utc

logger = logging.getLogger("pickleball.storage")

UPLOAD_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
VENUE_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "venues")
os.makedirs(VENUE_UPLOAD_DIR, exist_ok=True)

LOCAL_URL_PREFIX = "/uploads/venues/"

# Ảnh đại diện của người chơi: luôn được vẽ lại thành ảnh vuông nhỏ (xem make_avatar) rồi lưu như ảnh cụm sân
AVATAR_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "avatars")
os.makedirs(AVATAR_UPLOAD_DIR, exist_ok=True)
AVATAR_URL_PREFIX = "/uploads/avatars/"
AVATAR_SIZE = 320
# Ảnh nén rất nhỏ vẫn có thể bung ra hàng trăm triệu điểm ảnh khi giải mã: chặn trước khi xử lý
AVATAR_MAX_PIXELS = 40_000_000

# Chỉ nhận ảnh bitmap. SVG bị loại vì có thể chứa mã script và được phục vụ cùng origin với API.
_PIL_FORMAT_TO_EXT = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp", "GIF": ".gif"}

# Chứng từ hoàn tiền là dữ liệu tài chính của khách: lưu trong CSDL (bảng refund_proofs), NGOÀI thư mục /uploads công
# khai, và chỉ tải được qua API có kiểm tra quyền (GET /bookings/{id}/refund-proof). Không đưa lên Cloudinary vì liên
# kết ở đó ai có cũng mở được; không để trên ổ đĩa vì máy chủ kiểu Render xóa ổ đĩa mỗi lần khởi động lại.
MAX_PROOF_BYTES = 5 * 1024 * 1024
_PROOF_MEDIA_TYPES = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf"}
_PROOF_NAME = re.compile(r"^\d+_[0-9a-f]{32}\.(jpg|png|webp|pdf)$")


def max_image_bytes() -> int:
    return settings.MAX_IMAGE_SIZE_MB * 1024 * 1024


def detect_image_extension(contents: bytes) -> str:
    """
    Xác định định dạng từ chính nội dung file (không tin tên file hay Content-Type do client gửi).
    Trả về phần mở rộng chuẩn hoặc báo lỗi 400 nếu không phải ảnh hợp lệ.
    """
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tệp tin ảnh rỗng (0 bytes).")
    if len(contents) > max_image_bytes():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dung lượng ảnh vượt quá giới hạn cho phép ({settings.MAX_IMAGE_SIZE_MB}MB).",
        )
    try:
        from PIL import Image

        with Image.open(io.BytesIO(contents)) as img:
            img.verify()
            image_format = (img.format or "").upper()
    except Exception:
        image_format = ""

    ext = _PIL_FORMAT_TO_EXT.get(image_format)
    if not ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tệp tin không phải ảnh hợp lệ. Chỉ chấp nhận JPG, PNG, WEBP, GIF.",
        )
    return ext


def _cloudinary_enabled() -> bool:
    return (
        settings.STORAGE_BACKEND.lower() == "cloudinary"
        and bool(settings.CLOUDINARY_CLOUD_NAME and settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET)
    )


def save_venue_image(venue_id: int, contents: bytes) -> str:
    """
    Lưu ảnh theo STORAGE_BACKEND: "cloudinary" (nếu đủ khóa) hoặc "local" (/uploads/venues/...).
    Hàm này chặn (ghi đĩa / gọi HTTP) nên endpoint async phải gọi qua run_in_threadpool.
    """
    ext = detect_image_extension(contents)

    if _cloudinary_enabled():
        cloud_url = _upload_cloudinary(contents, f"picklematch2k/venues/v{venue_id}_{uuid.uuid4().hex[:10]}", ext)
        if cloud_url:
            return cloud_url
        logger.warning("Upload Cloudinary thất bại, lưu ảnh cục bộ thay thế.")

    unique_filename = f"venue_{venue_id}_{uuid.uuid4().hex[:12]}{ext}"
    with open(os.path.join(VENUE_UPLOAD_DIR, unique_filename), "wb") as f:
        f.write(contents)
    return f"{LOCAL_URL_PREFIX}{unique_filename}"


def delete_venue_image_file(image_url: str) -> bool:
    """
    Xóa file ảnh khỏi nơi lưu trữ. Người gọi phải bảo đảm image_url thuộc đúng cụm sân
    mà người dùng có quyền (xem endpoint delete_venue_image).
    """
    if not image_url:
        return False
    if image_url.startswith(LOCAL_URL_PREFIX):
        return _delete_local_file(image_url, VENUE_UPLOAD_DIR)
    if "res.cloudinary.com" in image_url and _cloudinary_enabled():
        return _delete_cloudinary(image_url)
    return False


def _delete_local_file(url: str, directory: str) -> bool:
    """Xóa tệp tên lấy từ url, chỉ khi tệp nằm đúng trong thư mục được phép."""
    filename = os.path.basename(url)
    safe_path = os.path.abspath(os.path.join(directory, filename))
    if os.path.commonpath([directory, safe_path]) != directory:
        logger.warning("Chặn yêu cầu xóa file ngoài thư mục ảnh: %s", url)
        return False
    if os.path.exists(safe_path):
        try:
            os.remove(safe_path)
            return True
        except OSError as exc:
            logger.error("Không xóa được file ảnh %s: %s", safe_path, exc)
    return False


# ---------------------------------------------------------------------------
# Ảnh đại diện của người chơi
# ---------------------------------------------------------------------------
def make_avatar(contents: bytes) -> bytes:
    """
    Kiểm tra đúng là ảnh (theo nội dung), xoay theo hướng chụp ghi trong EXIF, cắt vuông phần giữa và thu về
    AVATAR_SIZE x AVATAR_SIZE dạng WEBP. Ảnh được vẽ lại từ điểm ảnh nên mọi siêu dữ liệu (EXIF có thể chứa toạ độ GPS
    nơi chụp, tên máy...) đều bị bỏ, và tệp chỉ còn vài chục KB dù ảnh gốc chụp bằng điện thoại.
    """
    detect_image_extension(contents)
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(contents)) as img:
        if img.width * img.height > AVATAR_MAX_PIXELS:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ảnh có kích thước quá lớn, hãy chọn ảnh nhỏ hơn.")
        upright = ImageOps.exif_transpose(img)
        transparent = upright.mode in ("RGBA", "LA", "PA") or "transparency" in upright.info
        square = ImageOps.fit(upright.convert("RGBA" if transparent else "RGB"), (AVATAR_SIZE, AVATAR_SIZE),
                              method=Image.Resampling.LANCZOS)
    output = io.BytesIO()
    square.save(output, format="WEBP", quality=85)
    return output.getvalue()


def save_avatar(user_id: int, contents: bytes) -> str:
    """
    Xử lý (make_avatar) rồi lưu ảnh đại diện theo STORAGE_BACKEND như ảnh cụm sân; trả về đường dẫn để hiển thị.
    Hàm này chặn (xử lý ảnh, ghi đĩa / gọi HTTP) nên endpoint async phải gọi qua run_in_threadpool.
    """
    avatar = make_avatar(contents)
    token = uuid.uuid4().hex[:12]
    if _cloudinary_enabled():
        cloud_url = _upload_cloudinary(avatar, f"picklematch2k/avatars/u{user_id}_{token}", ".webp")
        if cloud_url:
            return cloud_url
        logger.warning("Upload Cloudinary thất bại, lưu ảnh đại diện cục bộ thay thế.")
    filename = f"user_{user_id}_{token}.webp"
    with open(os.path.join(AVATAR_UPLOAD_DIR, filename), "wb") as f:
        f.write(avatar)
    return f"{AVATAR_URL_PREFIX}{filename}"


def delete_avatar_file(avatar_url: Optional[str]) -> bool:
    """Xóa tệp ảnh đại diện cũ; chỉ xóa tệp do hệ thống lưu (thư mục ảnh đại diện hoặc thư mục avatars trên Cloudinary)."""
    if not avatar_url:
        return False
    if avatar_url.startswith(AVATAR_URL_PREFIX):
        return _delete_local_file(avatar_url, AVATAR_UPLOAD_DIR)
    if "res.cloudinary.com" in avatar_url and "/picklematch2k/avatars/" in avatar_url and _cloudinary_enabled():
        return _delete_cloudinary(avatar_url)
    return False


def _cloudinary_signature(params: dict) -> str:
    to_sign = "&".join(f"{k}={params[k]}" for k in sorted(params)) + (settings.CLOUDINARY_API_SECRET or "")
    return hashlib.sha1(to_sign.encode("utf-8")).hexdigest()


def _upload_cloudinary(contents: bytes, public_id: str, ext: str) -> Optional[str]:
    try:
        import httpx

        params = {"public_id": public_id, "timestamp": int(time.time())}
        data = {**params, "api_key": settings.CLOUDINARY_API_KEY, "signature": _cloudinary_signature(params)}
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/upload"
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, data=data, files={"file": (f"image{ext}", contents)})
        if resp.status_code in (200, 201):
            return resp.json().get("secure_url")
        logger.warning("Cloudinary trả về mã %s", resp.status_code)
    except Exception as exc:
        logger.warning("Lỗi upload Cloudinary: %s", exc)
    return None


def _delete_cloudinary(image_url: str) -> bool:
    match = re.search(r"/upload/(?:v\d+/)?(picklematch2k/(?:venues|avatars)/[^.]+)", image_url)
    if not match:
        return False
    try:
        import httpx

        params = {"public_id": match.group(1), "timestamp": int(time.time())}
        data = {**params, "api_key": settings.CLOUDINARY_API_KEY, "signature": _cloudinary_signature(params)}
        url = f"https://api.cloudinary.com/v1_1/{settings.CLOUDINARY_CLOUD_NAME}/image/destroy"
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, data=data)
        return resp.status_code == 200
    except Exception as exc:
        logger.warning("Không xóa được ảnh Cloudinary: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Chứng từ hoàn tiền (lưu riêng, không công khai)
# ---------------------------------------------------------------------------
def _proof_extension(contents: bytes) -> str:
    """Định dạng chứng từ xác định từ nội dung tệp: ảnh JPG/PNG/WEBP hoặc PDF."""
    if not contents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tệp chứng từ rỗng (0 bytes).")
    if len(contents) > MAX_PROOF_BYTES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tệp chứng từ vượt quá 5MB.")
    if contents.startswith(b"%PDF-"):
        return ".pdf"
    try:
        ext = detect_image_extension(contents)
    except HTTPException:
        ext = ""
    if ext not in (".jpg", ".png", ".webp"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chứng từ phải là ảnh JPG, PNG, WEBP hoặc tệp PDF.",
        )
    return ext


def save_refund_proof(db: Session, booking: Booking, contents: bytes) -> None:
    """Lưu chứng từ hoàn tiền của một đơn vào CSDL, thay tệp cũ nếu có. Người gọi commit (tệp và đơn cùng một giao dịch)."""
    ext = _proof_extension(contents)
    name = f"{booking.id}_{uuid.uuid4().hex}{ext}"
    proof = db.get(RefundProof, booking.id)
    if proof is None:
        proof = RefundProof(booking_id=booking.id)
        db.add(proof)
    proof.name = name
    proof.media_type = _PROOF_MEDIA_TYPES[ext]
    proof.size = len(contents)
    proof.content = contents
    proof.uploaded_at = now_utc()
    booking.refund_proof_file = name


def load_refund_proof(db: Session, booking: Booking) -> tuple:
    """(nội dung, media type, đuôi tệp) của chứng từ hiện tại của đơn; 404 nếu không có."""
    name = booking.refund_proof_file or ""
    proof = db.get(RefundProof, booking.id) if _PROOF_NAME.fullmatch(name) else None
    if proof is None or proof.name != name:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy tệp chứng từ.")
    return proof.content, proof.media_type, os.path.splitext(name)[1]
